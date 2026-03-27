"""
Unit tests for scripts/diff_sync.py — diff engine for calendar sync V2.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import diff_sync  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
UPN_A = "alice.smith@swisslearninggroup.onmicrosoft.com"
UPN_B = "bob.jones@swisslearninggroup.onmicrosoft.com"


def method_old(upn, day, start, end, event_id):
    return {"outlook_event_id": event_id, "day": day, "start": start, "end": end}


def method_new(day, start, end):
    return {"day": day, "start": start, "end": end}


def vip_old(upn, date, start, end, vtype, online, event_id):
    return {
        "outlook_event_id": event_id,
        "date": date,
        "start": start,
        "end": end,
        "type": vtype,
        "online": online,
    }


def vip_new(date, start, end, vtype, online):
    return {"date": date, "start": start, "end": end, "type": vtype, "online": online}


# ---------------------------------------------------------------------------
# compute_method_diff
# ---------------------------------------------------------------------------
class TestComputeMethodDiff:

    def test_all_unchanged(self):
        old = {UPN_A: [method_old(UPN_A, "Monday", "09:00", "10:00", "ev1")]}
        new = {UPN_A: [method_new("Monday", "09:00", "10:00")]}
        diff = diff_sync.compute_method_diff(old, new)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1

    def test_new_slot_for_existing_teacher(self):
        old = {UPN_A: [method_old(UPN_A, "Monday", "09:00", "10:00", "ev1")]}
        new = {
            UPN_A: [
                method_new("Monday", "09:00", "10:00"),
                method_new("Wednesday", "11:00", "12:00"),  # new
            ]
        }
        diff = diff_sync.compute_method_diff(old, new)
        assert len(diff["added"]) == 1
        assert diff["added"][0][0] == UPN_A
        assert diff["added"][0][1]["day"] == "Wednesday"
        assert diff["removed"] == []
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1

    def test_slot_removed_from_existing_teacher(self):
        old = {
            UPN_A: [
                method_old(UPN_A, "Monday", "09:00", "10:00", "ev1"),
                method_old(UPN_A, "Friday", "14:00", "15:00", "ev2"),  # removed
            ]
        }
        new = {UPN_A: [method_new("Monday", "09:00", "10:00")]}
        diff = diff_sync.compute_method_diff(old, new)
        assert diff["added"] == []
        assert len(diff["removed"]) == 1
        assert diff["removed"][0][1]["day"] == "Friday"
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1

    def test_end_time_changed(self):
        old = {UPN_A: [method_old(UPN_A, "Tuesday", "09:00", "10:00", "ev1")]}
        new = {UPN_A: [method_new("Tuesday", "09:00", "10:30")]}  # end changed
        diff = diff_sync.compute_method_diff(old, new)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["changed"]) == 1
        upn, old_ev, new_slot = diff["changed"][0]
        assert upn == UPN_A
        assert old_ev["end"] == "10:00"
        assert new_slot["end"] == "10:30"
        assert diff["unchanged_count"] == 0

    def test_teacher_removed_entirely(self):
        old = {
            UPN_A: [method_old(UPN_A, "Monday", "09:00", "10:00", "ev1")],
            UPN_B: [
                method_old(UPN_B, "Tuesday", "13:00", "14:00", "ev2"),
                method_old(UPN_B, "Thursday", "15:00", "16:00", "ev3"),
            ],
        }
        new = {UPN_A: [method_new("Monday", "09:00", "10:00")]}  # UPN_B removed
        diff = diff_sync.compute_method_diff(old, new)
        assert diff["added"] == []
        assert len(diff["removed"]) == 2
        removed_upns = [r[0] for r in diff["removed"]]
        assert all(u == UPN_B for u in removed_upns)
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1

    def test_teacher_added_entirely(self):
        old = {UPN_A: [method_old(UPN_A, "Monday", "09:00", "10:00", "ev1")]}
        new = {
            UPN_A: [method_new("Monday", "09:00", "10:00")],
            UPN_B: [  # entirely new teacher
                method_new("Wednesday", "10:00", "11:00"),
                method_new("Friday", "14:00", "15:00"),
            ],
        }
        diff = diff_sync.compute_method_diff(old, new)
        assert len(diff["added"]) == 2
        added_upns = [a[0] for a in diff["added"]]
        assert all(u == UPN_B for u in added_upns)
        assert diff["removed"] == []
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1


# ---------------------------------------------------------------------------
# compute_vip_diff
# ---------------------------------------------------------------------------
class TestComputeVipDiff:

    def test_all_unchanged(self):
        old = {UPN_A: [vip_old(UPN_A, "2026-04-01", "10:00", "11:00", "VAD", False, "xyz1")]}
        new = {UPN_A: [vip_new("2026-04-01", "10:00", "11:00", "VAD", False)]}
        diff = diff_sync.compute_vip_diff(old, new)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1

    def test_new_event_for_a_date(self):
        old = {UPN_A: [vip_old(UPN_A, "2026-04-01", "10:00", "11:00", "VAD", False, "xyz1")]}
        new = {
            UPN_A: [
                vip_new("2026-04-01", "10:00", "11:00", "VAD", False),
                vip_new("2026-04-03", "14:00", "15:00", "TPC", False),  # new
            ]
        }
        diff = diff_sync.compute_vip_diff(old, new)
        assert len(diff["added"]) == 1
        assert diff["added"][0][1]["date"] == "2026-04-03"
        assert diff["removed"] == []
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1

    def test_event_removed(self):
        old = {
            UPN_A: [
                vip_old(UPN_A, "2026-04-01", "10:00", "11:00", "VAD", False, "xyz1"),
                vip_old(UPN_A, "2026-04-02", "09:00", "10:00", "TPC", False, "xyz2"),
            ]
        }
        new = {UPN_A: [vip_new("2026-04-01", "10:00", "11:00", "VAD", False)]}
        diff = diff_sync.compute_vip_diff(old, new)
        assert diff["added"] == []
        assert len(diff["removed"]) == 1
        assert diff["removed"][0][1]["date"] == "2026-04-02"
        assert diff["changed"] == []
        assert diff["unchanged_count"] == 1

    def test_end_time_changed(self):
        old = {UPN_A: [vip_old(UPN_A, "2026-04-01", "10:00", "11:00", "VAD", False, "xyz1")]}
        new = {UPN_A: [vip_new("2026-04-01", "10:00", "11:30", "VAD", False)]}  # end changed
        diff = diff_sync.compute_vip_diff(old, new)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["changed"]) == 1
        _, old_ev, new_slot = diff["changed"][0]
        assert old_ev["end"] == "11:00"
        assert new_slot["end"] == "11:30"
        assert diff["unchanged_count"] == 0

    def test_online_flag_flipped(self):
        old = {UPN_A: [vip_old(UPN_A, "2026-04-01", "10:00", "11:00", "VAD", False, "xyz1")]}
        new = {UPN_A: [vip_new("2026-04-01", "10:00", "11:00", "VAD", True)]}  # online flipped
        diff = diff_sync.compute_vip_diff(old, new)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["changed"]) == 1
        _, old_ev, new_slot = diff["changed"][0]
        assert old_ev["online"] is False
        assert new_slot["online"] is True
        assert diff["unchanged_count"] == 0

    def test_both_end_and_online_changed_is_single_entry(self):
        old = {UPN_A: [vip_old(UPN_A, "2026-04-01", "10:00", "11:00", "VAD", False, "xyz1")]}
        new = {UPN_A: [vip_new("2026-04-01", "10:00", "11:30", "VAD", True)]}  # both changed
        diff = diff_sync.compute_vip_diff(old, new)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["changed"]) == 1  # single entry, not two
        assert diff["unchanged_count"] == 0


# ---------------------------------------------------------------------------
# merge_synced_events
# ---------------------------------------------------------------------------
class TestMergeSyncedEvents:

    def _base_old(self):
        return {
            UPN_A: [
                {**method_old(UPN_A, "Monday", "09:00", "10:00", "ev1"), "subject": "Teaching"},
                {**method_old(UPN_A, "Wednesday", "11:00", "12:00", "ev2"), "subject": "Teaching"},
            ],
            UPN_B: [
                {**method_old(UPN_B, "Tuesday", "13:00", "14:00", "ev3"), "subject": "Teaching"},
            ],
        }

    def test_removed_events_excluded(self):
        old = self._base_old()
        diff = {
            "removed": [(UPN_A, old[UPN_A][1])],  # ev2 removed
            "changed": [],
            "added": [],
            "unchanged_count": 2,
        }
        merged = diff_sync.merge_synced_events(old, diff, {})
        upn_a_ids = [ev["outlook_event_id"] for ev in merged.get(UPN_A, [])]
        assert "ev1" in upn_a_ids
        assert "ev2" not in upn_a_ids

    def test_changed_old_excluded_new_included(self):
        old = self._base_old()
        new_ev = {"outlook_event_id": "ev1_new", "day": "Monday", "start": "09:00", "end": "10:30", "subject": "Teaching"}
        diff = {
            "removed": [],
            "changed": [(UPN_A, old[UPN_A][0], method_new("Monday", "09:00", "10:30"))],  # ev1 changed
            "added": [],
            "unchanged_count": 2,
        }
        applied = {UPN_A: [new_ev]}
        merged = diff_sync.merge_synced_events(old, diff, applied)
        upn_a_ids = [ev["outlook_event_id"] for ev in merged.get(UPN_A, [])]
        assert "ev1" not in upn_a_ids
        assert "ev1_new" in upn_a_ids
        assert "ev2" in upn_a_ids  # unchanged, still present

    def test_unchanged_events_preserved(self):
        old = self._base_old()
        diff = {"removed": [], "changed": [], "added": [], "unchanged_count": 3}
        merged = diff_sync.merge_synced_events(old, diff, {})
        assert len(merged[UPN_A]) == 2
        assert len(merged[UPN_B]) == 1

    def test_multiple_teachers_merged_correctly(self):
        old = self._base_old()
        new_ev_b = {"outlook_event_id": "ev4", "day": "Friday", "start": "10:00", "end": "11:00", "subject": "Teaching"}
        diff = {
            "removed": [],
            "changed": [],
            "added": [(UPN_B, method_new("Friday", "10:00", "11:00"))],
            "unchanged_count": 3,
        }
        applied = {UPN_B: [new_ev_b]}
        merged = diff_sync.merge_synced_events(old, diff, applied)
        # UPN_A unchanged
        assert len(merged[UPN_A]) == 2
        # UPN_B has original ev3 + new ev4
        upn_b_ids = [ev["outlook_event_id"] for ev in merged[UPN_B]]
        assert "ev3" in upn_b_ids
        assert "ev4" in upn_b_ids


# ---------------------------------------------------------------------------
# format_diff_summary
# ---------------------------------------------------------------------------
class TestFormatDiffSummary:

    def test_smoke_with_adds_removes_changes(self):
        diff = {
            "added": [(UPN_A, method_new("Monday", "09:00", "10:00"))],
            "removed": [(UPN_B, method_old(UPN_B, "Friday", "14:00", "15:00", "ev99"))],
            "changed": [
                (
                    UPN_A,
                    method_old(UPN_A, "Wednesday", "11:00", "12:00", "ev5"),
                    method_new("Wednesday", "11:00", "12:30"),
                )
            ],
            "unchanged_count": 7,
        }
        summary = diff_sync.format_diff_summary(diff)
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "1" in summary   # counts appear in output
        assert "7" in summary   # unchanged count
