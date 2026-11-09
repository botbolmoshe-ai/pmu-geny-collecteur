"""Adaptateur réutilisable autour du collecteur Geny V4 testé en local.

Chaque cheval est extrait dans un sous-dossier propre. Le code de sortie du
collecteur V4 est conservé : 0 complet, 1 partiel, 2 erreur.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from .collecte_geny_v4 import main as _v4_main


def extraire_cheval(url: str, identifiant: str, sortie: Path) -> dict[str, Any]:
    import sys
    if not re.fullmatch(r"\d{4,15}", str(identifiant)):
        raise ValueError("Identifiant cheval invalide")
    if not re.fullmatch(r"https://www\.geny\.com/cheval/[A-Za-z0-9_\-/%]+", url):
        raise ValueError("URL Geny cheval invalide")
    folder = sortie / str(identifiant)
    folder.mkdir(parents=True, exist_ok=True)
    old_argv = sys.argv[:]
    try:
        sys.argv = ["collecte_geny_v4.py", "--url", url, "--sortie", str(folder), "--headless"]
        code = _v4_main()
    finally:
        sys.argv = old_argv
    path = folder / "historique_geny.json"
    limitation = folder / 'etat_collecte.json'
    if code == 3 and limitation.exists():
        result = json.loads(limitation.read_text(encoding='utf-8'))
        result.setdefault('nombre_extrait', 0)
    elif code == 3:
        result = {'statut': 'ACCES_LIMITE_429', 'nombre_extrait': 0, 'source_url': url}
    elif path.exists():
        result = json.loads(path.read_text(encoding="utf-8"))
    else:
        result = {"statut": "ERREUR_NAVIGATION", "nombre_extrait": 0, "source_url": url}
    result["identifiant_cheval"] = str(identifiant)
    result["code_retour"] = code
    return result
