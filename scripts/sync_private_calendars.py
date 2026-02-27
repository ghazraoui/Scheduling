"""
Sync private/VIP lesson schedules to teachers' Outlook calendars as one-time events.

Reads detailed schedule JSONs (with dates, activity types, online flags),
matches teachers to their M365 accounts, and creates single-occurrence events
with type-specific subjects and color categories.

V2: Uses diff-based sync — only creates/deletes/updates what changed.
State tracked in data/last_synced/{agenda}.json.

Usage:
    python scripts/sync_private_calendars.py              # dry-run (default, all agendas)
    python scripts/sync_private_calendars.py --execute    # diff-sync all agendas
    python scripts/sync_private_calendars.py --clear-only # just remove existing private events
    python scripts/sync_private_calendars.py --agenda private_english_lausanne              # single agenda
    python scripts/sync_private_calendars.py --agenda private_english_lausanne --execute    # single agenda diff-sync

Pre-requisites:
    - App registration must have Calendars.ReadWrite (application) permission
    - Admin consent must be granted
    - data/teachers.json must exist
    - data/teacher-schedule-*-detailed.json must exist
"""

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding for accented characters (guard against double-wrap)
if sys.platform == "win32" and not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    DOMAIN,
    get_token,
    graph_delete,
    graph_get,
    graph_get_all,
    graph_post,
)
from diff_sync import (
    apply_vip_diff,
    compute_vip_diff,
    format_diff_summary,
    load_last_synced,
    merge_synced_events,
    save_synced_state,
)

# Reuse name-matching logic from the recurring sync script
from sync_calendars import (
    build_teacher_lookup,
    clean_sparksource_name,
    match_teacher,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

ALL_PRIVATE_AGENDAS = [
    "private_english_lausanne",
    "private_french_lausanne",
    "private_german_lausanne",
]
TEACHERS_FILE = DATA_DIR / "teachers.json"

# ---------------------------------------------------------------------------
# Event subject prefix — distinct from "Teaching" so we don't touch method events
# ---------------------------------------------------------------------------
PRIVATE_EVENT_PREFIX = "Private:"

# ---------------------------------------------------------------------------
# Activity type config: subject labels and Outlook category colors
# ---------------------------------------------------------------------------
# Outlook preset colors (from Graph API outlookCategory resource):
#   preset0=Red, preset1=Orange, preset2=Brown, preset3=Yellow,
#   preset4=Green, preset5=Teal, preset6=Olive, preset7=Blue,
#   preset8=Purple, preset9=Cranberry, preset10=Steel, preset11=DarkSteel

ACTIVITY_TYPES = {
    "VAD": {
        "label": "VIP Adults",
        "color": "preset8",       # Purple (matches SparkSource pink/magenta)
    },
    "TPC": {
        "label": "Test Prep",
        "color": "preset0",       # Red (matches SparkSource red/salmon)
    },
    "JPR": {
        "label": "Junior Private",
        "color": "preset7",       # Blue (matches SparkSource blue/lavender)
    },
    "JGP": {
        "label": "Junior Group",
        "color": "preset4",       # Green (matches SparkSource green)
    },
    "ICO": {
        "label": "In Company",
        "color": "preset1",       # Orange (matches SparkSource orange/gold)
    },
    "VIP": {
        "label": "VIP Class",
        "color": "preset3",       # Yellow (matches SparkSource yellow)
    },
}

# Fallback for unknown activity codes
DEFAULT_ACTIVITY = {"label": "Private Lesson", "color": "preset10"}  # Steel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_event_subject(slot):
    """Build the event subject line from a detailed slot.

    Format: "Private: VAD - VIP Adults" or "Private: VAD - VIP Adults (Online)"
    """
    code = slot.get("type", "")
    info = ACTIVITY_TYPES.get(code, DEFAULT_ACTIVITY)
    subject = f"{PRIVATE_EVENT_PREFIX} {code} - {info['label']}"
    if slot.get("online"):
        subject += " (Online)"
    return subject


def get_category_name(slot):
    """Get the Outlook category name for this slot's activity type."""
    code = slot.get("type", "")
    info = ACTIVITY_TYPES.get(code, DEFAULT_ACTIVITY)
    return f"{code} - {info['label']}" if code else "Private Lesson"


def build_private_event_body(slot):
    """Build the Graph API event JSON for a one-time private lesson."""
    code = slot.get("type", "")
    info = ACTIVITY_TYPES.get(code, DEFAULT_ACTIVITY)
    category = get_category_name(slot)

    return {
        "subject": get_event_subject(slot),
        "start": {
            "dateTime": f"{slot['date']}T{slot['start']}:00",
            "timeZone": "Europe/Zurich",
        },
        "end": {
            "dateTime": f"{slot['date']}T{slot['end']}:00",
            "timeZone": "Europe/Zurich",
        },
        "showAs": "busy",
        "isReminderOn": False,
        "categories": [category],
    }


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def _schedule_file_for_agenda(agenda: str) -> Path:
    """Return the detailed schedule file path for a given agenda key."""
    return DATA_DIR / f"teacher-schedule-{agenda}-detailed.json"


def load_detailed_schedule(agenda: str) -> dict:
    """Load a single detailed schedule JSON for one agenda."""
    path = _schedule_file_for_agenda(agenda)
    if not path.exists():
        print(f"  WARNING: {path} not found")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_and_merge_detailed_schedules(agendas: list[str] | None = None) -> dict:
    """Load detailed schedule JSONs and merge by teacher name.

    Deduplicates on (teacher, date, start, end, type, online).
    """
    if agendas is None:
        agendas = ALL_PRIVATE_AGENDAS
    merged = {}
    for agenda in agendas:
        path = _schedule_file_for_agenda(agenda)
        if not path.exists():
            print(f"  WARNING: {path} not found, skipping")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for name, slots in data.items():
            if name not in merged:
                merged[name] = list(slots)
            else:
                existing = {
                    (s["date"], s["start"], s["end"], s["type"], s["online"])
                    for s in merged[name]
                }
                for slot in slots:
                    key = (slot["date"], slot["start"], slot["end"],
                           slot["type"], slot["online"])
                    if key not in existing:
                        merged[name].append(slot)
                        existing.add(key)
    return merged


def match_all_teachers(merged_schedules, teachers):
    """Match SparkSource names to provisioned teachers.

    Returns: (matched, unmatched, skipped)
        matched: list of (display_name, upn, slots)
    """
    exact_lookup, fuzzy_lookup = build_teacher_lookup(teachers)

    matched = []
    unmatched = []
    skipped = []
    seen_upns = {}

    for raw_name, slots in merged_schedules.items():
        parsed = clean_sparksource_name(raw_name)
        if not parsed:
            unmatched.append(raw_name)
            continue

        firstname, lastname = parsed
        result, method = match_teacher(firstname, lastname, exact_lookup, fuzzy_lookup)

        if method == "skipped":
            skipped.append(raw_name)
            continue

        if result is None:
            unmatched.append(raw_name)
            continue

        display_name, upn = result

        # Merge slots if same teacher already matched
        if upn in seen_upns:
            idx = seen_upns[upn]
            existing_keys = {
                (s["date"], s["start"], s["end"], s["type"], s["online"])
                for s in matched[idx][2]
            }
            for slot in slots:
                key = (slot["date"], slot["start"], slot["end"],
                       slot["type"], slot["online"])
                if key not in existing_keys:
                    matched[idx][2].append(slot)
                    existing_keys.add(key)
            print(f"  [  merged] {raw_name:<35} -> {display_name} (added to existing)")
            continue

        seen_upns[upn] = len(matched)
        matched.append((display_name, upn, list(slots)))
        print(f"  [{method:>8}] {raw_name:<35} -> {display_name} ({upn})")

    return matched, unmatched, skipped


def ensure_categories(token, upn):
    """Ensure all activity type categories exist on the teacher's mailbox.

    Creates missing categories with the correct color. Idempotent.
    """
    # Fetch existing categories
    resp = graph_get(token, f"/users/{upn}/outlook/masterCategories")
    if "error" in resp:
        print(f"    WARNING: Could not read categories for {upn}: {resp}")
        return

    existing = {cat["displayName"] for cat in resp.get("value", [])}

    for code, info in ACTIVITY_TYPES.items():
        cat_name = f"{code} - {info['label']}"
        if cat_name in existing:
            continue
        body = {"displayName": cat_name, "color": info["color"]}
        r = graph_post(token, f"/users/{upn}/outlook/masterCategories", body)
        if r.status_code in (200, 201):
            print(f"    Created category: {cat_name}")
        else:
            print(f"    WARNING: Failed to create category {cat_name}: {r.status_code}")


def clear_private_events(token, upn):
    """Delete all events whose subject starts with PRIVATE_EVENT_PREFIX.

    Does NOT touch recurring "Teaching" events from method sync.
    Returns (count, errors).
    """
    endpoint = (
        f"/users/{upn}/calendar/events"
        f"?$filter=startsWith(subject,'{PRIVATE_EVENT_PREFIX}')"
        f"&$select=id,subject&$top=100"
    )
    result = graph_get_all(token, endpoint)

    if "error" in result:
        print(f"    ERROR listing events: {result}")
        return 0, [f"list: {result}"]

    events = result.get("value", [])
    cleared = 0
    errors = []
    for ev in events:
        resp = graph_delete(token, f"/users/{upn}/calendar/events/{ev['id']}")
        if resp.status_code == 204:
            cleared += 1
        else:
            errors.append(f"delete {ev['id']}: {resp.status_code}")
    return cleared, errors


def create_private_events(token, upn, slots):
    """Create one-time events for each slot.

    Returns (created, failed, errors, created_events) where created_events
    is a list of dicts with outlook_event_id for state tracking.
    """
    created = 0
    failed = 0
    errors = []
    created_events = []
    for slot in slots:
        body = build_private_event_body(slot)
        resp = graph_post(token, f"/users/{upn}/events", body)
        if resp.status_code in (200, 201):
            created += 1
            event_id = resp.json().get("id", "")
            created_events.append({
                "outlook_event_id": event_id,
                "date": slot["date"],
                "start": slot["start"],
                "end": slot["end"],
                "type": slot.get("type", ""),
                "subject": get_event_subject(slot),
                "online": slot.get("online", False),
            })
        else:
            label = f"{slot['date']} {slot['start']}-{slot['end']} {slot['type']}"
            errors.append(f"create {label}: {resp.status_code} {resp.text[:200]}")
            print(f"    FAILED: {label} -- {resp.status_code}")
            failed += 1
    return created, failed, errors, created_events


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Sync private/VIP lesson schedules to Outlook calendars"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--execute", action="store_true",
        help="Diff-sync: only create/delete what changed (or full sync on first run)",
    )
    group.add_argument(
        "--clear-only", action="store_true",
        help="Only remove existing private lesson events (no creation)",
    )
    parser.add_argument(
        "--agenda", type=str, default=None,
        help="Single agenda to sync (e.g., private_english_lausanne). Default: all private agendas.",
    )
    args = parser.parse_args()

    mode = "execute" if args.execute else ("clear-only" if args.clear_only else "dry-run")
    agendas = [args.agenda] if args.agenda else ALL_PRIVATE_AGENDAS

    print("=" * 60)
    print(f"PRIVATE CALENDAR SYNC [{mode.upper()}]")
    print(f"Agendas: {', '.join(agendas)}")
    print("=" * 60)

    # 1. Load detailed schedules
    merged = load_and_merge_detailed_schedules(agendas)
    total_slots = sum(len(s) for s in merged.values())
    print(f"Loaded {total_slots} classes for {len(merged)} SparkSource teachers\n")

    # Type breakdown
    type_counts = {}
    for slots in merged.values():
        for s in slots:
            code = s.get("type", "?")
            type_counts[code] = type_counts.get(code, 0) + 1
    print("Class types:")
    for code, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        info = ACTIVITY_TYPES.get(code, DEFAULT_ACTIVITY)
        print(f"  {code:>4}: {count:>3} ({info['label']})")
    print()

    # 2. Load teachers and match
    with open(TEACHERS_FILE, encoding="utf-8") as f:
        teachers = json.load(f)

    print("Matching names:")
    matched, unmatched, skipped = match_all_teachers(merged, teachers)

    print(f"\nMatched: {len(matched)}  |  Skipped: {len(skipped)}  |  Unmatched: {len(unmatched)}")
    if skipped:
        print(f"  Skipped: {', '.join(skipped)}")
    if unmatched:
        print(f"  Unmatched: {', '.join(unmatched)}")

    matched_slots = sum(len(m[2]) for m in matched)
    print(f"  Total events to sync: {matched_slots}\n")

    # Build new schedule keyed by UPN (for diff comparison)
    new_schedule_by_upn: dict[str, list[dict]] = {}
    for display_name, upn, slots in matched:
        new_schedule_by_upn[upn] = slots

    # State key — single agenda or "all_private"
    state_agenda = args.agenda if args.agenda else "all_private"

    # 3. Dry-run: show diff preview or full list
    if mode == "dry-run":
        last_synced = load_last_synced(state_agenda)
        if last_synced:
            old_events = last_synced.get("events", {})
            diff = compute_vip_diff(old_events, new_schedule_by_upn)
            print("--- DRY RUN (diff preview) ---\n")
            print(format_diff_summary(diff))
        else:
            print("--- DRY RUN (no previous state — would do full sync) ---\n")
            for display_name, upn, slots in matched:
                by_type = {}
                for s in slots:
                    code = s.get("type", "?")
                    by_type[code] = by_type.get(code, 0) + 1
                type_str = ", ".join(f"{c}:{n}" for c, n in sorted(by_type.items()))
                print(f"  {display_name} ({len(slots)} events): {type_str}")
        print("\nRun with --execute to create events, or --clear-only to remove them.")
        return

    # 4. Authenticate
    print("Authenticating...")
    token = get_token()
    print("OK\n")

    if mode == "clear-only":
        total_cleared = 0
        for display_name, upn, slots in matched:
            print(f"  {display_name}: clearing old private events...")
            cleared, errors = clear_private_events(token, upn)
            if cleared:
                print(f"    Cleared {cleared}")
            total_cleared += cleared
        print(f"\nTotal cleared: {total_cleared}")
        return

    # 5. Execute: diff-based sync
    last_synced = load_last_synced(state_agenda)

    # Ensure categories exist for all matched teachers
    categories_done = set()
    for display_name, upn, slots in matched:
        if upn not in categories_done:
            ensure_categories(token, upn)
            categories_done.add(upn)

    if last_synced is None:
        # First run — clear existing events and do full create, saving state
        print("First run (no state file) — full clear + create\n")
        all_synced_events: dict[str, list[dict]] = {}
        total_cleared = 0
        total_created = 0
        total_failed = 0

        for display_name, upn, slots in matched:
            # Clear existing
            print(f"  {display_name}: clearing old private events...")
            cleared, errors = clear_private_events(token, upn)
            total_cleared += cleared
            if cleared:
                print(f"    Cleared {cleared}")

            # Create new
            print(f"  {display_name}: creating {len(slots)} events...")
            created, failed, errors, created_events = create_private_events(
                token, upn, slots
            )
            total_created += created
            total_failed += failed
            print(f"    Created {created}" + (f", {failed} failed" if failed else ""))

            if created_events:
                all_synced_events[upn] = created_events

        # Save state
        state_path = save_synced_state(state_agenda, "vip", all_synced_events)
        print(f"\nState saved: {state_path}")
        print(f"Cleared: {total_cleared}  |  Created: {total_created}  |  Failed: {total_failed}")
    else:
        # Subsequent run — compute diff and apply
        old_events = last_synced.get("events", {})
        diff = compute_vip_diff(old_events, new_schedule_by_upn)

        print("Diff computed:")
        print(format_diff_summary(diff))
        print()

        if not diff["added"] and not diff["removed"] and not diff["changed"]:
            print("No changes — calendars are up to date.")
            return

        # Apply diff
        print("Applying diff...")
        result = apply_vip_diff(
            token, diff,
            build_event_body_fn=build_private_event_body,
            get_event_subject_fn=get_event_subject,
            graph_post_fn=graph_post,
            graph_delete_fn=graph_delete,
        )

        # Merge unchanged events with newly created ones
        new_state = merge_synced_events(old_events, diff, result["synced_events"])
        state_path = save_synced_state(state_agenda, "vip", new_state)

        print(f"\nCreated: {result['created']}  |  Deleted: {result['deleted']}  |  Failed: {result['failed']}")
        if result["errors"]:
            print("Errors:")
            for err in result["errors"]:
                print(f"  {err}")
        print(f"State saved: {state_path}")

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = REPORTS_DIR / f"private_calendar_sync_{ts}.json"
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "agendas": agendas,
        "teachers_matched": len(matched),
        "teachers_unmatched": len(unmatched),
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
