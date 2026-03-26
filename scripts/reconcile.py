"""
Reconcile tracked Outlook event IDs against the live Graph API.

Reads every state file in data/last_synced/ and checks that each tracked
outlook_event_id still exists in Outlook. Reports present / missing / error
counts per agenda without making any changes (always read-only).

Usage:
    python scripts/reconcile.py              # check all agendas
    python scripts/reconcile.py --agenda sfs_lausanne   # single agenda
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_token, graph_get
from diff_sync import load_last_synced, STATE_DIR

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def discover_agendas() -> list[str]:
    """Return all agenda keys found in data/last_synced/."""
    if not STATE_DIR.exists():
        return []
    return sorted(p.stem for p in STATE_DIR.glob("*.json"))


def check_agenda(token: str, agenda: str) -> dict:
    """Check every tracked event for one agenda.

    Returns:
        {
            "agenda": str,
            "synced_at": str,
            "total": int,
            "present": int,
            "missing": int,
            "errors": int,
            "missing_events": [...],
            "error_events": [...],
        }
    """
    state = load_last_synced(agenda)
    if state is None:
        return {
            "agenda": agenda,
            "skipped": True,
            "reason": "no state file",
        }

    events_by_upn: dict = state.get("events", {})
    synced_at = state.get("synced_at", "unknown")

    present = 0
    missing = 0
    errors = 0
    missing_events = []
    error_events = []

    for upn, events in events_by_upn.items():
        for ev in events:
            event_id = ev.get("outlook_event_id", "")
            if not event_id:
                errors += 1
                error_events.append({"upn": upn, "event": ev, "status": "no_id"})
                continue

            result = graph_get(token, f"/users/{upn}/calendar/events/{event_id}")

            if "error" not in result:
                present += 1
            elif result["error"] == 404:
                missing += 1
                missing_events.append({"upn": upn, "event": ev})
            else:
                errors += 1
                error_events.append({
                    "upn": upn,
                    "event": ev,
                    "status": result["error"],
                    "message": result.get("message", "")[:200],
                })

    return {
        "agenda": agenda,
        "synced_at": synced_at,
        "total": present + missing + errors,
        "present": present,
        "missing": missing,
        "errors": errors,
        "missing_events": missing_events,
        "error_events": error_events,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Reconcile tracked Outlook event IDs against the live Graph API (read-only)"
    )
    parser.add_argument(
        "--agenda", type=str, default=None,
        help="Single agenda to check (e.g., sfs_lausanne). Default: all agendas.",
    )
    args = parser.parse_args()

    if args.agenda:
        agendas = [args.agenda]
    else:
        agendas = discover_agendas()
        if not agendas:
            print("No state files found in data/last_synced/ — nothing to reconcile.")
            sys.exit(0)

    print("=" * 60)
    print("CALENDAR RECONCILIATION [READ-ONLY]")
    print(f"Agendas: {', '.join(agendas)}")
    print("=" * 60)
    print()

    print("Authenticating...")
    token = get_token()
    print("OK\n")

    results = []
    total_present = 0
    total_missing = 0
    total_errors = 0

    for agenda in agendas:
        print(f"Checking: {agenda}")
        result = check_agenda(token, agenda)
        results.append(result)

        if result.get("skipped"):
            print(f"  SKIPPED — {result['reason']}\n")
            continue

        present = result["present"]
        missing = result["missing"]
        errors = result["errors"]
        total = result["total"]

        status = "OK" if missing == 0 and errors == 0 else "DRIFT DETECTED"
        print(f"  [{status}] {total} events checked: {present} present, {missing} missing, {errors} errors")

        if result["missing_events"]:
            for item in result["missing_events"][:5]:
                upn = item["upn"]
                ev = item["event"]
                label = ev.get("day", ev.get("date", "?"))
                print(f"    MISSING: {upn.split('@')[0]} — {label} {ev.get('start', '')} (id: {ev.get('outlook_event_id', '?')[:16]}...)")
            if len(result["missing_events"]) > 5:
                print(f"    ... and {len(result['missing_events']) - 5} more missing")

        if result["error_events"]:
            for item in result["error_events"][:3]:
                upn = item["upn"]
                print(f"    ERROR: {upn.split('@')[0]} — status {item.get('status', '?')}")
            if len(result["error_events"]) > 3:
                print(f"    ... and {len(result['error_events']) - 3} more errors")

        total_present += present
        total_missing += missing
        total_errors += errors
        print()

    # Summary
    checked_results = [r for r in results if not r.get("skipped")]
    print("-" * 60)
    print(f"TOTAL: {total_present + total_missing + total_errors} events across {len(checked_results)} agendas")
    print(f"  Present: {total_present}  |  Missing: {total_missing}  |  Errors: {total_errors}")
    if total_missing > 0 or total_errors > 0:
        print("  ACTION REQUIRED: Re-run sync to restore missing events.")
    else:
        print("  All tracked events confirmed present in Outlook.")

    # Write report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"reconcile_{ts}.json"
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agendas_checked": agendas,
        "summary": {
            "total": total_present + total_missing + total_errors,
            "present": total_present,
            "missing": total_missing,
            "errors": total_errors,
        },
        "results": results,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
