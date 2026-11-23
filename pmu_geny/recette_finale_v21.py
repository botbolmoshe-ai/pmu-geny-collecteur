"""Recette V21 sans écriture : cohérence du registre et import confirmé.

Ne simule pas des prévisions ni l'exhaustivité des arrivées.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .audit_generique_hors_ligne import main as _unused  # module d'audit déjà présent
from .controle_historique import classifier
from .reprise_historiques_v21 import HORSES, EXPECTED_PERFS

PARTIELS_CONNU = frozenset({"2905469","2907579","2907581"})

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="reference_pmu")
    p.add_argument("--rapport",default="resultats/v21/recette_finale.json")
    p.add_argument(
        "--registre-evolutif", action="store_true",
        help="Traiter le total de l'import initial comme un minimum pour le registre actif.",
    )
    a=p.parse_args()
    cache=Path(a.source)
    problems=[]
    rows=[]
    complete=set()
    partial=set()
    states={}
    try:
        journal=read(cache/"etat_persistant.json")
        states=journal.get("chevaux",{})
        if journal.get("version")!=1 or not isinstance(states,dict):
            problems.append("JOURNAL_VERSION_OU_SCHEMA_INVALIDE")
    except (OSError,ValueError,TypeError) as exc:
        problems.append("JOURNAL_ILLISIBLE:"+str(exc))
    files=sorted((cache/"historiques").glob("*/historique_geny.json"))
    validated=0
    for f in files:
        ident=f.parent.name
        try:
            doc=read(f)
            status,motifs=classifier(doc)
            if status=="COMPLET":
                complete.add(ident)
            else:
                partial.add(ident)
            if ident in HORSES:
                validated+=len(doc.get("performances",[]))
                if status!="COMPLET":
                    problems.append(f"IMPORT_INCOMPLET:{ident}:{status}")
                if str(states.get(ident,{}).get("statut"))!="COMPLET":
                    problems.append(f"JOURNAL_IMPORT_NON_COMPLET:{ident}")
                if states.get(ident,{}).get("nombre_extrait")!=doc.get("nombre_extrait"):
                    problems.append(f"JOURNAL_COMPTAGE_INCOHERENT:{ident}")
                if not (f.parent/"historique_geny.csv").is_file():
                    problems.append(f"CSV_ABSENT:{ident}")
            rows.append({"id":ident,"statut":status,"motifs":motifs,
                         "annonce":doc.get("nombre_annonce_geny"),
                         "extrait":doc.get("nombre_extrait")})
        except (ValueError,TypeError,OSError) as exc:
            problems.append(f"FICHIER_ILLISIBLE:{ident}:{exc}")
    missing=set(HORSES)-complete
    if missing:
        problems.append("17_HISTORIQUES_NON_VALIDES:"+",".join(sorted(missing)))
    if validated < EXPECTED_PERFS or (validated > EXPECTED_PERFS and not a.registre_evolutif):
        problems.append(f"PERFORMANCES_IMPORTEES:{validated}/{EXPECTED_PERFS}")
    # Les 3 cas partiels sont antérieurs : signalés et tolérés pour cette recette.
    unexpected=partial-PARTIELS_CONNU
    if unexpected:
        problems.append("NOUVEAUX_PARTIELS:"+",".join(sorted(unexpected)))
    manifests=list((cache/"manifestes").glob("GENY-*.json"))
    if not manifests:problems.append("MANIFESTES_ABSENTS")
    result={"date_utc":datetime.now(timezone.utc).isoformat(),"mode":"LECTURE_SEULE",
            "resultat":"CONFORME_PERIMETRE_HISTORIQUES" if not problems else "NON_CONFORME",
            "nombre_historiques":len(files),"historiques_complets":len(complete),
            "historiques_partiels":sorted(partial),"manifestes":len(manifests),
            "chevaux_importes_valides":len(set(HORSES)&complete),
            "performances_importees":validated,"problemes":problems,
            "limitations":["3 historiques partiels preexistants à investiguer",
                           "Arrivees et bilans non garantis par cette recette hors ligne",
                           "Aucune nouvelle collecte Geny/PMU ni ecriture Google Sheets"]}
    output=Path(a.rapport)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RECETTE_FINALE_V21 "+json.dumps(result,ensure_ascii=False),flush=True)
    if problems:raise SystemExit(1)

if __name__=="__main__":
    main()
