"""Pilote indépendant: manifeste et historique de deux chevaux maximum."""
import argparse
import json
import tempfile
from pathlib import Path
from pmu_geny.auto_v18 import BASE, get_json, programme_diagnostic
from pmu_geny.rapprochement_v20_6 import index_programme, rapprocher
from pmu_geny.decouverte_partants import produire_manifest
from pmu_geny.traitement_course import traiter

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default="2026-11-12")
    p.add_argument("--course",default="R1C1")
    p.add_argument("--max-chevaux",type=int,default=2)
    a=p.parse_args()
    if not 1<=a.max_chevaux<=2: p.error("Le pilote autorise 1 ou 2 chevaux")
    target=Path("resultats/test_historique")
    target.mkdir(parents=True,exist_ok=True)
    report={"date":a.date,"course_pmu":a.course,"statut":"NON_EXECUTE"}
    try:
        pmu=get_json(BASE+a.date.replace("-","")[6:]+a.date.replace("-","")[4:6]+a.date.replace("-","")[:4])
        courses,_=programme_diagnostic(pmu,a.date)
        selected=[c for c in courses if c["code"]==a.course]
        if len(selected)!=1: raise RuntimeError("Course PMU introuvable ou hors perimetre")
        course=selected[0]
        with tempfile.TemporaryDirectory(prefix="pmu-history-isolated-") as directory:
            root=Path(directory)
            index=index_programme(root,a.date,root/"etat_persistant.json",ttl_heures=0)
            report["index_geny"]=index.get("statut")
            if index.get("statut")!="OK": raise RuntimeError("Index Geny indisponible")
            decision=rapprocher(course,index["courses"])
            report["rapprochement"]=decision
            if decision["statut"]!="CORRESPONDANCE_CONFIRMEE": raise RuntimeError("Correspondance non confirmee")
            manifest=produire_manifest(decision["url"],"",course["nombre_declares"],root/"manifest.json",target/"diagnostic_decouverte","",root/"etat_persistant.json")
            report["partants_identifies"]=len(manifest["courses"][0]["partants"])
            pilot=json.loads(json.dumps(manifest))
            pilot["courses"][0]["partants"]=pilot["courses"][0]["partants"][:a.max_chevaux]
            pilot["courses"][0]["nombre_partants_attendu"]=a.max_chevaux
            report["chevaux_testes"]=[{"id":x["id"],"nom":x["nom"]} for x in pilot["courses"][0]["partants"]]
            bilan=traiter(pilot,target/"collecte",a.max_chevaux,root/"etat_persistant.json")
            report["bilan"]=bilan
            report["statut"]="TEST_EXECUTE"
    except Exception as exc:
        report["statut"]="ECHEC_OU_BLOCAGE"
        report["erreur"]=f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (target/"rapport.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("BILAN_TEST_HISTORIQUE "+json.dumps({k:v for k,v in report.items() if k!="bilan"},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
