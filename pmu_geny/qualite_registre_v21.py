"""Controle qualite du registre PMU avant ou apres synchronisation.
Ne modifie aucune donnee; distingue champs manquants et predicteurs absents.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from .sync_google_sheets import source_rows, limiter_cours_registre

FIELDS_ACTUELS=("driver_jockey","entraineur","proprietaire","ferrure")
LEVELS=("top3_direct_top3","top3_cotes_top3","secours_top3","baseline_top3","baseline_final_top3","ml_top3")

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
                        "top3_direct_disponible":tiers["top3_direct_top3"]==3,
                        "top3_cotes_disponible":tiers["top3_cotes_top3"]==3,
                        "arrivee_renseignee":sum(bool(str(p.get("arrivee_rang","")).strip()) for p in participants)})
    # Verifier le veritable etat du moteur, y compris les courses sans export Geny.
    orchestration=Path(cache)/"orchestration"
    documents=sorted(orchestration.glob("????-??-??.json")) if orchestration.exists() else []
    dernier={}
    if documents:
        try:dernier=json.loads(documents[-1].read_text(encoding="utf-8"))
        except (OSError,ValueError):dernier={}
    fiches=dernier.get("courses",{})
    etats={}
    for course_code,fiche in fiches.items():
        if not isinstance(fiche,dict):continue
        etats[course_code]={
            "traitement":fiche.get("traitement","NON_TRAITE"),
            "association_geny":fiche.get("identifiant_geny") or "NON_ASSOCIE",
            "prevision":fiche.get("statut_prevision","TOP3_NON_CALCULE"),
            "ml":fiche.get("statut_ml","ML_NON_CALCULE"),
            "arrivee":fiche.get("statut_arrivee","ARRIVEE_NON_VERIFIEE"),
            "motif_attente":fiche.get("motif_attente_geny","")}
    diagnostic_traitement={
        "date":dernier.get("date",""),
        "courses_suivies":len(etats),
        "top3_figes":sum(v["prevision"] in ("FIGE_BASELINE_EXPERIMENTALE","DEJA_FIGE") for v in etats.values()),
        "previsions_donnees_insuffisantes":sum(v["prevision"]=="DONNEES_INSUFFISANTES" for v in etats.values()),
        "sans_geny":sum(v["association_geny"]=="NON_ASSOCIE" for v in etats.values()),
        "arrivees_recues":sum(v["arrivee"] in ("ARRIVEE_ENREGISTREE","ARRIVEE_DEJA_ENREGISTREE") for v in etats.values()),
        "details":etats}
    result={"date_debut":debut,"courses":courses,"diagnostic_traitement":diagnostic_traitement,
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
