"""Collecte isolée des dix chevaux restants de Vincennes R1C1, en trois lots.

Les URL viennent uniquement de l'artefact du manifeste vérifié le 11/11.
Aucune redécouverte, aucun accès Google Sheets, aucune écriture pmu-data.
"""
from __future__ import annotations
import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from .controle_historique import classifier
from .extraction_historique_par_cheval import extraire_cheval

LOTS = {
    "1": ((8,"2806589","Bullet The Bluesky"),(9,"2797925","L'As Desbois"),(10,"2803002","Lancier du Goutier")),
    "2": ((11,"2818957","Liberté de Choisel"),(12,"2808004","Lord du Bassin"),(13,"2826107","Madrid Haufor")),
    "3": ((14,"2818134","Koogoo Gaagaa"),(15,"2844554","Mila des Couperies"),(16,"2802274","L'Ecrin d'Or"),(17,"2820646","Midway Lady")),
}
HORSE_RE = re.compile(r"^/cheval/(\d+)(?:-[^/]*)?(?:/course/\d+)?/?$")

def url_attestee(folder, n, ident):
    doc=json.loads((folder/f"clic_{n:02d}.json").read_text(encoding="utf-8"))
    url=str(doc.get("url") or "")
    u=urlparse(url)
    m=HORSE_RE.fullmatch(u.path)
    if u.scheme!="https" or u.hostname not in ("www.geny.com","geny.com") or not m or m.group(1)!=ident or u.query or u.fragment:
        raise ValueError(f"URL non vérifiable pour le cheval n°{n}")
    return url

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lot",choices=sorted(LOTS)+["tous"],required=True)
    ap.add_argument("--liens",default="precedent/diagnostic_decouverte")
    ap.add_argument("--sortie",default="resultats/test_reste")
    ap.add_argument("--pause-secondes",type=int,default=30)
    args=ap.parse_args()
    if not 20<=args.pause_secondes<=180: ap.error("pause attendue entre 20 et 180 secondes")
    out=Path(args.sortie)/f"lot_{args.lot}"
    out.mkdir(parents=True,exist_ok=True)
    chevaux=LOTS["2"]+LOTS["3"] if args.lot=="tous" else LOTS[args.lot]
    bilan={"date":"2026-11-12","course":"R1C1","lot":args.lot,
           "horodatage_utc":datetime.now(timezone.utc).isoformat(),
           "mode":"SANS_REDECOUVERTE","chevaux_attendus":len(chevaux),
           "chevaux":[],"statut":"EN_COURS"}
    try:
        # Vérifier les URL avant la première requête.
        urls=[url_attestee(Path(args.liens),no,ident) for no,ident,_ in chevaux]
        for i,((no,ident,nom),url) in enumerate(zip(chevaux,urls)):
            if i: time.sleep(args.pause_secondes)
            entry={"numero":no,"id":ident,"nom":nom,"url":url}
            try:
                res=extraire_cheval(url,ident,out/"collecte")
                statut,motifs=classifier(res)
                entry.update({"statut":statut,"motifs":motifs,
                              "nombre_annonce_geny":res.get("nombre_annonce_geny"),
                              "nombre_extrait":res.get("nombre_extrait"),
                              "code_retour":res.get("code_retour")})
            except Exception as exc:
                entry.update({"statut":"ERREUR","erreur":f"{type(exc).__name__}: {exc}"})
            bilan["chevaux"].append(entry)
            print("RESULTAT_CHEVAL "+json.dumps(entry,ensure_ascii=False),flush=True)
            # Tout refus ou erreur d'accès incertaine suspend le lot.
            if entry["statut"] in ("ACCES_LIMITE_429","ACCES_REFUSE_403","ACCES_INDISPONIBLE","ERREUR_NAVIGATION","ERREUR"):
                bilan["statut"]="SUSPENDU_ACCES_OU_ERREUR"
                break
        if bilan["statut"]=="EN_COURS":
            bilan["statut"]="TOUS_COMPLETS" if len(bilan["chevaux"])==len(chevaux) and all(x["statut"]=="COMPLET" for x in bilan["chevaux"]) else "TERMINE_AVEC_ECARTS"
    except Exception as exc:
        bilan["statut"]="ECHEC_PREPARATION"
        bilan["erreur"]=f"{type(exc).__name__}: {exc}"
    finally:
        (out/"rapport.json").write_text(json.dumps(bilan,ensure_ascii=False,indent=2),encoding="utf-8")
        print("BILAN_LOT_HISTORIQUE "+json.dumps(bilan,ensure_ascii=False),flush=True)
    if bilan["statut"]=="ECHEC_PREPARATION":
        raise SystemExit(1)

if __name__=="__main__": main()
