import unittest
from datetime import datetime, timezone, date
from trot_analytics.performance import performance_rows, summarize, evolution


class PerformanceTests(unittest.TestCase):
    now=datetime(2026,11,18,12,tzinfo=timezone.utc)

    def row(self, key="a", day="2026-11-17", direct=66.67, ml=0):
        return {"Clé course (technique)":key,"Date":day,"Hippodrome":"VINCENNES",
                "Départ (Paris)":day+"T12:00:00+01:00",
                "Arrivée · Vérifiée UTC":day+"T12:30:00+01:00",
                "Évaluation · État":"EVALUE","Arrivée · N° officiels":"1,2,3",
                "TOP3 direct · Chevaux":"1,2,4",
                "TOP3 direct · Heure calcul UTC":day+"T11:00:00+01:00",
                "TOP3 direct · Chevaux à l’arrivée (0–3)":2,"TOP3 direct · Matching (%)":direct,
                "TOP3 ML · Chevaux":"4,5,6","TOP3 ML · Chevaux à l’arrivée (0–3)":0,
                "TOP3 ML · Matching (%)":ml,"ML · Statut":"ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE"}

    def test_zero_is_valid_not_missing(self):
        s=summarize(performance_rows([self.row()],self.now))
        self.assertEqual(s["courses"],1)
        self.assertAlmostEqual(s["direct"],200/3)
        self.assertEqual(s["ml"],0)

    def test_common_perimeter_and_missing(self):
        s=summarize(performance_rows([self.row(),self.row("b",ml="")],self.now))
        self.assertEqual((s["courses"],s["direct_available"],s["ml_available"]),(1,2,1))
        self.assertEqual(s["ml"],0)
        self.assertIsNone(summarize(performance_rows([self.row(ml="")],self.now))["ml"])

    def test_duplicate_keys_and_invalid_chronology(self):
        bad=self.row("b");bad["Arrivée · Vérifiée UTC"]="2026-11-30T12:30:00+01:00"
        self.assertEqual(summarize(performance_rows([self.row(),self.row(),bad],self.now))["courses"],0)

    def test_bad_published_matching(self):
        self.assertEqual(summarize(performance_rows([self.row(direct=33.33)],self.now))["courses"],0)

    def test_stale_status_allows_direct_but_keeps_ml_gate(self):
        row = self.row()
        row["Évaluation · État"] = "ARRIVEE_SANS_TOP3_PUBLIE"
        stats = summarize(performance_rows([row], self.now))
        self.assertEqual((stats["evaluated"], stats["direct_available"], stats["ml_available"]), (1, 1, 0))
        row["TOP3 direct · Heure calcul UTC"] = row["Départ (Paris)"]
        self.assertEqual(performance_rows([row], self.now), [])

    def test_cumulative_is_weighted_by_courses(self):
        rows=[{"date":date(2026,11,16),"direct":100,"ml":0},
              {"date":date(2026,11,17),"direct":0,"ml":100},
              {"date":date(2026,11,17),"direct":0,"ml":100}]
        e=evolution(rows)
        self.assertEqual(e[-1]["TOP3 direct"],0)
        self.assertAlmostEqual(e[-1]["Direct cumulé"],100/3)
        self.assertAlmostEqual(e[-1]["ML cumulé"],200/3)
        self.assertEqual(e[-1]["Courses cumulées"],3)
