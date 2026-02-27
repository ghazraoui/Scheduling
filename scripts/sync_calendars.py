"""
Sync teacher teaching schedules to their Outlook calendars as recurring busy events.

Reads SparkSource schedule JSONs, matches teachers to their M365 accounts,
and creates weekly recurring "Teaching" events so free/busy queries work.

Usage:
    python scripts/sync_calendars.py              # dry-run (default)
    python scripts/sync_calendars.py --execute    # clear old + create events
    python scripts/sync_calendars.py --clear-only # just remove existing Teaching events

Pre-requisites:
    - App registration must have Calendars.ReadWrite (application) permission
    - Admin consent must be granted
    - data/teachers.json must exist
    - data/teacher-schedule-*.json must exist
"""

import argparse
import io
import json
import os
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Fix Windows console encoding for accented characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    CALENDAR_EVENT_SUBJECT,
    DOMAIN,
    get_token,
    graph_delete,
    graph_get_all,
    graph_post,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

SCHEDULE_FILES = [
    DATA_DIR / "teacher-schedule-sfs_lausanne.json",
    DATA_DIR / "teacher-schedule-esa_lausanne.json",
]
TEACHERS_FILE = DATA_DIR / "teachers.json"

# ---------------------------------------------------------------------------
# Name matching constants
# ---------------------------------------------------------------------------
# Tokens to strip from SparkSource names (school prefixes / suffixes / class types)
# These appear as standalone words or slash-separated (e.g. "VIP/TP")
STRIP_TOKENS = {
    "MAIN", "CR",                           # role suffixes
    "ESA", "SFS", "WSE",                    # school prefixes
    "VIP", "TP", "VAD", "TPC",             # private class type annotations
    "JPR", "JGP", "JNR", "ICO",            # junior / in-company annotations
}

# Hardcoded overrides: cleaned SparkSource name -> teachers.json name
# (Empty after name corrections on 2026-02-24 — all names now match directly)
NAME_OVERRIDES = {}

# Teachers in SparkSource but not provisioned — skip silently
SKIP_NAMES = set()

# Weekday name -> Python weekday number (0=Monday)
DAY_INDEX = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2,
    "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6,
}

# Python weekday number -> Graph API daysOfWeek value
GRAPH_DAY = {
    0: "monday", 1: "tuesday", 2: "wednesday",
    3: "thursday", 4: "friday", 5: "saturday", 6: "sunday",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def strip_accents(text):
    """Remove accents/diacritics (e.g. e -> e, u -> u)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def make_upn(firstname, lastname):
    """Replicate the UPN generation logic from provision_teachers.py."""
    fn = strip_accents(firstname).lower().replace(" ", "").replace("-", "")
    ln = strip_accents(lastname).lower().replace(" ", ".").replace("-", "")
    fn = "".join(c for c in fn if c.isalnum())
    ln = "".join(c for c in ln if c.isalnum() or c == ".")
    return f"{fn}.{ln}@{DOMAIN}"


def clean_sparksource_name(raw_name):
    """Parse a SparkSource schedule key into (firstname, lastname) title-case.

    Strips known tokens (MAIN, CR, ESA, SFS, WSE, VIP, TP, etc.) and
    normalises case. Handles slash-separated tokens like "VIP/TP" by
    splitting them before filtering.

    Returns None if the name can't be parsed into at least two parts.
    """
    # Split on whitespace, then expand slash-separated tokens
    # e.g. "Emily VIP/TP TAYLOR" -> ["Emily", "VIP", "TP", "TAYLOR"]
    raw_parts = raw_name.strip().split()
    parts = []
    for p in raw_parts:
        if "/" in p:
            parts.extend(p.split("/"))
        else:
            parts.append(p)

    cleaned = [p for p in parts if p.upper() not in STRIP_TOKENS]
    if len(cleaned) < 2:
        return None
    # SparkSource format is "Firstname LASTNAME" — title-case everything
    firstname = cleaned[0]
    lastname = " ".join(cleaned[1:])
    # Preserve original capitalisation for mixed-case first names (e.g. Naima)
    # but title-case ALL-CAPS last names
    if firstname.isupper():
        firstname = firstname.title()
    if lastname.isupper():
        lastname = lastname.title()
    return firstname, lastname


def build_teacher_lookup(teachers):
    """Build lookup dicts from teachers.json.

    Returns:
        exact: {accent_stripped_lower_name: (display_name, upn)}
        fuzzy: {first3_last4_key: (display_name, upn)}
    """
    exact = {}
    fuzzy = {}
    for t in teachers:
        fn, ln = t["firstname"], t["lastname"]
        display = f"{fn} {ln}"
        upn = make_upn(fn, ln)
        key = strip_accents(f"{fn} {ln}").lower()
        exact[key] = (display, upn)
        # Fuzzy key: first 3 chars of firstname + first 4 chars of lastname (accent-stripped, lower)
        fk = strip_accents(fn)[:3].lower() + "_" + strip_accents(ln)[:4].lower()
        fuzzy[fk] = (display, upn)
    return exact, fuzzy


def match_teacher(firstname, lastname, exact_lookup, fuzzy_lookup):
    """Try to match a cleaned SparkSource name to a provisioned teacher.

    Returns: ((display_name, upn), match_method) or (None, reason)
    """
    full = f"{firstname} {lastname}"
    norm = strip_accents(full).lower()

    # Skip list
    if norm in {strip_accents(n).lower() for n in SKIP_NAMES}:
        return None, "skipped"

    # Hardcoded overrides (compared accent-stripped)
    for src, dst in NAME_OVERRIDES.items():
        if strip_accents(src).lower() == norm:
            result = exact_lookup.get(strip_accents(dst).lower())
            if result:
                return result, "override"

    # Exact match
    result = exact_lookup.get(norm)
    if result:
        return result, "exact"

    # Fuzzy: first 3 chars of firstname + first 4 chars of lastname
    fk = strip_accents(firstname)[:3].lower() + "_" + strip_accents(lastname)[:4].lower()
    result = fuzzy_lookup.get(fk)
    if result:
        return result, "fuzzy"

    return None, "unmatched"


def next_weekday(target, from_date=None):
    """Return the next occurrence of *target* weekday (0=Mon) from *from_date* inclusive."""
    if from_date is None:
        from_date = date.today()
    days_ahead = (target - from_date.weekday()) % 7
    return from_date + timedelta(days=days_ahead)


def build_event_body(slot, today):
    """Build the Graph API event JSON for one recurring teaching slot."""
    weekday_num = DAY_INDEX[slot["day"]]
    start_date = next_weekday(weekday_num, today)

    return {
        "subject": CALENDAR_EVENT_SUBJECT,
        "start": {
            "dateTime": f"{start_date}T{slot['start']}:00",
            "timeZone": "Europe/Zurich",
        },
        "end": {
            "dateTime": f"{start_date}T{slot['end']}:00",
            "timeZone": "Europe/Zurich",
        },
        "showAs": "busy",
        "isReminderOn": False,
        "recurrence": {
            "pattern": {
                "type": "weekly",
                "interval": 1,
                "daysOfWeek": [GRAPH_DAY[weekday_num]],
                "firstDayOfWeek": "monday",
            },
            "range": {
                "type": "noEnd",
                "startDate": str(start_date),
                "recurrenceTimeZone": "Europe/Zurich",
            },
        },
    }


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def load_and_merge_schedules():
    """Load all schedule JSONs and merge into one dict, deduplicating slots."""
    merged = {}
    for path in SCHEDULE_FILES:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for name, slots in data.items():
            if name not in merged:
                merged[name] = list(slots)
            else:
                existing = {(s["day"], s["start"], s["end"]) for s in merged[name]}
                for slot in slots:
                    key = (slot["day"], slot["start"], slot["end"])
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

    matched = []       # (display_name, upn, slots)
    unmatched = []     # raw_name
    skipped = []       # raw_name
    seen_upns = {}     # upn -> index in matched (to merge Sophie PARE)

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

        # Merge slots if same teacher already matched (e.g. Sophie PARE in SFS + ESA)
        if upn in seen_upns:
            idx = seen_upns[upn]
            existing_keys = {(s["day"], s["start"], s["end"]) for s in matched[idx][2]}
            for slot in slots:
                key = (slot["day"], slot["start"], slot["end"])
                if key not in existing_keys:
                    matched[idx][2].append(slot)
                    existing_keys.add(key)
            print(f"  [  merged] {raw_name:<35} -> {display_name} (added to existing)")
            continue

        seen_upns[upn] = len(matched)
        matched.append((display_name, upn, list(slots)))
        print(f"  [{method:>8}] {raw_name:<35} -> {display_name} ({upn})")

    return matched, unmatched, skipped


def clear_teaching_events(token, upn):
    """Delete all events whose subject starts with CALENDAR_EVENT_SUBJECT. Returns count."""
    endpoint = (
        f"/users/{upn}/calendar/events"
        f"?$filter=startsWith(subject,'{CALENDAR_EVENT_SUBJECT}')"
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


def create_teaching_events(token, upn, slots, today):
    """Create recurring events for each slot. Returns (created, failed, errors)."""
    created = 0
    failed = 0
    errors = []
    for slot in slots:
        body = build_event_body(slot, today)
        resp = graph_post(token, f"/users/{upn}/events", body)
        if resp.status_code in (200, 201):
            created += 1
        else:
            failed += 1
            label = f"{slot['day']} {slot['start']}-{slot['end']}"
            errors.append(f"create {label}: {resp.status_code} {resp.text[:200]}")
            print(f"    FAILED: {label} -- {resp.status_code}")
    return created, failed, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Sync teacher schedules to Outlook calendars"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--execute", action="store_true",
        help="Clear old events and create new recurring events",
    )
    group.add_argument(
        "--clear-only", action="store_true",
        help="Only remove existing Teaching events (no creation)",
    )
    args = parser.parse_args()

    mode = "execute" if args.execute else ("clear-only" if args.clear_only else "dry-run")

    print("=" * 60)
    print(f"CALENDAR SYNC [{mode.upper()}]")
    print("=" * 60)

    # 1. Load and merge schedules
    merged = load_and_merge_schedules()
    total_slots = sum(len(s) for s in merged.values())
    print(f"Loaded {total_slots} slots for {len(merged)} SparkSource teachers\n")

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
    print(f"  Total slots to sync: {matched_slots}\n")

    # 3. Dry-run: just print what would happen
    if mode == "dry-run":
        print("--- DRY RUN -- no API calls ---\n")
        for display_name, upn, slots in matched:
            labels = [f"{s['day'][:3]} {s['start']}-{s['end']}" for s in slots]
            print(f"  {display_name} ({len(slots)} events): {', '.join(labels)}")
        print("\nRun with --execute to create events, or --clear-only to remove them.")
        return

    # 4. Authenticate
    print("Authenticating...")
    token = get_token()
    print("OK\n")

    today = date.today()

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
            "slots": [f"{s['day'][:3]} {s['start']}-{s['end']}" for s in slots],
            "errors": [],
        }

        # Clear existing Teaching events
        print(f"  {display_name}: clearing old events...")
        cleared, errors = clear_teaching_events(token, upn)
        action["events_cleared"] = cleared
        action["errors"].extend(errors)
        print(f"    Cleared {cleared}")
        report["summary"]["events_cleared"] += cleared

        if mode == "clear-only":
            report["actions"].append(action)
            continue

        # Create new recurring events
        print(f"  {display_name}: creating {len(slots)} events...")
        created, failed, errors = create_teaching_events(token, upn, slots, today)
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
    report_path = REPORTS_DIR / f"calendar_sync_{ts}.json"
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
