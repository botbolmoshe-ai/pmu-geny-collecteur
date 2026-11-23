import copy
import unittest
from trot_analytics.quality import quality_sections, display_value, TOTAL_FIELD


class QualityTests(unittest.TestCase):
    def test_source_total_zero_and_missing_remain_distinct(self):
        data=[{"Dimension":"Historique","Indicateur":"Sans historique","Valeur (automatique)":0,TOTAL_FIELD:1429},
              {"Dimension":"ML","Indicateur":"Moyenne ML","Valeur (automatique)":""}]
        before=copy.deepcopy(data)
        sections=quality_sections(data)
        self.assertEqual(sections["Historique"][0]["Nombre / valeur"],"0")
        self.assertEqual(sections["Historique"][0]["Total"],"1\u202f429")
        self.assertEqual(sections["ML"][0]["Nombre / valeur"],"—")
        self.assertEqual(sections["ML"][0]["Total"],"—")
        self.assertEqual(data,before)

    def test_percent_value_keeps_its_original_reference_total(self):
        row={"Dimension":"Qualité","Indicateur":"Taux ferrure renseignée", "Valeur (automatique)":0.75,TOTAL_FIELD:100}
        result=quality_sections([row])["Qualité"][0]
        self.assertEqual(result["Nombre / valeur"],"75,0 %")
        self.assertEqual(result["Total"],"100")

    def test_maturite_rates_have_a_dedicated_section(self):
        row = {"Dimension": "ML", "Indicateur": "Maturité ML · Couverture · Forme PMU",
               "Valeur (automatique)": 0.9, TOTAL_FIELD: 3000}
        published = quality_sections([row])["Maturité ML"][0]
        self.assertEqual(published["Nombre / valeur"], "90,0 %")
        self.assertEqual(published["Total"], "3\u202f000")

    def test_geny_identity_indicators_keep_their_own_counts(self):
        values = {
            "Chevaux non identifiés (noms distincts)": 1000,
            "Contextes sans identifiant Geny": 1005,
            "Chevaux identifiés sans carrière complète": 24,
        }
        rows = [{"Indicateur": "Rattrapage · "+label, "Valeur (automatique)": value}
                for label, value in values.items()]
        published = quality_sections(rows)["Rattrapage"]
        self.assertEqual([row["Indicateur"] for row in published],
                         ["Rattrapage · "+label for label in values])
        self.assertEqual([row["Nombre / valeur"] for row in published],
                         ["1\u202f000", "1\u202f005", "24"])

    def test_sections_and_search_include_descriptions(self):
        rows=[{"Dimension":"ML","Indicateur":"Échéances · H-3 ouvertes","Valeur (automatique)":8,"Définition / réserve":"Avant départ"},
              {"Dimension":"ML","Indicateur":"Échéances · H1 ouvertes","Valeur (automatique)":3},
              {"Dimension":"ML","Indicateur":"Collecte · Rejets dernier passage","Valeur (automatique)":0},{}]
        self.assertEqual(list(quality_sections(rows)),["Échéances","Échéances · Historique H-2/H-1","Collecte"])
        self.assertEqual(list(quality_sections(rows,"  DÉPART ")),["Échéances"])
        self.assertEqual(quality_sections(rows,"Introuvable"),{})

    def test_text_timestamps_and_decimals_are_display_values(self):
        self.assertEqual(display_value("2026-11-17T16:02:00+00:00"),"17/11/2026 16:02")
        self.assertEqual(display_value(1.02564),"1,03")
        self.assertEqual(display_value(0,rate=True),"0,0 %")


if __name__=="__main__":unittest.main()
