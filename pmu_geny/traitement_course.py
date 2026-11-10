"""Orchestrateur pilote : contrôle Geny séparé du traitement global des courses.

Un refus 403 ou une limitation 429 suspend SEULEMENT la collecte Geny pour le reste du run.
Le bilan reste exploitable par les étapes suivantes (dont TOP3 dégradé).
Ce module ne calcule pas lui-même de pronostic et n'écrit pas Google Sheets.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone, timedelta
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


def traiter(manifest: dict, sortie: Path, max_chevaux: int, etat_path: Path | None = None, cooldown_heures: int = 1) -> dict:
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
    # Un blocage recent impose une periode sans consultation Geny, y compris
    # au premier cheval du prochain run. Cette regle n'essaie pas de contourner
    # les restrictions du site.
    dernier_blocage = etat_persistant.get("dernier_blocage_geny") or {}
    cooldown_actif = False
    if dernier_blocage.get("utc"):
        try:
            debut = datetime.fromisoformat(dernier_blocage["utc"])
            cooldown_actif = datetime.now(timezone.utc) < debut + timedelta(hours=cooldown_heures)
        except (ValueError, TypeError):
            pass
    if cooldown_actif:
        bilan["collecte_geny"] = "DIFFEREE_COOLDOWN"
        print(f"COOLDOWN GENY : pas de requete pendant {cooldown_heures}h apres un 403/429.", flush=True)
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
            # Ne jamais qualifier de COMPlET un cheval si son historique n'est
            # pas également sauvegardé : le journal seul ne suffit pas.
            historique_cache = etat_path.parent / "historiques" / ident / "historique_geny.json"
            if ancien.get("statut") == "COMPLET" and historique_cache.is_file():
                try:
                    snapshot = json.loads(historique_cache.read_text(encoding="utf-8"))
                    if (snapshot.get("nombre_extrait") != ancien.get("nombre_extrait")
                            or snapshot.get("statut") != "COMPLET"):
                        raise ValueError("Historique cache non concordant")
                    dest = sortie / cid / ident
                    dest.mkdir(parents=True, exist_ok=True)
                    for f in historique_cache.parent.glob("historique_geny.*"):
                        shutil.copy2(f, dest / f.name)
                    stats["chevaux"].append({"id": ident, "nom": nom, "statut": "COMPLET",
                        "origine": "CACHE_PERSISTANT", "nombre_extrait": ancien.get("nombre_extrait"),
                        "nombre_annonce_geny": ancien.get("nombre_annonce_geny")})
                    print(f"CACHE : {nom} ({ident}) historique complet conserve et reutilise.", flush=True)
                    continue
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    print(f"CACHE INVALIDE : {nom} - {exc}. Nouvelle collecte requise.", flush=True)
            elif ancien.get("statut") == "COMPLET":
                print(f"CACHE SANS DONNEES : {nom}; controle complet non recevable.", flush=True)
            if ancien.get("statut") == "COMPLET":
                ancien = {}  # marquage ancien sans donnees : autoriser la collecte
            # Une unique nouvelle tentative est permise pour corriger les cas partiels.
            # Les comptes 429 ne consomment pas ce droit de correction.
            reprise_partielle = (ancien.get("statut") in PARTIELS or ancien.get("correction_en_attente", False)) and not ancien.get("correction_tentee", False)
            if ancien.get("statut") not in (None, "ACCES_LIMITE_429", "ACCES_REFUSE_403", "NON_TENTE_ACCES_LIMITE_429", "NON_TENTE_ACCES_REFUSE_403", "NON_TENTE_LIMITE_TEST", "NON_TENTE_COOLDOWN") and not reprise_partielle:
                # Conformément à la règle : les autres erreurs/partiels nécessitent un contrôle ciblé.
                stats["chevaux"].append({"id": ident, "nom": nom, "statut": ancien["statut"],
                    "origine": "CACHE_A_CONTROLER", "nombre_extrait": ancien.get("nombre_extrait"),
                    "nombre_annonce_geny": ancien.get("nombre_annonce_geny"), "motifs": ancien.get("motifs", []), "correction_tentee": ancien.get("correction_tentee", False)})
                print(f"CACHE : {nom} ({ident}) {ancien['statut']}, pas de nouvelle requete automatique.", flush=True)
                continue
            if cooldown_actif:
                stats["chevaux"].append({"id": ident, "nom": nom, "statut": "NON_TENTE_COOLDOWN", "nombre_extrait": None})
                continue
            if collecte_suspendue:
                stats["chevaux"].append({
                    "id": ident, "nom": nom,
                    "statut": "NON_TENTE_ACCES_REFUSE_403" if bilan["collecte_geny"] == "SUSPENDUE_403" else "NON_TENTE_ACCES_LIMITE_429",
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
                # Persister le contenu, pas seulement le statut. Une exécution
                # GitHub Actions ne conserve pas son disque local par défaut.
                if statut == "COMPLET" or statut in PARTIELS:
                    source = sortie / cid / ident
                    dest = etat_path.parent / "historiques" / ident
                    dest.mkdir(parents=True, exist_ok=True)
                    for f in source.glob("historique_geny.*"):
                        shutil.copy2(f, dest / f.name)
                journal[ident] = {**etat, "maj_utc": datetime.now(timezone.utc).isoformat()}
                _ecrire_etat(etat_path, etat_persistant)
                if statut in ("ACCES_LIMITE_429", "ACCES_REFUSE_403"):
                    collecte_suspendue = True
                    cause = "403" if statut == "ACCES_REFUSE_403" else "429"
                    bilan["collecte_geny"] = f"SUSPENDUE_{cause}"
                    etat_persistant["dernier_blocage_geny"] = {"utc": datetime.now(timezone.utc).isoformat(), "code": cause}
                    _ecrire_etat(etat_path, etat_persistant)
                    print(f"Geny refuse ou limite les requetes ({cause}) : suspension de la collecte Geny uniquement.", flush=True)
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
            if item["statut"] in ("NON_TENTE_ACCES_LIMITE_429", "NON_TENTE_ACCES_REFUSE_403", "NON_TENTE_LIMITE_TEST", "NON_TENTE_COOLDOWN"):
                if item["id"] not in journal:
                    journal[item["id"]] = {**item, "maj_utc": datetime.now(timezone.utc).isoformat()}
        _ecrire_etat(etat_path, etat_persistant)
        states = [x["statut"] for x in stats["chevaux"]]
        if cooldown_actif:
            stats["collecte_geny"] = "DIFFEREE_COOLDOWN"
        elif collecte_suspendue:
            stats["collecte_geny"] = bilan["collecte_geny"]
        elif limite_test:
            stats["collecte_geny"] = "LIMITE_TEST_ATTEINTE"
        elif all(x == "COMPLET" for x in states):
            stats["collecte_geny"] = "COMPLETE"
        else:
            stats["collecte_geny"] = "TERMINEE_AVEC_ECARTS"
        stats["top3_mode_recommande"] = "DEGRADE" if any(x != "COMPLET" for x in states) else "COMPLET"
        _save_bilan(sortie, bilan)
    if not collecte_suspendue and not cooldown_actif:
        bilan["collecte_geny"] = "LIMITE_TEST_ATTEINTE" if limite_test else "TERMINEE"
    _save_bilan(sortie, bilan)
    return bilan


def main() -> None:
    p = argparse.ArgumentParser(description="Collecte Geny par cheval, sans bloquer la course en cas de 429")
    p.add_argument("--manifest", default="courses_test.json")
    p.add_argument("--sortie", default="resultats")
    p.add_argument("--max-chevaux", type=int, default=14)
    p.add_argument("--etat", default="cache_pmu/etat_persistant.json", help="Journal des chevaux entre executions")
    p.add_argument("--cooldown-heures", type=int, default=1, help="Minimum d heures sans demande Geny apres un refus")
    args = p.parse_args()
    if args.cooldown_heures < 1:
        p.error("--cooldown-heures >= 1")
    if args.max_chevaux < 1:
        p.error("--max-chevaux >= 1")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    bilan = traiter(manifest, Path(args.sortie), args.max_chevaux, Path(args.etat), args.cooldown_heures)
    for c in bilan["courses"]:
        print(f"BILAN {c['course_id']}: COLLECTE={c['collecte_geny']} / COURSE={c['traitement_course']} / TOP3 RECOMMANDE={c['top3_mode_recommande']}", flush=True)
        for horse in c["chevaux"]:
            print(f"  {horse['nom']}: {horse['statut']} ({horse.get('nombre_extrait')}/{horse.get('nombre_annonce_geny')})", flush=True)


if __name__ == "__main__":
    main()
