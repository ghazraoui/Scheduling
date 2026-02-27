"""Get today's or this week's class schedule from SparkSource as JSON or table.

Standalone CLI script for scraping SparkSource teacher schedules.
Authenticates, applies read-only guardrails, scrapes the schedule,
and outputs a JSON file or human-readable table.

Run with: python scripts/scrape_schedules.py
Debug:    python scripts/scrape_schedules.py --headed
Table:    python scripts/scrape_schedules.py --table
Agenda:   python scripts/scrape_schedules.py --agenda sfs_lausanne
Weekly:   python scripts/scrape_schedules.py --weekly-teachers
Weekly w/ output: python scripts/scrape_schedules.py --weekly-teachers --output data/teachers.json
Detailed: python scripts/scrape_schedules.py --weekly-detailed --agenda private_german_lausanne

Valid agenda keys: sfs_lausanne, esa_lausanne, sfs_geneva, esa_geneva,
                   sfs_fribourg, esa_fribourg, sfs_montreux, esa_montreux,
                   private_english_lausanne, private_french_lausanne,
                   private_german_lausanne

Exit codes:
  0 = success (JSON or table on stdout, or file written for --weekly-teachers)
  1 = error (message on stderr)
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# Add project root to path for src imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scraper.pages.schedule import (  # noqa: E402
    DEFAULT_AGENDA,
    ScheduleEntry,
    SchedulePage,
)
from src.scraper.utils import (  # noqa: E402
    WHITELISTED_AJAX_PATHS,
)

BASE_URL = os.getenv("SPARKSOURCE_URL", "https://slc.sparksource.fr")
SPARKSOURCE_USER = os.getenv("SPARKSOURCE_USER", "")
SPARKSOURCE_PASS = os.getenv("SPARKSOURCE_PASS", "")
SESSION_PATH = Path("data/session/state.json")

# Day order for sorting schedule slots
_DAY_ORDER = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
}


def _log(msg: str) -> None:
    """Write diagnostic messages to stderr so stdout stays clean for JSON."""
    print(msg, file=sys.stderr)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments using argparse."""
    parser = argparse.ArgumentParser(
        description="Get class schedule from SparkSource as JSON or table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Launch browser in headed mode (visible window).",
    )
    parser.add_argument(
        "--agenda",
        type=str,
        default=DEFAULT_AGENDA,
        help=f"School/centre agenda key (default: {DEFAULT_AGENDA}).",
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--table",
        action="store_true",
        help="Output a human-readable table to stdout (today's schedule).",
    )
    output_group.add_argument(
        "--weekly-teachers",
        action="store_true",
        help="Produce weekly teacher-grouped JSON file (Mon-Sat).",
    )
    output_group.add_argument(
        "--weekly-detailed",
        action="store_true",
        help=(
            "Produce weekly detailed JSON with actual dates, activity types, "
            "and online flags. No merging — one entry per class. "
            "Ideal for private/VIP agendas where classes vary week to week."
        ),
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Output file path for --weekly-teachers / --weekly-detailed mode. "
            "Default: data/teacher-schedule-{agenda}.json"
        ),
    )
    return parser.parse_args()


def _compute_week_dates(reference: date | None = None) -> list[tuple[str, str]]:
    """Compute Mon-Sat dates for the week containing `reference` (default: today).

    Returns list of (YYYY-MM-DD, day_name) tuples, e.g.:
      [("2026-02-23", "Monday"), ("2026-02-24", "Tuesday"), ...]
    """
    if reference is None:
        reference = date.today()

    # Find Monday of this week (weekday() returns 0 for Monday)
    monday = reference - timedelta(days=reference.weekday())

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    result: list[tuple[str, str]] = []
    for offset, day_name in enumerate(day_names):
        day = monday + timedelta(days=offset)
        result.append((day.strftime("%Y-%m-%d"), day_name))

    return result


def _aggregate_teacher_schedule(
    entries: list[tuple[str, ScheduleEntry]],
) -> dict[str, list[dict[str, str]]]:
    """Group entries by teacher_name, split class_time on '-' for start/end.

    Returns:
        {"Teacher Name": [{"day": "Monday", "start": "09:00", "end": "10:00"}, ...]}

    Skips entries where teacher_name is None or is non-teaching staff.
    Deduplicates on (teacher, day, start, end).
    Sorts slots by day order then start time.
    """
    # Non-teaching staff to exclude from teacher schedules
    _EXCLUDED_TEACHERS = frozenset({"Reception TEAM"})

    # Map teacher -> set of (day, start, end) tuples for deduplication
    teacher_slots: dict[str, set[tuple[str, str, str]]] = {}

    for day_name, entry in entries:
        if entry.teacher_name is None:
            continue
        if entry.teacher_name in _EXCLUDED_TEACHERS:
            continue

        # Split class_time on "-" to get start/end
        parts = entry.class_time.split("-")
        if len(parts) != 2:
            continue

        start, end = parts[0].strip(), parts[1].strip()
        teacher = entry.teacher_name

        if teacher not in teacher_slots:
            teacher_slots[teacher] = set()

        teacher_slots[teacher].add((day_name, start, end))

    # Convert to sorted list, merge consecutive slots, then to dicts
    result: dict[str, list[dict[str, str]]] = {}
    for teacher, slots in teacher_slots.items():
        sorted_slots = sorted(
            slots,
            key=lambda s: (_DAY_ORDER.get(s[0], 99), s[1]),
        )

        # Merge consecutive slots on the same day (end == next start)
        merged: list[tuple[str, str, str]] = []
        for day, start, end in sorted_slots:
            if merged and merged[-1][0] == day and merged[-1][2] == start:
                # Extend previous block's end time
                merged[-1] = (day, merged[-1][1], end)
            else:
                merged.append((day, start, end))

        result[teacher] = [
            {"day": day, "start": start, "end": end} for day, start, end in merged
        ]

    return result


def _build_detailed_schedule(
    entries: list[tuple[str, str, ScheduleEntry]],
) -> dict[str, list[dict[str, str]]]:
    """Build detailed per-class schedule grouped by teacher.

    Unlike _aggregate_teacher_schedule, this preserves:
    - actual date (YYYY-MM-DD) instead of day name
    - activity_code (VAD, TPC, JPR, JGP, ICO, VIP)
    - activity_name (full name e.g. "VIP Adults", "Test Preparation Class")
    - is_online flag
    - NO merging of consecutive slots — each class is a separate entry

    Returns:
        {"Teacher Name": [
            {"date": "2026-02-25", "start": "09:00", "end": "10:00",
             "type": "VAD", "name": "VIP Adults", "online": true},
            ...
        ]}

    Deduplicates on (teacher, date, start, end, type).
    Sorts by date then start time.
    """
    _EXCLUDED_TEACHERS = frozenset({"Reception TEAM"})

    teacher_slots: dict[str, set[tuple[str, str, str, str, str, bool]]] = {}

    for date_str, _day_name, entry in entries:
        if entry.teacher_name is None:
            continue
        if entry.teacher_name in _EXCLUDED_TEACHERS:
            continue

        parts = entry.class_time.split("-")
        if len(parts) != 2:
            continue

        start, end = parts[0].strip(), parts[1].strip()
        teacher = entry.teacher_name

        if teacher not in teacher_slots:
            teacher_slots[teacher] = set()

        teacher_slots[teacher].add((
            date_str,
            start,
            end,
            entry.activity_code or "",
            entry.activity_name or "",
            entry.is_online,
        ))

    result: dict[str, list[dict]] = {}
    for teacher, slots in teacher_slots.items():
        sorted_slots = sorted(slots, key=lambda s: (s[0], s[1]))
        result[teacher] = [
            {
                "date": d,
                "start": start,
                "end": end,
                "type": code,
                "name": name,
                "online": online,
            }
            for d, start, end, code, name, online in sorted_slots
        ]

    return result


def _format_table(entries: list) -> str:
    """Format schedule entries as a human-readable table.

    Columns: Time | Activity | Teacher | Room | Students
    """
    if not entries:
        return "(no classes scheduled)"

    # Column headers
    headers = ["Time", "Activity", "Teacher", "Room", "Students"]

    # Build rows
    rows = []
    for e in entries:
        rows.append(
            [
                e.class_time,
                e.activity_code or e.activity_name,
                e.teacher_name or "-",
                e.room or "-",
                str(e.students_booked),
            ]
        )

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Format header
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    separator = "-+-".join("-" * w for w in widths)

    # Format rows
    row_lines = []
    for row in rows:
        row_lines.append(
            " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        )

    return "\n".join([header_line, separator, *row_lines])


async def main(args: argparse.Namespace) -> None:
    headed = args.headed
    agenda = args.agenda
    table_output = args.table
    weekly_teachers = args.weekly_teachers
    weekly_detailed = args.weekly_detailed
    output_path = args.output

    # Default output path for weekly modes
    if weekly_teachers and output_path is None:
        output_path = f"data/teacher-schedule-{agenda}.json"
    if weekly_detailed and output_path is None:
        output_path = f"data/teacher-schedule-{agenda}-detailed.json"

    _log(f"scrape_schedules: starting (agenda={agenda})")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)

        # Load saved session if available
        context_kwargs: dict = {}
        if SESSION_PATH.exists():
            _log(f"  Loading session from {SESSION_PATH}")
            context_kwargs["storage_state"] = str(SESSION_PATH)

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        # --- Authenticate ---
        await page.goto(f"{BASE_URL}/login/show_login/true", wait_until="networkidle")

        if "launchpad" in page.url or "dashboard" in page.url.lower():
            _log("  Logged in via saved session")
        else:
            if not SPARKSOURCE_USER or not SPARKSOURCE_PASS:
                _log("  ERROR: No session and no credentials in .env")
                await browser.close()
                sys.exit(1)
            _log("  Logging in with credentials...")
            await page.fill("#username", SPARKSOURCE_USER)
            await page.fill("#password", SPARKSOURCE_PASS)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=30000)
            _log(f"  Logged in — {page.url}")

            # Save session for future runs
            SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(SESSION_PATH))

        # --- Read-only guardrails ---
        _BLOCKED_METHODS = frozenset({"PUT", "DELETE", "PATCH"})

        async def _block_mutations(route):
            req = route.request
            if req.method in _BLOCKED_METHODS:
                _log(f"  [BLOCKED] {req.method} {req.url}")
                await route.abort("blockedbyclient")
            elif req.method == "POST" and not any(
                p in req.url for p in WHITELISTED_AJAX_PATHS
            ):
                _log(f"  [BLOCKED] POST {req.url}")
                await route.abort("blockedbyclient")
            else:
                await route.continue_()

        await page.route("**/*", _block_mutations)

        # --- Extract schedule ---
        schedule_page = SchedulePage(page)
        await schedule_page.navigate(BASE_URL, agenda=agenda)

        if weekly_teachers or weekly_detailed:
            # --- Weekly modes (both need Mon-Sat extraction) ---
            week_dates = _compute_week_dates()

            if weekly_detailed:
                all_detailed: list[tuple[str, str, ScheduleEntry]] = []
                for date_str, day_name in week_dates:
                    _log(f"  Extracting {day_name} ({date_str})...")
                    day_entries = await schedule_page.extract_date(date_str)
                    for entry in day_entries:
                        all_detailed.append((date_str, day_name, entry))
                    _log(f"    {len(day_entries)} entries")

                result = _build_detailed_schedule(all_detailed)
            else:
                all_entries: list[tuple[str, ScheduleEntry]] = []
                for date_str, day_name in week_dates:
                    _log(f"  Extracting {day_name} ({date_str})...")
                    day_entries = await schedule_page.extract_date(date_str)
                    for entry in day_entries:
                        all_entries.append((day_name, entry))
                    _log(f"    {len(day_entries)} entries")

                result = _aggregate_teacher_schedule(all_entries)

            # Write JSON to disk
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            teacher_count = len(result)
            total_slots = sum(len(slots) for slots in result.values())
            mode_label = "detailed" if weekly_detailed else "teacher"
            _log(
                f"  Weekly {mode_label} schedule: {teacher_count} teachers, "
                f"{total_slots} slots -> {output_path}"
            )
        else:
            # --- Daily mode (today) ---
            entries = await schedule_page.extract_today()
            _log(f"  Extracted {len(entries)} schedule entries for {agenda}")

            if table_output:
                print(_format_table(entries))
            else:
                output = [entry.model_dump(mode="json") for entry in entries]
                print(json.dumps(output, indent=2))

        await browser.close()

    _log("scrape_schedules: done")


if __name__ == "__main__":
    args = _parse_args()
    try:
        asyncio.run(main(args))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
