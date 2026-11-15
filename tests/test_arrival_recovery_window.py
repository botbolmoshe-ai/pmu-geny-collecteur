"""Regression: yesterday's arrivals remain eligible, predictions do not."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pmu_geny.planification_v20_2 import selectionner_courses, decision_autorisee

PARIS = ZoneInfo("Europe/Paris")


class TestArrivalRecovery(unittest.TestCase):
    def test_yesterday_is_selected_only_for_arrival_recovery(self):
        now = datetime(2026, 11, 15, 9, 20, tzinfo=PARIS)
        yesterday = (now - timedelta(days=1)).date().isoformat()
        course = {
            "date": yesterday, "code": "R1C1",
            "depart": yesterday + "T14:00:00+01:00",
            "priorite_metier": "P1",
        }
        self.assertEqual(
            [c["code"] for c in selectionner_courses(
                [course], now, yesterday, [], True, {"courses": {}}, max_courses=10
            )],
            ["R1C1"],
        )
        self.assertFalse(decision_autorisee(
            now, yesterday, datetime.fromisoformat(course["depart"])
        ))

    def test_old_archives_are_excluded(self):
        now = datetime(2026, 11, 15, 9, 20, tzinfo=PARIS)
        day = "2026-11-13"
        course = {"code": "R1C1", "depart": day + "T14:00:00+01:00"}
        self.assertEqual(
            selectionner_courses([course], now, day, [], True, {"courses": {}}),
            [],
        )

    def test_archived_result_is_not_reprocessed(self):
        now = datetime(2026, 11, 15, 9, 20, tzinfo=PARIS)
        day = "2026-11-14"
        course = {"code": "R1C1", "depart": day + "T14:00:00+01:00"}
        state = {"courses": {"R1C1": {"etat": "TERMINE_ARCHIVE"}}}
        self.assertEqual(
            selectionner_courses([course], now, day, [], True, state), []
        )


if __name__ == "__main__":
    unittest.main()
