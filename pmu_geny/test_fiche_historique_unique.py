"""Test ciblé Geny, sans découverte préalable et sans écriture de production.

Ne consulte qu'une fiche cheval, à partir d'un identifiant/URL vérifiés dans
l'exécution historique du 11/11/2026. Les rapports sont publiés en artefacts.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .extraction_historique_par_cheval import extraire_cheval
from .controle_historique import classifier

CHEVAUX_VERIFIES = {
    "2788633": {
        "nom": "Lombok Jiel",
        "url": "https://www.geny.com/cheval/2788633-lombok-jiel/course/1698061",
        "course": "GENY-1698061",
    },
    "2786432": {
        "nom": "Frank Gio",
        "url": "https://www.geny.com/cheval/2786432-frank-gio/course/1698061",
        "course": "GENY-1698061",
    },
}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cheval-id", choices=sorted(CHEVAUX_VERIFIES), default="2788633")
    p.add_argument("--sortie", default="resultats/test_fiche_historique")
    args = p.parse_args()
    target = Path(args.sortie)
    target.mkdir(parents=True, exist_ok=True)
    cheval = CHEVAUX_VERIFIES[args.cheval_id]
    bilan = {
        "horodatage_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "UNE_FICHE_SANS_DECOUVERTE",
        "course": cheval["course"],
        "cheval_id": args.cheval_id,
        "nom": cheval["nom"],
        "source_url": cheval["url"],
        "statut": "NON_EXECUTE",
        "requetes_decouverte": 0,
        "politique_429": "ARRET_SANS_REESSAI",
    }
    try:
        data = extraire_cheval(cheval["url"], args.cheval_id, target / "collecte")
        statut, motifs = classifier(data)
        bilan.update({
            "statut": statut,
            "motifs": motifs,
            "nombre_annonce_geny": data.get("nombre_annonce_geny"),
            "nombre_extrait": data.get("nombre_extrait"),
            "code_retour": data.get("code_retour"),
            "controle_http": data.get("http"),
            "reussi": statut == "COMPLET",
        })
    except Exception as exc:
        bilan.update({"statut": "ERREUR", "erreur": f"{type(exc).__name__}: {exc}", "reussi": False})
    finally:
        (target / "rapport.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")
        print("BILAN_FICHE_UNIQUE " + json.dumps(bilan, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
