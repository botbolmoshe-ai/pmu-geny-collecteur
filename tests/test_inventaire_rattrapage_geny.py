import unittest
from pmu_geny.inventaire_rattrapage_geny import audit

class InventaireGenyTests(unittest.TestCase):
    def test_dedoublonnage_et_priorite(self):
        courses = [{"Cheval": "Étoile d'Or"}, {"Cheval": "ETOILE D'OR"},
                   {"Cheval": "Autre"}]
        hist = [{"cheval": "Étoile d'Or", "identifiant_cheval": "123",
                 "cle_performance": "123|2026-01-01|VINCENNES",
                 "source_url": "https://www.geny.com/cheval/123"}]
        result = audit(courses, hist)
        self.assertEqual(result["chevaux_uniques"], 2)
        self.assertEqual(result["sans_historique"], 1)
        self.assertEqual(result["file_rattrapage"][0]["nom"], "Autre")
        self.assertEqual(result["chevaux_avec_ligne_geny"], 1)

    def test_ne_confond_pas_autres_sources_avec_geny(self):
        result = audit([{"Cheval": "Test"}], [{"cheval": "Test",
                        "source_url": "https://www.zone-turf.fr/cheval/test"}])
        self.assertEqual(result["sans_historique"], 0)
        self.assertEqual(result["sans_ligne_geny"], 1)

if __name__ == "__main__":
    unittest.main()
