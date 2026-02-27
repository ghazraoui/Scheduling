"""
Sync private/VIP lesson schedules to teachers' Outlook calendars as one-time events.

Reads detailed schedule JSONs (with dates, activity types, online flags),
matches teachers to their M365 accounts, and creates single-occurrence events
with type-specific subjects and color categories.

Unlike sync_calendars.py (which creates recurring weekly "Teaching" events for
method classes), this script creates one-time events because private lessons
vary week to week.

Usage:
    python scripts/sync_private_calendars.py              # dry-run (default)
    python scripts/sync_private_calendars.py --execute    # clear old + create events
    python scripts/sync_private_calendars.py --clear-only # just remove existing private events

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

DETAILED_SCHEDULE_FILES = [
    DATA_DIR / "teacher-schedule-private_english_lausanne-detailed.json",
    DATA_DIR / "teacher-schedule-private_french_lausanne-detailed.json",
    DATA_DIR / "teacher-schedule-private_german_lausanne-detailed.json",
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
def load_detailed_schedules():
    """Load all detailed schedule JSONs and merge by teacher name.

    Deduplicates on (teacher, date, start, end, type, online).
    """
    merged = {}
    for path in DETAILED_SCHEDULE_FILES:
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
    """Create one-time events for each slot. Returns (created, failed, errors)."""
    created = 0
    failed = 0
    errors = []
    for slot in slots:
        body = build_private_event_body(slot)
        resp = graph_post(token, f"/users/{upn}/events", body)
        if resp.status_code in (200, 201):
            created += 1
        else:
            label = f"{slot['date']} {slot['start']}-{slot['end']} {slot['type']}"
            errors.append(f"create {label}: {resp.status_code} {resp.text[:200]}")
            print(f"    FAILED: {label} -- {resp.status_code}")
            failed += 1
    return created, failed, errors


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
        help="Clear old private events and create new one-time events",
    )
    group.add_argument(
        "--clear-only", action="store_true",
        help="Only remove existing private lesson events (no creation)",
    )
    args = parser.parse_args()

    mode = "execute" if args.execute else ("clear-only" if args.clear_only else "dry-run")

    print("=" * 60)
    print(f"PRIVATE CALENDAR SYNC [{mode.upper()}]")
    print("=" * 60)

    # 1. Load detailed schedules
    merged = load_detailed_schedules()
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

    # 3. Dry-run: just print what would happen
    if mode == "dry-run":
        print("--- DRY RUN -- no API calls ---\n")
        for display_name, upn, slots in matched:
            # Group by type for display
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

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "summary": {
            "teachers_matched": len(matched),
            "teachers_unmatched": len(unmatched),
            "events_cleared": 0,
            "events_created": 0,
            "events_failed": 0,
        },
        "actions": [],
        "unmatched": unmatched,
        "skipped": skipped,
    }

    for display_name, upn, slots in matched:
        action = {
            "teacher": display_name,
            "upn": upn,
            "events_cleared": 0,
            "events_created": 0,
            "events_failed": 0,
            "slot_count": len(slots),
            "errors": [],
        }

        # Ensure color categories exist on this teacher's mailbox
        print(f"  {display_name}: setting up categories...")
        ensure_categories(token, upn)

        # Clear existing private events
        print(f"  {display_name}: clearing old private events...")
        cleared, errors = clear_private_events(token, upn)
        action["events_cleared"] = cleared
        action["errors"].extend(errors)
        if cleared:
            print(f"    Cleared {cleared}")
        report["summary"]["events_cleared"] += cleared

        if mode == "clear-only":
            report["actions"].append(action)
            continue

        # Create new one-time events
        print(f"  {display_name}: creating {len(slots)} events...")
        created, failed, errors = create_private_events(token, upn, slots)
        action["events_created"] = created
        action["events_failed"] = failed
        action["errors"].extend(errors)
        print(f"    Created {created}" + (f", {failed} failed" if failed else ""))

        report["summary"]["events_created"] += created
        report["summary"]["events_failed"] += failed
        report["actions"].append(action)

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = REPORTS_DIR / f"private_calendar_sync_{ts}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    s = report["summary"]
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Cleared:  {s['events_cleared']}")
    print(f"  Created:  {s['events_created']}")
    print(f"  Failed:   {s['events_failed']}")
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
