"""V21: reprise contrôlée des 17 historiques Geny testés dans pmu-data.

Les cinq artefacts identifiés sont téléchargés par le workflow manuel.
Le mode validation ne modifie JAMAIS pmu-data. L'import remplace seulement
un historique absent ou non complet; il ne dégrade pas un historique complet.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .controle_historique import classifier
from .collecte_geny_v4 import lire_classement

# IDs observés dans le manifeste Geny 1698061 du 12 novembre.
HORSES = {
    "2788633": "Lombok Jiel",
    "2786432": "Frank Gio",
    "2790367": "Lionheart",
    "2820730": "Magic Night",
    "2790525": "Falco Killer Gar",
    "2784364": "Liza Josselyn",
    "2818051": "Maître Jacques",
    "2806589": "Bullet The Bluesky",
    "2797925": "L'As Desbois",
    "2803002": "Lancier du Goutier",
    "2818957": "Liberté de Choisel",
    "2808004": "Lord du Bassin",
    "2826107": "Madrid Haufor",
    "2818134": "Koogoo Gaagaa",
    "2844554": "Mila des Couperies",
    "2802274": "L'Ecrin d'Or",
    "2820646": "Midway Lady",
}
EXPECTED_PERFS = 465
COLUMNS = ("date","hippodrome","discipline","distance_m","classement","chrono","texte_source")
ARCHIVES = ("unique","progressif","suite","lot1","lot7")
HORSE_PATH = re.compile(r"^/cheval/(\d+)(?:-[^/]*)?(?:/course/1698061)?/?$")

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def validate_url(doc, ident):
    url=str(doc.get("source_url") or "")
    u=urlparse(url)
    match=HORSE_PATH.fullmatch(u.path)
    if not (u.scheme=="https" and u.hostname in ("www.geny.com","geny.com")
            and match and match.group(1)==ident and not u.query and not u.fragment):
        raise ValueError(f"{ident}: URL cheval Geny inattendue {url!r}")

def normalize(doc, ident):
    if not isinstance(doc,dict):
        raise ValueError(f"{ident}: données JSON incorrectes")
    validate_url(doc,ident)
    rows=doc.get("performances")
    if not isinstance(rows,list):
        raise ValueError(f"{ident}: performances absentes")
    # Deux cas observés et testés hors ligne: R et D sont des codes,
    # pas des rangs numériques. On n'invente aucun autre classement.
    for row in rows:
        if str(row.get("classement") or "").strip():
            continue
        parts=str(row.get("texte_source") or "").split("|")
        if len(parts)>=7:
            result=lire_classement(parts[4:])
            if result in ("D","R"):
                row["classement"]=result
    status,reasons=classifier(doc)
    if status!="COMPLET":
        raise ValueError(f"{ident}: historique non complet: {status} {reasons}")
    doc["statut"]="COMPLET"
    doc["complet"]=True
    doc["champs_detail_valides"]=True
    return doc

def audit_sources(root):
    found={}
    origins={}
    for bucket in ARCHIVES:
        folder=root/bucket
        if not folder.is_dir():
            raise FileNotFoundError(f"Archive requise absente: {folder}")
        for path in sorted(folder.rglob("historique_geny.json")):
            ident=path.parent.name
            if ident not in HORSES:
                raise ValueError(f"Cheval non autorisé dans {bucket}: {ident}")
            if ident in found:
                raise ValueError(f"Historique répété pour {ident} (archives {origins[ident]} et {bucket})")
            found[ident]=normalize(read_json(path),ident)
            origins[ident]=bucket
    if set(found)!=set(HORSES):
        raise ValueError(f"17 historiques requis; manquants={sorted(set(HORSES)-set(found))}")
    n=sum(len(doc["performances"]) for doc in found.values())
    if n!=EXPECTED_PERFS:
        raise ValueError(f"465 performances attendues; {n} validées")
    return found,origins,n

def import_one(cache,ident,doc,apply):
    dest=cache/"historiques"/ident
    oldfile=dest/"historique_geny.json"
    if oldfile.is_file():
        previous=read_json(oldfile)
        prevstatus,_=classifier(previous)
        if prevstatus=="COMPLET":
            return "CONSERVE_COMPLET_EXISTANT"
    if not apply:
        return "IMPORT_PREVU"
    dest.mkdir(parents=True,exist_ok=True)
    jf=dest/"historique_geny.json"
    tmp=jf.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(jf)
    csvfile=dest/"historique_geny.csv"
    tmpcsv=csvfile.with_suffix(".csv.tmp")
    with tmpcsv.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS,delimiter=";",extrasaction="ignore")
        writer.writeheader()
        writer.writerows(doc["performances"])
    tmpcsv.replace(csvfile)
    return "IMPORTE_COMPLET"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archives",default="archives")
    p.add_argument("--cache",default="reference_pmu")
    p.add_argument("--rapport",default="resultats/reprise_v21/rapport.json")
    p.add_argument("--appliquer",action="store_true")
    a=p.parse_args()
    cache=Path(a.cache)
    if not cache.is_dir() or not (cache/"etat_persistant.json").is_file():
        raise SystemExit("État durable absent, import interdit")
    report={"date_utc":datetime.now(timezone.utc).isoformat(),
            "action":"IMPORT" if a.appliquer else "SIMULATION","source":"ARTIFACTS_VALIDES_GENY_1698061",
            "chevaux":[], "nombre_attendu":17, "performances_attendues":EXPECTED_PERFS}
    output=Path(a.rapport)
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        docs,origins,total=audit_sources(Path(a.archives))
        state=read_json(cache/"etat_persistant.json")
        if state.get("version")!=1 or not isinstance(state.get("chevaux"),dict):
            raise ValueError("Journal de production incompatible")
        # Vérifier TOUS les fichiers avant la moindre écriture.
        for ident,doc in docs.items():
            oldfile=cache/"historiques"/ident/"historique_geny.json"
            if oldfile.is_file():
                old=read_json(oldfile)
                if not isinstance(old,dict):raise ValueError(f"Historique existant invalide pour {ident}")
        for ident,doc in docs.items():
            disposition=import_one(cache,ident,doc,a.appliquer)
            report["chevaux"].append({"id":ident,"nom":HORSES[ident],"archive":origins[ident],
                  "nombre":len(doc["performances"]),"action":disposition})
            if a.appliquer and disposition=="IMPORTE_COMPLET":
                previous=state["chevaux"].get(ident,{})
                state["chevaux"][ident]={**previous,"id":ident,"nom":HORSES[ident],
                    "statut":"COMPLET","motifs":[],"nombre_extrait":doc["nombre_extrait"],
                    "nombre_annonce_geny":doc["nombre_annonce_geny"],"maj_utc":datetime.now(timezone.utc).isoformat(),
                    "origine":"IMPORT_ARTEFACT_TEST_V21"}
        if a.appliquer:
            stfile=cache/"etat_persistant.json"
            tmp=stfile.with_suffix(".tmp")
            tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
            tmp.replace(stfile)
        report["performances_valides"]=total
        report["imports"]=sum(x["action"]=="IMPORTE_COMPLET" for x in report["chevaux"])
        report["conserves"]=sum(x["action"]=="CONSERVE_COMPLET_EXISTANT" for x in report["chevaux"])
        report["resultat"]="OK"
    except Exception as exc:
        report["resultat"]="ECHEC"
        report["erreur"]=f"{type(exc).__name__}: {exc}"
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("BILAN_REPRISE_V21 "+json.dumps(report,ensure_ascii=False),flush=True)
    if report["resultat"]!="OK":
        raise SystemExit(1)

if __name__=="__main__":main()
