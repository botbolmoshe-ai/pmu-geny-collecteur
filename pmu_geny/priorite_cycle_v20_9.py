"""Arbitrage complet/léger à partir de la préparation métier, non du statut GitHub."""
from datetime import datetime, timedelta, timezone

BLOCAGES_GENY = ("COOLDOWN_GENY", "GENY_BLOQUE")

def evaluer_preparation(courses, etat, now, horizon_heures=6):
    """Contrôle les départs futurs proches, sans inventer de TOP3 après H-1."""
    a_preparer, non_recuperables, bloquees = [], [], []
    pertinentes = 0
    for course in courses:
        try:
            depart = datetime.fromisoformat(course["depart"])
            code = course["code"]
        except (KeyError, TypeError, ValueError):
            continue
        if not now < depart <= now + timedelta(hours=horizon_heures):
            continue
        pertinentes += 1
        record = etat.get("courses", {}).get(code, {})
        reste = (depart - now).total_seconds() / 60
        figement = record.get("statut_prevision") in ("FIGE_BASELINE_EXPERIMENTALE", "DEJA_FIGE")
        if not record.get("identifiant_geny"):
            motif = "MANIFESTE_ABSENT"
        elif record.get("statut_prevision") in ("DONNEES_INSUFFISANTES", "ERREUR_MODELE_PROVISOIRE"):
            motif = record["statut_prevision"]
        elif reste <= 60 and not figement:
            motif = "TOP3_NON_FIGE"
        else:
            continue
        ligne = {"course": code, "motif": motif}
        if reste < 60 and not figement:
            non_recuperables.append(ligne)
        elif record.get("motif_attente_geny") in BLOCAGES_GENY:
            bloquees.append(ligne)
        else:
            a_preparer.append(ligne)
    if not courses or pertinentes == 0:
        statut = "AUCUNE_COURSE_PROCHE_A_CONTROLER"
    elif a_preparer:
        statut = "PREPARATION_INCOMPLETE"
    elif bloquees or non_recuperables:
        statut = "PREPARATION_DEGRADEE"
    else:
        statut = "PREPARATION_VALIDEE"
    return {"statut": statut, "courses_controlees": pertinentes,
            "a_preparer": a_preparer, "non_recuperables": non_recuperables,
            "bloquees": bloquees,
            "manquantes": a_preparer + bloquees + non_recuperables}

def choisir_cycle(courses, etat, now, cycle_demande):
    diagnostic = evaluer_preparation(courses, etat, now)
    # Un blocage Geny connu interdit les requêtes lourdes répétées.
    if cycle_demande == "complet" or diagnostic["a_preparer"]:
        return "complet", diagnostic
    return "leger", diagnostic
