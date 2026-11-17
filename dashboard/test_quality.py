import copy
import unittest
from quality import quality_sections, display_value, TOTAL_FIELD


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

    def test_sections_and_search_include_descriptions(self):
        rows=[{"Dimension":"ML","Indicateur":"Échéances · H1 ouvertes","Valeur (automatique)":8,"Définition / réserve":"Avant départ"},
              {"Dimension":"ML","Indicateur":"Collecte · Rejets dernier passage","Valeur (automatique)":0},{}]
        self.assertEqual(list(quality_sections(rows)),["Échéances","Collecte"])
        self.assertEqual(list(quality_sections(rows,"  DÉPART ")),["Échéances"])
        self.assertEqual(quality_sections(rows,"Introuvable"),{})

    def test_text_timestamps_and_decimals_are_display_values(self):
        self.assertEqual(display_value("2026-11-17T16:02:00+00:00"),"2026-11-17T16:02:00+00:00")
        self.assertEqual(display_value(1.02564),"1,03")
        self.assertEqual(display_value(0,rate=True),"0,0 %")


if __name__=="__main__":unittest.main()
