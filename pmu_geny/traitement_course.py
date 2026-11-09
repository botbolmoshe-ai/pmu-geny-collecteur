"""Orchestrateur pilote : contrôle Geny séparé du traitement global des courses.

Une limitation 429 suspend SEULEMENT la collecte Geny pour le reste du run.
Le bilan reste exploitable par les étapes suivantes (dont TOP3 dégradé).
Ce module ne calcule pas lui-même de pronostic et n'écrit pas Google Sheets.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from .extraction_historique_par_cheval import extraire_cheval
from .controle_historique import classifier, PARTIELS


def _save_bilan(sortie: Path, bilan: dict) -> None:
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / "bilan.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")


def _lire_etat(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) and obj.get("version") == 1 else {"version": 1, "chevaux": {}}
    except (FileNotFoundError, ValueError, OSError):
        return {"version": 1, "chevaux": {}}


def _ecrire_etat(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def traiter(manifest: dict, sortie: Path, max_chevaux: int, etat_path: Path | None = None) -> dict:
    courses = manifest.get("courses", [])
    if not isinstance(courses, list) or not courses:
        raise ValueError("Manifeste sans liste 'courses' non vide")
    bilan = {
        "execution_utc": datetime.now(timezone.utc).isoformat(),
        "collecte_geny": "ACTIVE", "traitement_courses": "A_POURSUIVRE",
        "courses": [], "note": "Le calcul TOP3 et l'ecriture Sheets ne sont pas inclus dans ce pilote.",
    }
    if etat_path is None:
        etat_path = sortie / "etat_persistant.json"
    etat_persistant = _lire_etat(etat_path)
    journal = etat_persistant.setdefault("chevaux", {})
    compteur = 0
    collecte_suspendue = False
    limite_test = False
    for course in courses:
        cid = str(course["course_id"])
        partants = course.get("partants", [])
        attendu = course.get("nombre_partants_attendu")
        if not partants or (attendu is not None and len(partants) != int(attendu)):
            raise ValueError(f"Liste de partants invalide pour {cid}")
        ids = [str(x["id"]) for x in partants]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Doublon d'identifiants pour {cid}")
        stats = {
            "course_id": cid, "nombre_partants_attendu": attendu,
            "chevaux": [], "collecte_geny": "EN_COURS",
            "traitement_course": "A_POURSUIVRE", "top3_mode_recommande": None,
        }
        bilan["courses"].append(stats)
        for cheval in partants:
            ident, nom = str(cheval["id"]), cheval.get("nom", "")
            # Identifiant global stable : les historiques se réutilisent entre courses.
            ancien = journal.get(ident, {})
            if ancien.get("statut") == "COMPLET":
                stats["chevaux"].append({"id": ident, "nom": nom, "statut": "COMPLET",
                    "origine": "CACHE_PERSISTANT", "nombre_extrait": ancien.get("nombre_extrait"),
                    "nombre_annonce_geny": ancien.get("nombre_annonce_geny")})
                print(f"CACHE : {nom} ({ident}) historique complet, aucune requete Geny.", flush=True)
                continue
            # Une unique nouvelle tentative est permise pour corriger les cas partiels.
            # Les comptes 429 ne consomment pas ce droit de correction.
            reprise_partielle = (ancien.get("statut") in PARTIELS or ancien.get("correction_en_attente", False)) and not ancien.get("correction_tentee", False)
            if ancien.get("statut") not in (None, "ACCES_LIMITE_429", "NON_TENTE_ACCES_LIMITE_429", "NON_TENTE_LIMITE_TEST") and not reprise_partielle:
                # Conformément à la règle : les autres erreurs/partiels nécessitent un contrôle ciblé.
                stats["chevaux"].append({"id": ident, "nom": nom, "statut": ancien["statut"],
                    "origine": "CACHE_A_CONTROLER", "nombre_extrait": ancien.get("nombre_extrait"),
                    "nombre_annonce_geny": ancien.get("nombre_annonce_geny"), "motifs": ancien.get("motifs", []), "correction_tentee": ancien.get("correction_tentee", False)})
                print(f"CACHE : {nom} ({ident}) {ancien['statut']}, pas de nouvelle requete automatique.", flush=True)
                continue
            if collecte_suspendue:
                stats["chevaux"].append({
                    "id": ident, "nom": nom,
                    "statut": "NON_TENTE_ACCES_LIMITE_429",
                    "nombre_extrait": None,
                })
                continue
            if compteur >= max_chevaux:
                limite_test = True
                stats["chevaux"].append({"id": ident, "nom": nom, "statut": "NON_TENTE_LIMITE_TEST"})
                continue
            print(f"COURSE {cid} / CHEVAL {ident} - {nom}", flush=True)
            try:
                res = extraire_cheval(cheval["url_geny"], ident, sortie / cid)
                statut, motifs = classifier(res)
                etat = {
                    "id": ident, "nom": nom,
                    "statut": statut, "motifs": motifs,
                    "correction_tentee": bool(reprise_partielle and statut != "ACCES_LIMITE_429"),
                    "correction_en_attente": bool(reprise_partielle and statut == "ACCES_LIMITE_429"),
                    "nombre_extrait": res.get("nombre_extrait"),
                    "nombre_annonce_geny": res.get("nombre_annonce_geny"),
                    "code_retour": res.get("code_retour"),
                }
                stats["chevaux"].append(etat)
                journal[ident] = {**etat, "maj_utc": datetime.now(timezone.utc).isoformat()}
                _ecrire_etat(etat_path, etat_persistant)
                if statut == "ACCES_LIMITE_429":
                    collecte_suspendue = True
                    bilan["collecte_geny"] = "SUSPENDUE_429"
                    print("Geny limite les requetes : suspension de la collecte Geny uniquement.", flush=True)
                    print("Le bilan de course reste disponible pour les etapes hors Geny.", flush=True)
            except Exception as exc:
                record = {"id": ident, "nom": nom, "statut": "ERREUR", "erreur": str(exc), "correction_tentee": bool(reprise_partielle)}
                stats["chevaux"].append(record)
                journal[ident] = {**record, "maj_utc": datetime.now(timezone.utc).isoformat()}
                _ecrire_etat(etat_path, etat_persistant)
            compteur += 1
            _save_bilan(sortie, bilan)
            if not collecte_suspendue and compteur < max_chevaux:
                time.sleep(15)  # cadence prudente, non garantie contre une limite 429
        # Les chevaux non tentés lors de cette exécution deviennent re-éligibles
        # à la prochaine exécution ; le blocage 429 reste enregistré.
        for item in stats["chevaux"]:
            if item["statut"] in ("NON_TENTE_ACCES_LIMITE_429", "NON_TENTE_LIMITE_TEST"):
                if item["id"] not in journal:
                    journal[item["id"]] = {**item, "maj_utc": datetime.now(timezone.utc).isoformat()}
        _ecrire_etat(etat_path, etat_persistant)
        states = [x["statut"] for x in stats["chevaux"]]
        if collecte_suspendue:
            stats["collecte_geny"] = "SUSPENDUE_429"
        elif limite_test:
            stats["collecte_geny"] = "LIMITE_TEST_ATTEINTE"
        elif all(x == "COMPLET" for x in states):
            stats["collecte_geny"] = "COMPLETE"
        else:
            stats["collecte_geny"] = "TERMINEE_AVEC_ECARTS"
        stats["top3_mode_recommande"] = "DEGRADE" if any(x != "COMPLET" for x in states) else "COMPLET"
        _save_bilan(sortie, bilan)
    if not collecte_suspendue:
        bilan["collecte_geny"] = "LIMITE_TEST_ATTEINTE" if limite_test else "TERMINEE"
    _save_bilan(sortie, bilan)
    return bilan


def main() -> None:
    p = argparse.ArgumentParser(description="Collecte Geny par cheval, sans bloquer la course en cas de 429")
    p.add_argument("--manifest", default="courses_test.json")
    p.add_argument("--sortie", default="resultats")
    p.add_argument("--max-chevaux", type=int, default=3)
    p.add_argument("--etat", default="cache_pmu/etat_persistant.json", help="Journal des chevaux entre executions")
    args = p.parse_args()
    if args.max_chevaux < 1:
        p.error("--max-chevaux >= 1")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    bilan = traiter(manifest, Path(args.sortie), args.max_chevaux, Path(args.etat))
    for c in bilan["courses"]:
        print(f"BILAN {c['course_id']}: COLLECTE={c['collecte_geny']} / COURSE={c['traitement_course']} / TOP3 RECOMMANDE={c['top3_mode_recommande']}", flush=True)
        for horse in c["chevaux"]:
            print(f"  {horse['nom']}: {horse['statut']} ({horse.get('nombre_extrait')}/{horse.get('nombre_annonce_geny')})", flush=True)


if __name__ == "__main__":
    main()
