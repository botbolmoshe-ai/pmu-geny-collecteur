"""Test borné de deux historiques supplémentaires depuis les URL observées.

Les liens des chevaux proviennent de l'artefact de découverte précédent.
Pas de réouverture du programme Geny ni des 17 partants, pas de Google Sheets.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from .extraction_historique_par_cheval import extraire_cheval
from .controle_historique import classifier

CHEVAUX = (
    (2, "2786432", "Frank Gio"),
    (3, "2790367", "Lionheart"),
)
CHEVAL_RE = re.compile(r"^/cheval/(\d+)(?:-[^/]*)?(?:/course/\d+)?/?$")

def _url_attestee(dir_source: Path, numero: int, identifiant: str) -> str:
    file = dir_source / f"clic_{numero:02d}.json"
    item = json.loads(file.read_text(encoding="utf-8"))
    url = str(item.get("url") or "")
    parsed = urlparse(url)
    match = CHEVAL_RE.fullmatch(parsed.path)
    if (parsed.scheme != "https"
        or parsed.hostname not in ("www.geny.com", "geny.com")
        or not match or match.group(1) != identifiant
        or parsed.query or parsed.fragment):
        raise ValueError(f"URL de cheval non attestee pour n°{numero}: {url!r}")
    return url

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnostic-source", default="precedent/diagnostic_decouverte")
    ap.add_argument("--sortie", default="resultats/test_progressif")
    ap.add_argument("--pause-secondes", type=int, default=30)
    args = ap.parse_args()
    if not 20 <= args.pause_secondes <= 180:
        ap.error("pause-secondes doit etre compris entre 20 et 180")
    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    rapport = {
        "horodatage_utc": datetime.now(timezone.utc).isoformat(),
        "source_precedente": "GitHub Actions #43001015559",
        "course": "R1C1 / GENY-1698061",
        "mode": "REUTILISATION_URLS_SANS_DECOUVERTE",
        "limite": len(CHEVAUX),
        "chevaux": [],
        "statut": "EN_COURS",
    }
    try:
        # Contrôler les deux URL enregistrées AVANT d'interroger Geny.
        urls = [_url_attestee(Path(args.diagnostic_source), no, ident)
                for no, ident, _ in CHEVAUX]
        for i, ((no, ident, nom), url) in enumerate(zip(CHEVAUX, urls)):
            if i:
                time.sleep(args.pause_secondes)
            item = {"numero": no, "id": ident, "nom": nom, "url_source": url}
            try:
                data = extraire_cheval(url, ident, sortie / "collecte")
                statut, motifs = classifier(data)
                item.update({
                    "statut": statut, "motifs": motifs,
                    "nombre_annonce_geny": data.get("nombre_annonce_geny"),
                    "nombre_extrait": data.get("nombre_extrait"),
                    "code_retour": data.get("code_retour"),
                })
            except Exception as exc:
                item.update({"statut": "ERREUR", "erreur": f"{type(exc).__name__}: {exc}"})
            rapport["chevaux"].append(item)
            print("RESULTAT_CHEVAL " + json.dumps(item, ensure_ascii=False), flush=True)
            if item["statut"] in ("ACCES_LIMITE_429", "ACCES_REFUSE_403"):
                rapport["statut"] = "SUSPENDU_REFUS_GENY"
                break
        if rapport["statut"] == "EN_COURS":
            rapport["statut"] = ("TOUS_COMPLETS" if len(rapport["chevaux"]) == len(CHEVAUX)
                                  and all(c["statut"] == "COMPLET" for c in rapport["chevaux"])
                                  else "TERMINE_AVEC_ECARTS")
    except Exception as exc:
        rapport["statut"] = "ECHEC_PREPARATION"
        rapport["erreur"] = f"{type(exc).__name__}: {exc}"
    finally:
        (sortie / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
        print("BILAN_TEST_PROGRESSIF " + json.dumps(rapport, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
