"""Tests hors réseau des invariants de supervision."""
import unittest
from datetime import datetime, timezone
from pmu_geny.audit_checkpoint import analyser


class AuditCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
        self.bilan = {
            "inventaire_id": "test", "revision_inventaire": 5,
            "maj_utc": "2026-11-23T11:00:00+00:00",
            "statut": "PARTIEL_REPRENABLE", "sync_kpi": "OK",
            "bilan": {
                "cibles_inventoriees": 2584, "cibles_completees": 1201,
                "cibles_restantes": 1383,
                "historiques_ferrures_a_completer": 447,
                "synchronisations_en_attente": 0,
            },
            "lot_96": {"cibles": 96, "completes": 75, "publiees": 75, "restantes": 21},
        }

    def audit(self):
        return analyser(self.bilan, maintenant=self.now)

    def test_partiel_coherent_ne_signifie_pas_termine(self):
        result = self.audit()
        self.assertEqual(result["alertes"], [])
        self.assertFalse(result["fin_globale_prouvee_par_compteurs"])

    def test_total_incoherent(self):
        self.bilan["bilan"]["cibles_restantes"] = 100
        self.assertIn("INCOHERENCE_INVENTAIRE", self.audit()["alertes"])

    def test_fausse_fin(self):
        self.bilan["statut"] = "TERMINE"
        self.assertIn("FIN_GLOBALE_NON_PROUVEE", self.audit()["alertes"])

    def test_fin_avec_compteurs_concordants(self):
        self.bilan["statut"] = "TERMINE"
        self.bilan["derniere_acquisition_validee_utc"] = "2026-11-21T11:00:00+00:00"
        self.bilan["bilan"].update(cibles_completees=2584, cibles_restantes=0, historiques_ferrures_a_completer=0)
        self.assertTrue(self.audit()["fin_globale_prouvee_par_compteurs"])

    def test_lot_96_inchange(self):
        self.bilan["lot_96"]["cibles"] = 95
        self.assertIn("DENOMINATEUR_LOT_96_MODIFIE", self.audit()["alertes"])

    def test_lot_96_restantes_calculees_sur_les_publications(self):
        self.bilan["lot_96"].update(completes=78, publiees=75, restantes=21)
        self.assertEqual(self.audit()["alertes"], [])
        self.bilan["lot_96"]["restantes"] = 18
        self.assertIn("LOT_96_INCOHERENT", self.audit()["alertes"])

    def test_lot_96_compteur_negatif_refuse(self):
        self.bilan["lot_96"]["publiees"] = -1
        self.assertIn("LOT_96_COMPTEURS_INVALIDES", self.audit()["alertes"])

    def test_bilan_perime(self):
        self.bilan["maj_utc"] = "2026-11-22T00:00:00+00:00"
        self.assertIn("BILAN_ANCIEN", self.audit()["alertes"])

    def test_bilan_frais_mais_acquisition_ancienne(self):
        self.bilan["derniere_acquisition_validee_utc"] = "2026-11-23T03:00:00+00:00"
        resultat = self.audit()
        self.assertEqual(resultat["age_heures"], 1)
        self.assertEqual(resultat["age_acquisition_heures"], 9)
        self.assertEqual(resultat["alertes"], ["ACQUISITION_ANCIENNE"])

    def test_horodatage_acquisition_absent_invalide_ou_futur(self):
        cas = (
            (None, "AUCUNE_ACQUISITION_VALIDEE"),
            ("2026-11-23T11:00:00", "HORODATAGE_ACQUISITION_INVALIDE"),
            ("2026-11-23T13:00:00Z", "HORODATAGE_ACQUISITION_FUTUR"),
        )
        for horodatage, alerte in cas:
            with self.subTest(horodatage=horodatage):
                self.bilan["derniere_acquisition_validee_utc"] = horodatage
                self.assertEqual(self.audit()["alertes"], [alerte])

    def test_compteur_booleen_refuse(self):
        self.bilan["bilan"]["cibles_completees"] = True
        self.assertIn("COMPTEUR_INVALIDE:cibles_completees", self.audit()["alertes"])


if __name__ == "__main__":
    unittest.main()
