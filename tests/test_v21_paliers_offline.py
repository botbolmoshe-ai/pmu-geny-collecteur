"""Validation progressive de la collecte actuelle et des paliers TOP3, sans mutation."""
import tempfile
import unittest
import csv
import json
from pathlib import Path

from pmu_geny.partants_actuels_v21 import extraire_partants
from pmu_geny.sync_google_sheets import source_rows, plan_sheet


class V21PaliersTests(unittest.TestCase):
    def test_champs_pmu_explicitement_extraits(self):
        raw={"participants":[
            {"numPmu":1,"driver":{"nom":"A. Test"},"entraineur":"B. Test",
             "proprietaire":{"nomComplet":"Écurie Exemple"},"ferrure":"D4"},
            {"numPmu":2,"driver":{"id":123}, "ferrure":None}
        ]}
        d=extraire_partants(raw)
        self.assertEqual(d[1],{"driver_jockey":"A. Test","entraineur":"B. Test",
                               "proprietaire":"Écurie Exemple","ferrure":"D4"})
        self.assertEqual(d[2],{})

    def test_deux_paliers_sans_inventer_ml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);day="2026-11-12";code="R1C1";cid="GENY-TEST"
            def write(path,obj):
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(obj),encoding="utf8")
            write(root/"sources_pmu"/f"programme_{day}.json",
                  {"programme":[{"code":code,"hippodrome":"Vincennes","discipline":"TROT_ATTELE","distance_m":2700}]})
            write(root/"manifestes"/f"{cid}.json",
                  {"courses":[{"course_id":cid,
                      "source_course_geny":"https://www.geny.com/course/123-test/partants-pronostics",
                      "partants":[{"numero":1,"id":"123","nom":"Cheval A"}]}]})
            write(root/"partants_actuels"/f"{day}_{code}.json",
                  {"capture_utc":"2026-11-12T07:30:00+00:00","chevaux":{"1":{
                      "driver_jockey":"A. Driver","entraineur":"B. Entraîneur",
                      "proprietaire":"Écurie A","ferrure":"D4"}}})
            write(root/"pronostics"/f"{day}_{code}_top3.json",
                  {"frozen_at":"2026-11-12T08:30:00+00:00",
                   "top3":[{"numero":1}],"classement_complet":[{"numero":1}]})
            exp=root/"exports"/cid
            exp.mkdir(parents=True)
            with (exp/"comparatif_predictions.csv").open("w",newline="",encoding="utf8") as f:
                w=csv.DictWriter(f,fieldnames=["date","course","depart","numero","nom","statut_np",
                  "baseline_rang","baseline_top3","baseline_final_rang","baseline_final_top3",
                  "ml_etat","arrivee_rang"],delimiter=";")
                w.writeheader()
                w.writerow({"date":day,"course":code,"depart":"2026-11-12T10:00:00+01:00",
                    "numero":1,"nom":"Cheval A","statut_np":"PARTANT","baseline_rang":1,
                    "baseline_top3":"OUI","baseline_final_rang":1,"baseline_final_top3":"OUI",
                    "ml_etat":"ML_NON_ENTRAINE"})
            with (exp/"suivi_chevaux.csv").open("w",newline="",encoding="utf8") as f:
                w=csv.DictWriter(f,fieldnames=["numero","historique_statut",
                                               "nombre_performances_persistantes","nombre_annonce_geny"],delimiter=";")
                w.writeheader()
                w.writerow({"numero":1,"historique_statut":"COMPLET",
                            "nombre_performances_persistantes":35,"nombre_annonce_geny":35})
            rows=source_rows(root)["Courses & Prévisions"]
            self.assertEqual(len(rows),1)
            v=next(iter(rows.values()))
            self.assertEqual(v["driver_jockey"],"A. Driver")
            self.assertEqual(v["entraineur"],"B. Entraîneur")
            self.assertEqual(v["ferrure"],"D4")
            self.assertEqual(v["historique_nb_courses_datees"],"35")
            self.assertEqual(v["statut_prevision"],"FIGE_HISTORIQUE")
            self.assertEqual(v["ml_modele_statut"],"ML_NON_ENTRAINE")
            self.assertEqual(v["ml_rang"],"")
            self.assertEqual(v["historique_modele_statut"],"FIGE")
            self.assertEqual(v["secours_statut"],"NON_CALCULE")
            self.assertEqual(v["rang_top3"],"1")

    def test_top3_np_inconnu_rattrapage_avant_depart(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from pmu_geny.pronostics_v18 import preparer_top3
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            course={"date":"2026-11-12","code":"R1C1",
                    "depart":"2026-11-12T15:00:00+01:00"}
            manifest={"courses":[{"course_id":"GENY-123",
                      "partants":[{"numero":i,"id":str(i),"nom":f"Cheval {i}"} for i in range(1,5)]}]}
            for i in range(1,5):
                path=root/"historiques"/str(i)/"historique_geny.json"
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps({"performances":[
                    {"date":"2026-11-01","classement":str(i)},
                    {"date":"2026-10-25","classement":str(i)}]}),encoding="utf8")
            now=datetime(2026,11,12,14,30,tzinfo=ZoneInfo("Europe/Paris"))
            result=preparer_top3(root,course,manifest,now)
            self.assertEqual(result,"FIGE_BASELINE_EXPERIMENTALE")
            forecast=json.loads((root/"pronostics"/"2026-11-12_R1C1_top3.json").read_text())
            self.assertEqual(forecast["statut_np"],"NP_NON_VERIFIE")
            self.assertEqual(forecast["qualite_horaire"],"RATTRAPAGE_AVANT_DEPART")
            self.assertEqual([h["numero"] for h in forecast["top3"]],[1,2,3])
            self.assertEqual(preparer_top3(root,course,manifest,
                            datetime(2026,11,12,15,1,tzinfo=ZoneInfo("Europe/Paris"))),
                            "DEJA_FIGE")

    def test_registre_11_novembre_reel(self):
        root=Path("reference_pmu")
        if not root.exists():self.skipTest("registre de production non charge")
        courses=source_rows(root)["Courses & Prévisions"]
        day=[r for r in courses.values() if r.get("date_course")=="2026-11-11"]
        self.assertGreaterEqual(len(day),24)
        self.assertTrue(any(r.get("rncn")=="R10C1" for r in day))
        self.assertTrue(any(r.get("rncn")=="R13C1" for r in day))
        self.assertTrue(all(r.get("ml_modele_statut") for r in day))
        self.assertTrue(all(r.get("statut_prevision") for r in day))


if __name__=="__main__":
    unittest.main()
