"""Classer un historique Geny selon son exhaustivite et la qualite des lignes.

Pas d'acces reseau : fonction pure utilisable avec les resultats V4/V6.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

PARTIELS = frozenset({"PARTIEL_A_CONTROLER", "PARTIEL_HISTORIQUE", "DONNEES_INCOMPLETES", "DONNEES_INCOHERENTES"})


def classifier(result: dict[str, Any]) -> tuple[str, list[str]]:
    statut = str(result.get("statut", ""))
    if statut in {"ACCES_LIMITE_429", "ACCES_REFUSE_403", "ACCES_INDISPONIBLE", "ERREUR_NAVIGATION", "ERREUR"}:
        return statut, [statut]
    expected, extracted = result.get("nombre_annonce_geny"), result.get("nombre_extrait")
    rows = result.get("performances")
    reasons: list[str] = []
    if expected is None or not isinstance(expected, int) or not isinstance(extracted, int):
        reasons.append("NB_COURSES_NON_VERIFIABLE")
        return "PARTIEL_HISTORIQUE", reasons
    if extracted != expected:
        reasons.append(f"NB_COURSES_DIFFERENT:{extracted}/{expected}")
        return "PARTIEL_HISTORIQUE", reasons
    if not isinstance(rows, list) or len(rows) != extracted:
        reasons.append("LIGNES_DETAIL_INDISPONIBLES_OU_INCOHERENTES")
        return "DONNEES_INCOHERENTES", reasons
    # Dates seules sont insuffisantes comme cle universelle ; pour une meme
    # date et un meme hippodrome, la repetition est en revanche suspecte.
    keys = [(str(r.get("date", "")).strip(), str(r.get("hippodrome", "")).strip().casefold()) for r in rows]
    dupl = sum(n - 1 for n in Counter(keys).values() if n > 1)
    if dupl or result.get("dates_uniques") is False:
        reasons.append(f"DOUBLONS_OU_DATES_REPETEES:{dupl}")
        return "DONNEES_INCOHERENTES", reasons
    mandatory = ("date", "hippodrome", "discipline", "distance_m", "classement")
    missing = {field: sum(not str(r.get(field, "")).strip() for r in rows) for field in mandatory}
    reasons.extend(f"CHAMP_MANQUANT:{field}:{n}" for field, n in missing.items() if n)
    if reasons:
        return "DONNEES_INCOMPLETES", reasons
    # La detection de chrono manquant n'est pas une anomalie obligatoire :
    # certaines performances n'ont aucun chrono affiche par Geny.
    return "COMPLET", []
