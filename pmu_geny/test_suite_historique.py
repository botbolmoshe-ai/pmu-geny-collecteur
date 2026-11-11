"""Regression du cas Frank Gio et collecte prudente de quatre autres chevaux.

Ne recharge ni index Geny ni manifeste. Utilise uniquement les URLs attestées
dans le diagnostic initial et les données historiques de l'artefact précédent.
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

CHEVAUX=((4,"2820730","Magic Night"),(5,"2790525","Falco Killer Gar"),
         (6,"2784364","Liza Josselyn"),(7,"2818051","Maître Jacques"))
HORSE_RE=re.compile(r"^/cheval/(\d+)(?:-[^/]*)?(?:/course/\d+)?/?$")

def lire_lien(folder, n, ident):
    doc=json.loads((folder/f"clic_{n:02d}.json").read_text(encoding="utf-8"))
    url=doc["url"]; parsed=urlparse(url); match=HORSE_RE.fullmatch(parsed.path)
    if parsed.scheme!="https" or parsed.hostname not in ("www.geny.com","geny.com") or not match or match.group(1)!=ident or parsed.query or parsed.fragment:
        raise ValueError(f"Lien cheval non conforme: {ident}")
    return url

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--liens",default="precedent/diagnostic_decouverte")
    p.add_argument("--historique-frank",default="historique_precedent/collecte/2786432/historique_geny.json")
    p.add_argument("--sortie",default="resultats/test_suite")
    p.add_argument("--pause-secondes",type=int,default=30)
    args=p.parse_args()
    if not 20<=args.pause_secondes<=180: p.error("pause entre 20 et 180 secondes")
    out=Path(args.sortie);out.mkdir(parents=True,exist_ok=True)
    report={"utc":datetime.now(timezone.utc).isoformat(),"course":"R1C1",
            "mode":"QUATRE_FICHES_SANS_REDECOUVERTE","chevaux":[],"statut":"EN_COURS"}
    try:
        frank=json.loads(Path(args.historique_frank).read_text(encoding="utf-8"))
        statut,motifs=classifier(frank)
        rows=[r for r in frank["performances"] if r["date"]=="2026-05-03" and r["hippodrome"].casefold()=="naples"]
        if len(rows)!=2 or len({r["texte_source"] for r in rows})!=2 or statut!="COMPLET" or frank["nombre_extrait"]!=35:
            raise AssertionError(f"Régression Frank Gio: {statut} ({motifs}), lignes Naples={len(rows)}")
        # Un vrai doublon doit rester refusé.
        dupl=json.loads(json.dumps(frank))
        dupl["performances"][3]=dict(dupl["performances"][2])
        statut_double,_=classifier(dupl)
        if statut_double!="DONNEES_INCOHERENTES":
            raise AssertionError("Non-regression: doublon strict non detecte")
        report["frank_gio"]={"statut":statut,"performances":35,"courses_naples_distinctes":2,
                              "doublon_strict_refuse":True}
        print("REGRESSION_FRANK_GIO "+json.dumps(report["frank_gio"],ensure_ascii=False),flush=True)
        liens=[lire_lien(Path(args.liens),n,ident) for n,ident,_ in CHEVAUX]
        for ix,((numero,ident,nom),url) in enumerate(zip(CHEVAUX,liens)):
            if ix: time.sleep(args.pause_secondes)
            rec={"numero":numero,"id":ident,"nom":nom,"url":url}
            try:
                d=extraire_cheval(url,ident,out/"collecte")
                statut,motifs=classifier(d)
                rec.update({"statut":statut,"motifs":motifs,"nombre_annonce_geny":d.get("nombre_annonce_geny"),
                            "nombre_extrait":d.get("nombre_extrait"),"code_retour":d.get("code_retour")})
            except Exception as ex:
                rec.update({"statut":"ERREUR","erreur":f"{type(ex).__name__}: {ex}"})
            report["chevaux"].append(rec)
            print("RESULTAT_CHEVAL "+json.dumps(rec,ensure_ascii=False),flush=True)
            if rec["statut"] in ("ACCES_LIMITE_429","ACCES_REFUSE_403"):
                report["statut"]="SUSPENDU_GENY"
                break
        if report["statut"]=="EN_COURS":
            report["statut"]="TOUS_COMPLETS" if all(x["statut"]=="COMPLET" for x in report["chevaux"]) and len(report["chevaux"])==len(CHEVAUX) else "TERMINE_AVEC_ECARTS"
    except Exception as exc:
        report["statut"]="ECHEC_PREPARATION"
        report["erreur"]=f"{type(exc).__name__}: {exc}"
    finally:
        (out/"rapport.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("BILAN_SUITE_HISTORIQUE "+json.dumps(report,ensure_ascii=False),flush=True)
    if report["statut"]=="ECHEC_PREPARATION":
        raise SystemExit(1)

if __name__=="__main__": main()
