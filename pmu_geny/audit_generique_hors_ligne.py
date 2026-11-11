"""Audit générique hors réseau des historiques et manifestes persistés en production.

Lecture seule sur un export de pmu-data: pas d'accès Geny, PMU, ni Sheets.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from .controle_historique import classifier

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="reference_pmu")
    p.add_argument("--sortie",default="resultats/audit_generique")
    args=p.parse_args()
    source=Path(args.source);out=Path(args.sortie);out.mkdir(parents=True,exist_ok=True)
    report={"utc":datetime.now(timezone.utc).isoformat(),"mode":"AUDIT_GENERIQUE_HORS_RESEAU",
            "ecriture_production":False,"manifestes":[],"historiques":[],"erreurs":[]}
    manifests=sorted((source/"manifestes").glob("GENY-*.json"))
    histories=sorted((source/"historiques").glob("*/historique_geny.json"))
    report["nb_manifestes"]=len(manifests)
    report["nb_historiques"]=len(histories)
    for path in manifests:
        try:
            doc=json.loads(path.read_text(encoding="utf-8"))
            blocks=doc.get("courses")
            if not isinstance(blocks,list) or len(blocks)!=1:
                raise ValueError("bloc course unique requis")
            block=blocks[0];partants=block.get("partants",[])
            ids=[str(p["id"]) for p in partants]
            nums=[int(p["numero"]) for p in partants]
            expected=int(block["nombre_partants_attendu"])
            valid=len(ids)==expected and len(ids)==len(set(ids)) and len(nums)==len(set(nums))
            report["manifestes"].append({"course_id":block.get("course_id"),
                "partants":len(ids),"attendu":expected,"valid":valid})
            if not valid:report["erreurs"].append(f"{path}: manifeste incoherent")
        except Exception as exc:report["erreurs"].append(f"{path}: {type(exc).__name__}: {exc}")
    counts=Counter()
    for path in histories:
        try:
            doc=json.loads(path.read_text(encoding="utf-8"))
            statut,motifs=classifier(doc)
            counts[statut]+=1
            report["historiques"].append({"id":path.parent.name,"statut":statut,
                "motifs":motifs,"annonce":doc.get("nombre_annonce_geny"),"extrait":doc.get("nombre_extrait")})
        except Exception as exc:
            counts["ERREUR_AUDIT"]+=1
            report["erreurs"].append(f"{path}: {type(exc).__name__}: {exc}")
    report["statuts"]=dict(counts)
    report["resultat"]="AUDIT_EXECUTE" if manifests and histories else "REFERENTIEL_VIDE"
    (out/"rapport.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("BILAN_AUDIT_GENERIQUE "+json.dumps({k:v for k,v in report.items() if k not in ("historiques","manifestes")},ensure_ascii=False),flush=True)
    if report["resultat"]=="REFERENTIEL_VIDE" or report["erreurs"]:
        raise SystemExit(1)

if __name__=="__main__":main()
