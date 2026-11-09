"""Orchestrateur séquentiel : une course, puis chaque cheval dans l'ordre.

Entrée : manifest JSON (liste de courses et partants). Sortie : JSON de bilan.
Pas d'écriture Sheets dans la phase pilote. Ne fait aucun pronostic.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from .extraction_historique_par_cheval import extraire_cheval


def traiter(manifest: dict, sortie: Path, max_chevaux: int) -> dict:
    courses = manifest.get("courses", [])
    if not courses or not isinstance(courses, list):
        raise ValueError("Le manifeste doit contenir une liste 'courses' non vide")
    total = 0
    bilan = {"execution_utc": datetime.now(timezone.utc).isoformat(), "courses": []}
    for course in courses:
        cid = str(course["course_id"])
        partants = course.get("partants", [])
        if not partants:
            raise ValueError(f"Aucun partant pour {cid}")
        expected = course.get("nombre_partants_attendu")
        if expected is not None and len(partants) != int(expected):
            raise ValueError(f"Liste des partants incomplète pour {cid}: {len(partants)}/{expected}")
        ids = [str(c["id"]) for c in partants]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Identifiants de chevaux en doublon pour {cid}")
        stats = {"course_id": cid, "nombre_partants_attendu": expected, "chevaux": [], "traitement": "EN_COURS"}
        bilan["courses"].append(stats)
        for cheval in partants:
            if total >= max_chevaux:
                stats["traitement"] = "LIMITE_TEST_ATTEINTE"
                break
            ident = str(cheval["id"])
            print(f"COURSE {cid} / CHEVAL {ident} - {cheval.get('nom', '')}", flush=True)
            try:
                res = extraire_cheval(cheval["url_geny"], ident, sortie / cid)
                stats["chevaux"].append({"id": ident, "nom": cheval.get("nom"), "statut": res.get("statut"), "nombre_extrait": res.get("nombre_extrait"), "nombre_annonce_geny": res.get("nombre_annonce_geny"), "code_retour": res.get("code_retour")})
            except Exception as e:
                stats["chevaux"].append({"id": ident, "nom": cheval.get("nom"), "statut": "ERREUR", "erreur": str(e)})
            total += 1
            time.sleep(2)  # Politesse vis-à-vis du site, pas de requêtes parallèles.
            sortie.mkdir(parents=True, exist_ok=True)
            (sortie / "bilan.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            stats["traitement"] = "TERMINE_AVEC_ECARTS" if any(x["statut"] != "COMPLET" for x in stats["chevaux"]) else "TERMINE_COMPLET"
            continue
        break
    (sortie / "bilan.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")
    return bilan


def main() -> None:
    p = argparse.ArgumentParser(description="Extraction Geny : courses et chevaux séquentiels")
    p.add_argument("--manifest", default="courses_test.json")
    p.add_argument("--sortie", default="resultats")
    p.add_argument("--max-chevaux", type=int, default=1)
    args = p.parse_args()
    if args.max_chevaux < 1:
        p.error("--max-chevaux >= 1")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    bilan = traiter(manifest, Path(args.sortie), args.max_chevaux)
    for course in bilan["courses"]:
        print(f"BILAN {course['course_id']}: {course['traitement']}", flush=True)
        for ch in course["chevaux"]:
            print(f"  {ch['nom']}: {ch['statut']} ({ch.get('nombre_extrait')}/{ch.get('nombre_annonce_geny')})", flush=True)


if __name__ == "__main__":
    main()
