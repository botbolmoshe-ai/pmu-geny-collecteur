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
    # Plusieurs performances le meme jour au meme hippodrome peuvent etre
    # reelles (cas Frank Gio, Naples, 03/05/2026, chronos distincts).
    # Ne jamais fusionner ces lignes, ni deduire un doublon de la seule date.
    # La ligne source complete sert de preuve primaire de non-duplication.
    # Sans source, employer les attributs disponibles et rester prudent.
    def cle_ligne(r):
        texte = " ".join(str(r.get("texte_source") or "").casefold().split())
        if texte:
            return ("source", texte)
        return ("champs",) + tuple(
            str(r.get(k) or "").strip().casefold()
            for k in ("date", "hippodrome", "discipline", "distance_m", "classement", "chrono")
        )
    counts = Counter(cle_ligne(r) for r in rows)
    dupl = sum(n - 1 for n in counts.values() if n > 1)
    if dupl:
        reasons.append(f"LIGNES_IDENTIQUES_REPETEES:{dupl}")
        return "DONNEES_INCOHERENTES", reasons
    mandatory = ("date", "hippodrome", "discipline", "distance_m", "classement")
    missing = {field: sum(not str(r.get(field, "")).strip() for r in rows) for field in mandatory}
    reasons.extend(f"CHAMP_MANQUANT:{field}:{n}" for field, n in missing.items() if n)
    if reasons:
        return "DONNEES_INCOMPLETES", reasons
    # La detection de chrono manquant n'est pas une anomalie obligatoire :
    # certaines performances n'ont aucun chrono affiche par Geny.
    return "COMPLET", []
