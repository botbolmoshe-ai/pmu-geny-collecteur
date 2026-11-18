import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pmu_geny.index_geny_apres_publication import dates_a_traiter, run


class IndexApresPublicationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.now = datetime(2026, 11, 18, 8, tzinfo=timezone.utc)
        self.plan = {"mode": "GLOBAL"}
        for day in ("2026-11-18", "2026-11-19"):
            self.save("sources_pmu/programme_"+day+".json", {"programme": [
                {"depart": day+"T14:00:00+01:00"}]})

    def save(self, name, value):
        path = self.cache / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_index_only_on_global(self):
        self.assertEqual(dates_a_traiter(self.cache, self.plan, self.now),
                         ["2026-11-18", "2026-11-19"])
        self.assertEqual(dates_a_traiter(self.cache, {"mode":"JALONS"}, self.now), [])

    def test_fresh_cache(self):
        self.save("sources_geny/index_2026-11-18.json", {
            "statut":"OK", "schema_index":2, "consultation_utc":self.now.isoformat()})
        self.assertEqual(dates_a_traiter(self.cache,self.plan,self.now), ["2026-11-19"])

    def test_shared_pause(self):
        self.save("rattrapage_historiques/etat.json", {
            "prochain_acces_geny_utc":(self.now+timedelta(minutes=5)).isoformat()})
        self.assertEqual(dates_a_traiter(self.cache,self.plan,self.now), [])

    def test_stop_on_first_refusal(self):
        called = []
        def fetch(cache, date, state):
            called.append(date)
            return {"statut":"GENY_BLOQUE"}
        run(self.cache,self.plan,clock=lambda:self.now,fetch=fetch)
        self.assertEqual(called,["2026-11-18"])

    def test_workflow_order(self):
        workflow = Path(__file__).resolve().parents[1]/".github/workflows/pmu-v16.yml"
        s = workflow.read_text(encoding="utf-8")
        self.assertLess(s.index("Cycle automatique quotidien"),s.index("Synchroniser le registre Google Sheets"))
        self.assertLess(s.index("Synchroniser le registre Google Sheets"),s.index("Rafraichir les index Geny apres publication"))
        self.assertLess(s.index("Synchroniser le registre Google Sheets"),s.index("Apprentissage ML unique apres les cycles de resultats"))
        auto = s.split("Cycle automatique quotidien",1)[1].split("Experience ML manuelle",1)[0]
        self.assertNotIn("max_discoveries=1",auto)
        self.assertNotIn("max_discoveries=0 if",auto)
