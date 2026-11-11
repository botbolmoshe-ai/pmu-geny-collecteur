"""Révalidation hors réseau de deux rangs Geny codés D/R.

Valide le parseur sur les vraies lignes sauvegardées, sans changer leur rang
ni altérer les historiques bruts.
"""
import json
from pathlib import Path
from .collecte_geny_v4 import lire_classement
from .controle_historique import classifier

def main():
    base=Path("archives_test")
    cases=[
        ("2820730", "2025-09-13", "R", 27),
        ("2784364", "2024-11-17", "D", 30),
    ]
    report=[]
    for ident,date,expected,total in cases:
        file=base/"collecte"/ident/"historique_geny.json"
        raw=json.loads(file.read_text(encoding="utf-8"))
        rows=[r for r in raw["performances"] if r["date"]==date]
        if len(rows)!=1:
            raise AssertionError(f"{ident}: date ambiguë")
        original=rows[0]["texte_source"]
        cells=original.split("|")
        actual=lire_classement(cells[4:])
        if actual.upper()!=expected:
            raise AssertionError(f"{ident}: code source {expected}, analyse {actual!r}")
        # Récupérer le code d'origine, sans construire un rang numérique.
        rows[0]["classement"]=actual
        statut,motifs=classifier(raw)
        if statut!="COMPLET" or len(raw["performances"])!=total:
            raise AssertionError(f"{ident}: {statut} ({motifs})")
        report.append({"id":ident,"code_conserve":actual,"performances":total,"statut":statut})
    result=Path("resultats/validation_codes_geny.json")
    result.parent.mkdir(exist_ok=True,parents=True)
    result.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("VALIDATION_CODES_GENY "+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
