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
        for key,value in {"driver_jockey":"A. Test","entraineur":"B. Test",
                          "proprietaire":"Écurie Exemple","ferrure":"D4"}.items():
            self.assertEqual(d[1][key],value)
        self.assertEqual(d[2]["statut_np"],"NP_NON_VERIFIE")

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

    def test_reset_preserves_histories_and_blocks_old_courses(self):
        from pmu_geny.sync_google_sheets import limiter_cours_registre
        src={"Courses & Prévisions":{
                 "ancien":{"date_course":"2026-11-11"},
                 "nouveau":{"date_course":"2026-11-12"}},
             "Résultats & Analyse":{
                 "ancien":{"date_course":"2026-11-10"},
                 "nouveau":{"date_course":"2026-11-12"}},
             "Historique chevaux":{
                 "historique":{"date_course_historique":"2026-06-27"}}}
        out=limiter_cours_registre(src)
        self.assertEqual(list(out["Courses & Prévisions"]),["nouveau"])
        self.assertEqual(list(out["Résultats & Analyse"]),["nouveau"])
        self.assertEqual(out["Historique chevaux"],src["Historique chevaux"])

    def test_resultat_pmu_sans_manifest_geny(self):
        from pmu_geny.resultats_v18 import enregistrer_resultats
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            day="2026-11-12"
            course={"date":day,"code":"R2C1","depart":"2026-11-12T13:30:00+01:00",
                    "hippodrome":"Vincennes"}
            raw={"participants":[
                {"numPmu":1,"ordreArrivee":3},
                {"numPmu":2,"ordreArrivee":1},
                {"numPmu":3,"ordreArrivee":2},
                {"numPmu":4}]}
            self.assertEqual(enregistrer_resultats(root,course,raw),"ARRIVEE_ENREGISTREE")
            src=root/"sources_pmu"/f"programme_{day}.json"
            src.parent.mkdir(parents=True,exist_ok=True)
            src.write_text(json.dumps({"programme":[course]}),encoding="utf8")
            output=source_rows(root)["Résultats & Analyse"]
            self.assertEqual(len(output),1)
            row=next(iter(output.values()))
            self.assertEqual(row["arrivee_officielle_numeros"],"2,3,1")
            self.assertEqual(row["statut_evaluation"],"ARRIVEE_SANS_TOP3_FIGE")
            self.assertEqual(row["top3_prevu_numeros"],"")
            self.assertEqual(row["score_sur_3"],"")

    def test_v22_trois_niveaux_independants_du_manifeste(self):
        from datetime import datetime, timezone
        from pmu_geny.top3_independants_v22 import calculer
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            day="2026-11-12";code="R1C3"
            course={"date":day,"code":code,"depart":"2026-11-12T15:00:00+01:00",
                    "hippodrome":"Vincennes","nombre_declares":4}
            raw={"participants":[
                {"numPmu":1,"nomCheval":"A","musique":"1a2a3a","rapportDirect":4.2,"nonPartant":False},
                {"numPmu":2,"nomCheval":"B","musique":"2a3a4a","rapportDirect":3.2,"nonPartant":False},
                {"numPmu":3,"nomCheval":"C","musique":"4a5a6a","rapportDirect":9.4,"nonPartant":False},
                {"numPmu":4,"nomCheval":"D","musique":"Da0a5a","rapportDirect":14.5,"nonPartant":False}]}
            moment=datetime(2026,11,12,12,30,tzinfo=timezone.utc)
            self.assertEqual(calculer(root,course,raw,moment),
                            {"direct":"CALCULE_COMPLET","cotes":"CALCULE_COMPLET"})
            dossier=root/"pronostics"
            self.assertEqual([r["numero"] for r in json.loads(
                (dossier/f"{day}_{code}_direct.json").read_text())["top3"]],[1,2,3])
            self.assertEqual([r["numero"] for r in json.loads(
                (dossier/f"{day}_{code}_cotes.json").read_text())["top3"]],[2,1,3])
            self.assertFalse((dossier/f"{day}_{code}_ml_latest.json").exists())
            self.assertEqual(calculer(root,course,raw,datetime(
                2026,11,12,14,30,tzinfo=timezone.utc))["direct"],"APRES_DEPART")
            programme=root/"sources_pmu"/f"programme_{day}.json"
            programme.parent.mkdir(parents=True)
            programme.write_text(json.dumps({"programme":[course]}),encoding="utf8")
            current=root/"partants_actuels"/f"{day}_{code}.json"
            current.parent.mkdir(parents=True)
            current.write_text(json.dumps({"source":"PMU_API_PARTICIPANTS",
                "chevaux":{str(x["numPmu"]):{"nom":x["nomCheval"],
                "statut_np":"PARTANT"} for x in raw["participants"]}}),encoding="utf8")
            rows=source_rows(root)["Courses & Prévisions"]
            self.assertEqual(len(rows),4)
            self.assertEqual(sum(x.get("top3_direct_top3")=="OUI" for x in rows.values()),3)
            self.assertEqual(sum(x.get("top3_cotes_top3")=="OUI" for x in rows.values()),3)
            self.assertTrue(all(x.get("ml_modele_statut")=="ML_NON_ENTRAINE" for x in rows.values()))
            self.assertTrue(all(not x.get("ml_score_non_calibre") for x in rows.values()))

    def test_v22_comparaison_trois_top3_avec_arrivee(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            day,code="2026-11-12","R2C2"
            c={"date":day,"code":code,"depart":"2026-11-12T15:00:00+01:00",
               "hippodrome":"Vincennes"}
            def write(rel,data):
                path=root/rel;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(data),encoding="utf-8")
            write(f"sources_pmu/programme_{day}.json",{"programme":[c]})
            write(f"pronostics/{day}_{code}_direct.json",{"top3":[
                {"numero":1},{"numero":2},{"numero":3}]})
            write(f"pronostics/{day}_{code}_cotes.json",{"top3":[
                {"numero":2},{"numero":4},{"numero":5}]})
            write(f"pronostics/{day}_{code}_ml_latest.json",{"statut":"ML_ENTRAINE_NON_CALIBRE",
                "top3":[{"numero":1},{"numero":4},{"numero":5}]})
            write(f"arrivees/{day}_{code}.json",{"source":"PMU_API_PARTICIPANTS",
                "arrivee":[{"numero":1,"rang":1},{"numero":2,"rang":2},{"numero":5,"rang":3}]})
            res=source_rows(root)["Résultats & Analyse"]
            self.assertEqual(len(res),1)
            row=next(iter(res.values()))
            self.assertEqual(row["score_direct"],2)
            self.assertEqual(row["score_cotes"],2)
            self.assertEqual(row["score_ml"],2)
            self.assertEqual(row["arrivee_officielle_numeros"],"1,2,5")
            self.assertEqual(row["statut_evaluation"],"EVALUE")

    def test_preparation_j1_avant_18h(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from pmu_geny.planification_v20_2 import selectionner_courses
        now=datetime(2026,11,11,15,30,tzinfo=ZoneInfo("Europe/Paris"))
        cours=[{"code":"R1C1","depart":"2026-11-12T12:00:00+01:00","priorite_metier":"P1"}]
        selected=selectionner_courses(cours,now,"2026-11-12",[],True,{"courses":{}})
        self.assertEqual([x["code"] for x in selected],["R1C1"])
        after=datetime(2026,11,12,12,1,tzinfo=ZoneInfo("Europe/Paris"))
        self.assertEqual(selectionner_courses(cours,after,"2026-11-12",[],True,{"courses":{}}),cours)
        too_late=datetime(2026,11,12,18,30,tzinfo=ZoneInfo("Europe/Paris"))
        self.assertEqual(selectionner_courses(cours,too_late,"2026-11-12",[],True,{"courses":{}}),[])

    def test_v22_capture_pmu_sans_manifest_avec_historique_cache(self):
        from datetime import datetime, timezone
        from pmu_geny.ml_v19 import snapshot_pmu, dataset
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def write(rel,doc):
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps(doc),encoding='utf-8')
            write('etat_persistant.json',{'chevaux':{'81235':{
                'nom':'Étoile du Nord','statut':'COMPLET'}}})
            perf={'date':'2026-10-31','hippodrome':'Vincennes','discipline':'Attelé',
                  'distance_m':'2700','classement':'2','texte_source':'course test unique'}
            write('historiques/81235/historique_geny.json',
                  {'statut':'COMPLET','nombre_extrait':1,'performances':[perf]})
            course={'date':'2026-11-12','code':'R1C1','depart':'2026-11-12T15:00:00+01:00',
                    'nombre_declares':4,'hippodrome':'Vincennes','distance_m':2700}
            raw={'participants':[
                {'numPmu':1,'nomCheval':'Etoile du Nord','nonPartant':False,'musique':'2a3a4a'},
                {'numPmu':2,'nomCheval':'B','nonPartant':False,'musique':'4a'},
                {'numPmu':3,'nomCheval':'C','nonPartant':False,'musique':'1a'},
                {'numPmu':4,'nomCheval':'D','nonPartant':False,'musique':'Da'}]}
            before=datetime(2026,11,12,12,0,tzinfo=timezone.utc)
            self.assertEqual(snapshot_pmu(root,course,raw,before),'CAPTURE_PMU')
            self.assertEqual(snapshot_pmu(root,course,raw,before),'DEJA_CAPTURE')
            snap=json.loads((root/'ml/instantanes/2026-11-12_R1C1.json').read_text())
            self.assertEqual(snap['historiques_complets_reutilises'],1)
            self.assertEqual(snap['chevaux'][0]['cheval_id'],'81235')
            self.assertIsNotNone(snap['chevaux'][0]['features']['pmu_score_direct'])
            self.assertEqual(snapshot_pmu(root,course,raw,datetime(2026,11,12,14,30,tzinfo=timezone.utc)),'TROP_TARD')
            write('arrivees/2026-11-12_R1C1.json',{
                'verifie_utc':'2026-11-12T15:00:00+00:00',
                'arrivee':[{'numero':1,'rang':1},{'numero':2,'rang':2},{'numero':3,'rang':3}]})
            samples,n=dataset(root)
            self.assertEqual((n,len(samples)),(1,4))

    def test_v22_historiques_canoniques_visibles_sans_export_geny(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def write(rel,doc):
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps(doc),encoding='utf-8')
            write('etat_persistant.json',{'chevaux':{'123456':{
                'nom':'Fleur d Etoile','statut':'COMPLET'}}})
            perf={'date':'2026-10-31','hippodrome':'Vincennes','discipline':'Attelé',
                  'distance_m':'2700','classement':'2','texte_source':'historique source unique'}
            write('historiques/123456/historique_geny.json',
                  {'statut':'COMPLET','performances':[perf]})
            hist=source_rows(root)['Historique chevaux']
            self.assertEqual(len(hist),1)
            row=next(iter(hist.values()))
            self.assertEqual(row['identifiant_cheval'],'123456')
            self.assertEqual(row['cheval'],'Fleur d Etoile')
            self.assertEqual(row['classement'],'2')

    def test_v22_entetes_lisibles_et_moteur_inchange(self):
        from pmu_geny.sync_google_sheets import canonical_headers, DISPLAY_NAMES
        names=['course_key','numero','top3_direct_rang','top3_direct_score',
               'top3_cotes_rang','ml_modele_statut']
        display=[DISPLAY_NAMES[k] for k in names]
        self.assertEqual(canonical_headers(display),names)
        existing=[dict(zip(names,['2026-11-12|VINCENNES|R1C1','1','','','','']))]
        incoming={'a':{'course_key':'2026-11-12|VINCENNES|R1C1','numero':'1',
                       'top3_direct_rang':2,'top3_direct_score':8.5}}
        headers,changes,add=plan_sheet(canonical_headers(display),existing,incoming,'Courses & Prévisions')
        self.assertFalse(add)
        self.assertEqual(len(changes),2)
        self.assertEqual(headers[:len(names)],names)

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
