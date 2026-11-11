"""Controle qualite du registre PMU avant ou apres synchronisation.
Ne modifie aucune donnee; distingue champs manquants et predicteurs absents.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from .sync_google_sheets import source_rows, limiter_cours_registre

FIELDS_ACTUELS=("driver_jockey","entraineur","proprietaire","ferrure")
LEVELS=("secours_top3","baseline_top3","baseline_final_top3","ml_top3")

def evaluer(cache, debut="2026-11-12"):
    rows=limiter_cours_registre(source_rows(Path(cache)),debut)
    buckets=defaultdict(list)
    for r in rows["Courses & Prévisions"].values():
        buckets[r["course_key"]].append(r)
    courses=[]
    for key,participants in sorted(buckets.items()):
        nb=len(participants)
        absent={field:sum(not str(p.get(field,"")).strip() for p in participants) for field in FIELDS_ACTUELS}
        tiers={level:sum(str(p.get(level,"")).strip().upper()=="OUI" for p in participants) for level in LEVELS}
        courses.append({"course_key":key,"partants":nb,"champs_absents":absent,
                        "paliers_top3":tiers,
                        "top3_historique_fige":tiers["baseline_top3"]==3,
                        "top3_ml_disponible":tiers["ml_top3"]==3,
                        "arrivee_renseignee":sum(bool(str(p.get("arrivee_rang","")).strip()) for p in participants)})
    result={"date_debut":debut,"courses":courses,
            "nombre_courses":len(courses),"nombre_partants":sum(x["partants"] for x in courses),
            "nombre_bilans":len(rows["Résultats & Analyse"]),
            "nombre_performances_historiques":len(rows["Historique chevaux"]),
            "attention":"Un cycle GitHub reussi ne prouve pas qu'un TOP3 a ete calcule."}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cache",default="cache_pmu")
    p.add_argument("--debut",default="2026-11-12")
    p.add_argument("--sortie",default="")
    a=p.parse_args()
    doc=evaluer(a.cache,a.debut)
    content=json.dumps(doc,ensure_ascii=False,indent=2)
    print("QUALITE_REGISTRE_V21 "+json.dumps(doc,ensure_ascii=False))
    if a.sortie:
        out=Path(a.sortie);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(content,encoding="utf-8")

if __name__=="__main__":
    main()
