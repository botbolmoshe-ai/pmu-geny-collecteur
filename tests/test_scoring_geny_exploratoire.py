"""Tests hors ligne du scoring Geny; aucun accès réseau ni écriture Sheets."""
import unittest
from pmu_geny.scoring_geny_exploratoire import evaluer_cheval, classer_course

COURSE = {"date": "2026-11-13", "depart": "2026-11-13T14:00:00+01:00",
          "hippodrome": "VINCENNES", "distance_m": 2700}

def perf(day, rank, hip="VINCENNES", distance=2700):
    return {"date": day, "classement": rank, "hippodrome": hip, "distance_m": distance}

class ScoringGenyTests(unittest.TestCase):
    def test_aucune_fuite_future(self):
        h = {"performances": [perf("2026-11-01", "2"), perf("2026-11-14", "1")]}
        r = evaluer_cheval(h, COURSE)
        self.assertEqual(r["nb_performances"], 1)

    def test_sans_historique(self):
        r = evaluer_cheval({}, COURSE)
        self.assertIsNone(r["score_merite"])
        self.assertEqual(r["couverture_pct"], 0)

    def test_ordre_et_top3(self):
        chevaux = [
            {"numero": 1, "nom": "A", "historique": {"performances": [perf("2026-11-01", "1")]}},
            {"numero": 2, "nom": "B", "historique": {"performances": [perf("2026-11-01", "2")]}},
            {"numero": 3, "nom": "C", "historique": {"performances": [perf("2026-11-01", "3")]}},
            {"numero": 4, "nom": "D", "historique": {}},
        ]
        result = classer_course(COURSE, chevaux)
        self.assertEqual(result["statut"], "TOP3_DISPONIBLE")
        self.assertEqual([x["numero"] for x in result["top3"]], [1, 2, 3])

    def test_inconnu_pas_penalise_comme_echec(self):
        h = {"performances": [{"date": "2026-11-01", "classement": "2"}]}
        r = evaluer_cheval(h, COURSE)
        self.assertLess(r["couverture_pct"], 100)
        self.assertGreater(r["score_merite"], 0)

if __name__ == "__main__":
    unittest.main()
