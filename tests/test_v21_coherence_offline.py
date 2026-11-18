"""Non-regression V21 : perimetre, historiques et export Sheets."""
import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from pmu_geny.auto_v18 import programme_diagnostic
from pmu_geny.collecte_geny_v4 import lire_classement
from pmu_geny.controle_historique import classifier
from pmu_geny.sync_google_sheets import source_rows

PARIS=ZoneInfo("Europe/Paris")

class V21CoherenceTest(unittest.TestCase):
    def test_perimetre_france_trot_07_21(self):
        courses=[]
        for i,(h,m) in enumerate(((6,59),(7,0),(19,1),(21,0),(21,1)),1):
            courses.append({"numOrdre":i,"heureDepart":int(datetime(2026,11,12,h,m,tzinfo=PARIS).timestamp()*1000),
                            "nombreDeclaresPartants":12,"specialite":"TROT_ATTELE","libelle":f"Prix {i}"})
        obj={"reunions":[{"numOfficiel":1,"pays":"FRA","hippodrome":{"libelleLong":"Vincennes"},"courses":courses}]}
        selected,diag=programme_diagnostic(obj,"2026-11-12")
        self.assertEqual([c["code"] for c in selected],["R1C2","R1C3","R1C4"])
        self.assertEqual(diag["exclusions"].get("depart_hors_plage_07_21"),2)
    def test_deux_performances_distinctes_meme_date(self):
        base={"date":"2026-05-03","hippodrome":"Naples","discipline":"Attelé",
              "distance_m":"1600","classement":"2"}
        rows=[{**base,"chrono":"1'11''1","texte_source":"03/05/2026 | Naples | Attelé | 1600 | 1'11''1 | 2e"},
              {**base,"chrono":"1'09''8","texte_source":"03/05/2026 | Naples | Attelé | 1600 | 1'09''8 | 2e"}]
        result={"nombre_annonce_geny":2,"nombre_extrait":2,"performances":rows,"dates_uniques":False}
        self.assertEqual(classifier(result)[0],"COMPLET")
        result["performances"][1]=dict(rows[0])
        self.assertEqual(classifier(result)[0],"DONNEES_INCOHERENTES")
    def test_codes_de_classement_source(self):
        self.assertEqual(lire_classement(["13,5","D"]),"D")
        self.assertEqual(lire_classement(["13,5","R"]),"R")
        self.assertEqual(lire_classement(["13,5","12","e"]),"12")
    def test_export_deux_courses_meme_date_vers_sheets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for course in ("GENY-100","GENY-101"):
                folder=root/"exports"/course
                folder.mkdir(parents=True)
                with (folder/"performances.csv").open("w",encoding="utf-8-sig",newline="") as f:
                    cols=["cheval_id","nom","date","hippodrome","discipline","distance_m","classement","chrono","texte_source"]
                    w=csv.DictWriter(f,fieldnames=cols,delimiter=";")
                    w.writeheader()
                    for chrono in ("1'11''1","1'09''8"):
                        w.writerow({"cheval_id":"2786432","nom":"Frank Gio","date":"2026-05-03",
                                    "hippodrome":"Naples","discipline":"Attelé","distance_m":"1600",
                                    "classement":"2","chrono":chrono,"texte_source":f"Naples|{chrono}"})
            one=source_rows(root)["Historique chevaux"]
            two=source_rows(root)["Historique chevaux"]
            self.assertEqual(len(one),2)
            self.assertEqual(set(one),set(two))
            self.assertIn("2786432|2026-05-03|NAPLES",one)
            self.assertEqual({row["chrono"] for row in one.values()},{"1'11''1","1'09''8"})

if __name__=="__main__":
    unittest.main()
