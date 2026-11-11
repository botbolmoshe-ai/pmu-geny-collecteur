"""Décision de cycle fondée sur l'état métier, indépendamment du succès GitHub."""
from datetime import datetime, timedelta

def evaluer_preparation(courses, etat, now, horizon_heures=6):
    """Ne valide que les courses futures dans l'horizon opérationnel.

    Un manque de données n'est jamais assimilé à une préparation réussie.
    Les TOP3 ne sont exigibles que dans leur fenêtre H-1.
    """
    manquantes = []
    pertinentes = []
    for course in courses:
        depart = datetime.fromisoformat(course["depart"])
        if not now < depart <= now + timedelta(hours=horizon_heures):
            continue
        code = course["code"]
        pertinentes.append(code)
        record = etat.get("courses", {}).get(code, {})
        if not record.get("identifiant_geny"):
            manquantes.append({"course": code, "motif": "MANIFESTE_ABSENT"})
        elif record.get("statut_prevision") in ("DONNEES_INSUFFISANTES", "ERREUR_MODELE_PROVISOIRE"):
            manquantes.append({"course": code, "motif": record["statut_prevision"]})
        elif (depart - now) <= timedelta(minutes=60) and record.get("statut_prevision") not in (
            "FIGE_BASELINE_EXPERIMENTALE", "DEJA_FIGE"
        ):
            manquantes.append({"course": code, "motif": "TOP3_NON_FIGE"})
    return {
        "statut": "PREPARATION_VALIDEE" if not manquantes else "PREPARATION_INCOMPLETE",
        "courses_controlees": len(pertinentes),
        "manquantes": manquantes,
    }

def choisir_cycle(courses, etat, now, cycle_demande):
    """Priorité complète si préparation insuffisante; cycle léger sinon."""
    diagnostic = evaluer_preparation(courses, etat, now)
    if cycle_demande == "complet" or diagnostic["statut"] != "PREPARATION_VALIDEE":
        return "complet", diagnostic
    return "leger", diagnostic
