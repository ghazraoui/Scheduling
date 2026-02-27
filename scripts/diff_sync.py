"""
Diff-based calendar sync engine for Scheduling V2.

Compares new schedule data against the last-synced state and produces
targeted Graph API operations (create/delete) instead of clearing everything.

State files (data/last_synced/{agenda}.json) store synced events with their
Outlook event IDs for targeted deletes on subsequent runs.

Used by sync_calendars.py (method classes) and sync_private_calendars.py (VIP).
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / "data" / "last_synced"


# ---------------------------------------------------------------------------
# State file I/O
# ---------------------------------------------------------------------------
def load_last_synced(agenda: str) -> dict | None:
    """Load the last-synced state for an agenda.

    Returns:
        Parsed JSON dict, or None if no state file exists.
    """
    path = STATE_DIR / f"{agenda}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_synced_state(
    agenda: str,
    sync_type: str,
    events: dict[str, list[dict]],
) -> Path:
    """Write the synced state to disk.

    Args:
        agenda: Agenda key (e.g., "sfs_lausanne").
        sync_type: "method" or "vip".
        events: {upn: [event_with_outlook_id, ...]}.

    Returns:
        Path to the written state file.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "agenda": agenda,
        "sync_type": sync_type,
        "events": events,
    }
    path = STATE_DIR / f"{agenda}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------------
# Method class diff
# ---------------------------------------------------------------------------
def compute_method_diff(
    old_events: dict[str, list[dict]],
    new_schedule: dict[str, list[dict]],
) -> dict:
    """Compare method class schedules (recurring weekly events).

    Identity key: (upn, day, start_time)

    Args:
        old_events: {upn: [{outlook_event_id, day, start, end, subject}, ...]}.
        new_schedule: {upn: [{day, start, end}, ...]} — from schedule file after
                      teacher matching.

    Returns:
        {
            "added": [(upn, slot), ...],
            "removed": [(upn, old_event), ...],
            "changed": [(upn, old_event, new_slot), ...],
            "unchanged_count": int,
        }
    """
    # Build lookup of old events by identity key
    old_by_key: dict[tuple, tuple[str, dict]] = {}
    for upn, events in old_events.items():
        for ev in events:
            key = (upn, ev["day"], ev["start"])
            old_by_key[key] = (upn, ev)

    # Build lookup of new events by identity key
    new_by_key: dict[tuple, tuple[str, dict]] = {}
    for upn, slots in new_schedule.items():
        for slot in slots:
            key = (upn, slot["day"], slot["start"])
            new_by_key[key] = (upn, slot)

    added = []
    removed = []
    changed = []
    unchanged = 0

    # Find removed and changed
    for key, (upn, old_ev) in old_by_key.items():
        if key not in new_by_key:
            removed.append((upn, old_ev))
        else:
            _, new_slot = new_by_key[key]
            # Check if end time changed (day and start are part of the key)
            if old_ev["end"] != new_slot["end"]:
                changed.append((upn, old_ev, new_slot))
            else:
                unchanged += 1

    # Find added
    for key, (upn, new_slot) in new_by_key.items():
        if key not in old_by_key:
            added.append((upn, new_slot))

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": unchanged,
    }


# ---------------------------------------------------------------------------
# VIP diff
# ---------------------------------------------------------------------------
def compute_vip_diff(
    old_events: dict[str, list[dict]],
    new_schedule: dict[str, list[dict]],
) -> dict:
    """Compare VIP schedules (one-time dated events).

    Identity key: (upn, date, start_time, activity_code)

    Args:
        old_events: {upn: [{outlook_event_id, date, start, end, type, subject, ...}, ...]}.
        new_schedule: {upn: [{date, start, end, type, name, online}, ...]} — from
                      schedule file after teacher matching.

    Returns:
        {
            "added": [(upn, slot), ...],
            "removed": [(upn, old_event), ...],
            "changed": [(upn, old_event, new_slot), ...],
            "unchanged_count": int,
        }
    """
    old_by_key: dict[tuple, tuple[str, dict]] = {}
    for upn, events in old_events.items():
        for ev in events:
            key = (upn, ev["date"], ev["start"], ev.get("type", ""))
            old_by_key[key] = (upn, ev)

    new_by_key: dict[tuple, tuple[str, dict]] = {}
    for upn, slots in new_schedule.items():
        for slot in slots:
            key = (upn, slot["date"], slot["start"], slot.get("type", ""))
            new_by_key[key] = (upn, slot)

    added = []
    removed = []
    changed = []
    unchanged = 0

    for key, (upn, old_ev) in old_by_key.items():
        if key not in new_by_key:
            removed.append((upn, old_ev))
        else:
            _, new_slot = new_by_key[key]
            # Check if end time or online flag changed
            if (
                old_ev["end"] != new_slot["end"]
                or old_ev.get("online") != new_slot.get("online")
            ):
                changed.append((upn, old_ev, new_slot))
            else:
                unchanged += 1

    for key, (upn, new_slot) in new_by_key.items():
        if key not in old_by_key:
            added.append((upn, new_slot))

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": unchanged,
    }


# ---------------------------------------------------------------------------
# Apply diff — method classes
# ---------------------------------------------------------------------------
def apply_method_diff(
    token: str,
    diff: dict,
    today: date,
    *,
    build_event_body_fn,
    graph_post_fn,
    graph_delete_fn,
) -> dict:
    """Execute Graph API calls for method class diff.

    Args:
        token: Graph API access token.
        diff: Output from compute_method_diff().
        today: Reference date for recurring event start dates.
        build_event_body_fn: Callable(slot, today) -> event JSON.
        graph_post_fn: Callable(token, endpoint, body) -> response.
        graph_delete_fn: Callable(token, endpoint) -> response.

    Returns:
        {
            "created": int,
            "deleted": int,
            "failed": int,
            "errors": [...],
            "synced_events": {upn: [event_with_id, ...]},
        }
    """
    created = 0
    deleted = 0
    failed = 0
    errors = []
    synced_events: dict[str, list[dict]] = {}

    def _ensure_upn(upn):
        if upn not in synced_events:
            synced_events[upn] = []

    # Delete removed events
    for upn, old_ev in diff["removed"]:
        event_id = old_ev.get("outlook_event_id")
        if not event_id:
            continue
        resp = graph_delete_fn(token, f"/users/{upn}/calendar/events/{event_id}")
        if resp.status_code == 204:
            deleted += 1
        else:
            label = f"{old_ev['day']} {old_ev['start']}-{old_ev['end']}"
            errors.append(f"delete {upn} {label}: {resp.status_code}")
            failed += 1

    # Delete old + create new for changed events
    for upn, old_ev, new_slot in diff["changed"]:
        _ensure_upn(upn)
        # Delete old
        event_id = old_ev.get("outlook_event_id")
        if event_id:
            resp = graph_delete_fn(token, f"/users/{upn}/calendar/events/{event_id}")
            if resp.status_code == 204:
                deleted += 1
            else:
                label = f"{old_ev['day']} {old_ev['start']}-{old_ev['end']}"
                errors.append(f"delete-changed {upn} {label}: {resp.status_code}")
                failed += 1
                continue  # Skip create if delete failed

        # Create new
        body = build_event_body_fn(new_slot, today)
        resp = graph_post_fn(token, f"/users/{upn}/events", body)
        if resp.status_code in (200, 201):
            created += 1
            new_event_id = resp.json().get("id", "")
            synced_events[upn].append({
                "outlook_event_id": new_event_id,
                "day": new_slot["day"],
                "start": new_slot["start"],
                "end": new_slot["end"],
                "subject": body.get("subject", ""),
            })
        else:
            label = f"{new_slot['day']} {new_slot['start']}-{new_slot['end']}"
            errors.append(f"create-changed {upn} {label}: {resp.status_code}")
            failed += 1

    # Create added events
    for upn, new_slot in diff["added"]:
        _ensure_upn(upn)
        body = build_event_body_fn(new_slot, today)
        resp = graph_post_fn(token, f"/users/{upn}/events", body)
        if resp.status_code in (200, 201):
            created += 1
            new_event_id = resp.json().get("id", "")
            synced_events[upn].append({
                "outlook_event_id": new_event_id,
                "day": new_slot["day"],
                "start": new_slot["start"],
                "end": new_slot["end"],
                "subject": body.get("subject", ""),
            })
        else:
            label = f"{new_slot['day']} {new_slot['start']}-{new_slot['end']}"
            errors.append(f"create {upn} {label}: {resp.status_code}")
            failed += 1

    return {
        "created": created,
        "deleted": deleted,
        "failed": failed,
        "errors": errors,
        "synced_events": synced_events,
    }


# ---------------------------------------------------------------------------
# Apply diff — VIP events
# ---------------------------------------------------------------------------
def apply_vip_diff(
    token: str,
    diff: dict,
    *,
    build_event_body_fn,
    get_event_subject_fn,
    graph_post_fn,
    graph_delete_fn,
) -> dict:
    """Execute Graph API calls for VIP diff.

    Args:
        token: Graph API access token.
        diff: Output from compute_vip_diff().
        build_event_body_fn: Callable(slot) -> event JSON.
        get_event_subject_fn: Callable(slot) -> subject string.
        graph_post_fn: Callable(token, endpoint, body) -> response.
        graph_delete_fn: Callable(token, endpoint) -> response.

    Returns:
        {
            "created": int,
            "deleted": int,
            "failed": int,
            "errors": [...],
            "synced_events": {upn: [event_with_id, ...]},
        }
    """
    created = 0
    deleted = 0
    failed = 0
    errors = []
    synced_events: dict[str, list[dict]] = {}

    def _ensure_upn(upn):
        if upn not in synced_events:
            synced_events[upn] = []

    # Delete removed events
    for upn, old_ev in diff["removed"]:
        event_id = old_ev.get("outlook_event_id")
        if not event_id:
            continue
        resp = graph_delete_fn(token, f"/users/{upn}/calendar/events/{event_id}")
        if resp.status_code == 204:
            deleted += 1
        else:
            label = f"{old_ev['date']} {old_ev['start']}-{old_ev['end']} {old_ev.get('type', '')}"
            errors.append(f"delete {upn} {label}: {resp.status_code}")
            failed += 1

    # Delete old + create new for changed events
    for upn, old_ev, new_slot in diff["changed"]:
        _ensure_upn(upn)
        event_id = old_ev.get("outlook_event_id")
        if event_id:
            resp = graph_delete_fn(token, f"/users/{upn}/calendar/events/{event_id}")
            if resp.status_code == 204:
                deleted += 1
            else:
                label = f"{old_ev['date']} {old_ev['start']}"
                errors.append(f"delete-changed {upn} {label}: {resp.status_code}")
                failed += 1
                continue

        body = build_event_body_fn(new_slot)
        resp = graph_post_fn(token, f"/users/{upn}/events", body)
        if resp.status_code in (200, 201):
            created += 1
            new_event_id = resp.json().get("id", "")
            synced_events[upn].append({
                "outlook_event_id": new_event_id,
                "date": new_slot["date"],
                "start": new_slot["start"],
                "end": new_slot["end"],
                "type": new_slot.get("type", ""),
                "subject": get_event_subject_fn(new_slot),
                "online": new_slot.get("online", False),
            })
        else:
            label = f"{new_slot['date']} {new_slot['start']}-{new_slot['end']} {new_slot.get('type', '')}"
            errors.append(f"create-changed {upn} {label}: {resp.status_code}")
            failed += 1

    # Create added events
    for upn, new_slot in diff["added"]:
        _ensure_upn(upn)
        body = build_event_body_fn(new_slot)
        resp = graph_post_fn(token, f"/users/{upn}/events", body)
        if resp.status_code in (200, 201):
            created += 1
            new_event_id = resp.json().get("id", "")
            synced_events[upn].append({
                "outlook_event_id": new_event_id,
                "date": new_slot["date"],
                "start": new_slot["start"],
                "end": new_slot["end"],
                "type": new_slot.get("type", ""),
                "subject": get_event_subject_fn(new_slot),
                "online": new_slot.get("online", False),
            })
        else:
            label = f"{new_slot['date']} {new_slot['start']}-{new_slot['end']} {new_slot.get('type', '')}"
            errors.append(f"create {upn} {label}: {resp.status_code}")
            failed += 1

    return {
        "created": created,
        "deleted": deleted,
        "failed": failed,
        "errors": errors,
        "synced_events": synced_events,
    }


# ---------------------------------------------------------------------------
# Merge synced events (unchanged + new from diff application)
# ---------------------------------------------------------------------------
def merge_synced_events(
    old_events: dict[str, list[dict]],
    diff: dict,
    applied_events: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Merge unchanged events from old state with newly created events.

    After applying a diff, the new state = unchanged old events + created events.
    Removed events are excluded. Changed events have new entries from applied_events.

    Args:
        old_events: Previous state's events dict.
        diff: The diff that was applied (to identify removed/changed keys).
        applied_events: {upn: [event_with_id, ...]} from apply_*_diff().

    Returns:
        Merged events dict ready for save_synced_state().
    """
    # Collect keys of removed and changed events (to exclude from old)
    removed_ids = set()
    for _, old_ev in diff["removed"]:
        eid = old_ev.get("outlook_event_id")
        if eid:
            removed_ids.add(eid)
    for _, old_ev, _ in diff["changed"]:
        eid = old_ev.get("outlook_event_id")
        if eid:
            removed_ids.add(eid)

    # Start with unchanged old events
    merged: dict[str, list[dict]] = {}
    for upn, events in old_events.items():
        kept = [ev for ev in events if ev.get("outlook_event_id") not in removed_ids]
        if kept:
            merged[upn] = kept

    # Add new/changed events from applied_events
    for upn, events in applied_events.items():
        if upn not in merged:
            merged[upn] = []
        merged[upn].extend(events)

    return merged


# ---------------------------------------------------------------------------
# Diff summary formatting
# ---------------------------------------------------------------------------
def format_diff_summary(diff: dict) -> str:
    """Format a diff for human-readable display."""
    lines = []
    lines.append(
        f"  Added: {len(diff['added'])}  |  "
        f"Removed: {len(diff['removed'])}  |  "
        f"Changed: {len(diff['changed'])}  |  "
        f"Unchanged: {diff['unchanged_count']}"
    )

    if diff["added"]:
        lines.append("  New:")
        for upn, slot in diff["added"][:10]:
            user = upn.split("@")[0]
            if "day" in slot:
                lines.append(f"    + {user}: {slot['day']} {slot['start']}-{slot['end']}")
            else:
                lines.append(f"    + {user}: {slot['date']} {slot['start']}-{slot['end']} {slot.get('type', '')}")
        if len(diff["added"]) > 10:
            lines.append(f"    ... and {len(diff['added']) - 10} more")

    if diff["removed"]:
        lines.append("  Removed:")
        for upn, old_ev in diff["removed"][:10]:
            user = upn.split("@")[0]
            if "day" in old_ev:
                lines.append(f"    - {user}: {old_ev['day']} {old_ev['start']}-{old_ev['end']}")
            else:
                lines.append(f"    - {user}: {old_ev['date']} {old_ev['start']}-{old_ev['end']} {old_ev.get('type', '')}")
        if len(diff["removed"]) > 10:
            lines.append(f"    ... and {len(diff['removed']) - 10} more")

    if diff["changed"]:
        lines.append("  Changed:")
        for upn, old_ev, new_slot in diff["changed"][:10]:
            user = upn.split("@")[0]
            if "day" in old_ev:
                lines.append(f"    ~ {user}: {old_ev['day']} {old_ev['start']}-{old_ev['end']} -> {new_slot['end']}")
            else:
                lines.append(f"    ~ {user}: {old_ev['date']} {old_ev['start']} end:{old_ev['end']}->{new_slot['end']}")
        if len(diff["changed"]) > 10:
            lines.append(f"    ... and {len(diff['changed']) - 10} more")

    return "\n".join(lines)
