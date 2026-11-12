"""Scoring exploratoire Geny, sans apprentissage ni requêtes réseau.

Aucun score n'est une probabilité. Les champs manquants sont exclus du
dénominateur; la couverture documentaire est affichée séparément.
"""
from __future__ import annotations
from datetime import date, datetime
from math import isfinite

WEIGHTS = {"forme": 30, "regularite": 20, "distance": 20, "hippodrome": 15, "repos": 15}
RANK_POINTS = {1: 100, 2: 80, 3: 65, 4: 45, 5: 30}
DISQUALIFICATIONS = {"DAI", "DI", "DA", "DISQ", "D"}

def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None

def _number(value):
    try:
        x = float(str(value).replace(",", "."))
        return x if isfinite(x) else None
    except (TypeError, ValueError):
        return None

def _rank_score(value):
    label = str(value or "").strip().upper()
    if label in DISQUALIFICATIONS:
        return 0
    try:
        rank = int(label)
    except ValueError:
        return None
    return RANK_POINTS.get(rank, 15 if rank > 5 else None)

def evaluer_cheval(historique, course, nom="", cheval_id=""):
    """Retourne score de mérite et couverture, sans données post-départ."""
    depart = _day(course.get("depart") or course.get("date"))
    if depart is None:
        raise ValueError("Date de course manquante")
    valid = []
    for p in historique.get("performances", []):
        d = _day(p.get("date"))
        if d is None or d >= depart:
            continue
        rank = _rank_score(p.get("classement"))
        if rank is None:
            continue
        valid.append((d, rank, p))
    valid.sort(key=lambda row: row[0], reverse=True)
    valid = valid[:10]
    metrics = {}
    if valid:
        weights = [0.85 ** i for i in range(len(valid))]
        metrics["forme"] = sum(r * w for (_, r, _), w in zip(valid, weights)) / sum(weights)
        metrics["regularite"] = 100 * sum(r >= 65 for _, r, _ in valid) / len(valid)
        days = (depart - valid[0][0]).days
        metrics["repos"] = max(0, 100 - 1.5 * abs(days - 21))
        target_dist = _number(course.get("distance_m"))
        if target_dist is not None:
            comparable = [(r, p) for _, r, p in valid
                          if _number(p.get("distance_m")) is not None
                          and abs(_number(p["distance_m"]) - target_dist) <= 250]
            if comparable:
                metrics["distance"] = sum(r for r, _ in comparable) / len(comparable)
        target_hip = str(course.get("hippodrome") or "").strip().casefold()
        if target_hip:
            at_track = [r for _, r, p in valid
                        if str(p.get("hippodrome") or "").strip().casefold() == target_hip]
            if at_track:
                metrics["hippodrome"] = sum(at_track) / len(at_track)
    available = sum(WEIGHTS[k] for k in metrics)
    score = round(sum(WEIGHTS[k] * metrics[k] for k in metrics) / available, 2) if available else None
    return {"cheval_id": str(cheval_id), "nom": nom, "score_merite": score,
            "couverture_pct": available, "nb_performances": len(valid),
            "criteres_disponibles": sorted(metrics),
            "statut": "EXPLORATOIRE" if score is not None else "HISTORIQUE_INEXPLOITABLE",
            "note": "Score relatif, non calibré; aucune probabilité implicite."}

def classer_course(course, chevaux):
    """chevaux: liste {numero, nom, cheval_id, historique}; aucune écriture."""
    results = []
    for horse in chevaux:
        result = evaluer_cheval(horse.get("historique") or {}, course,
                                horse.get("nom", ""), horse.get("cheval_id", ""))
        result["numero"] = horse.get("numero")
        results.append(result)
    results.sort(key=lambda x: (x["score_merite"] is None,
                                -(x["score_merite"] or 0),
                                -x["couverture_pct"], str(x["numero"])))
    return {"mode": "GENY_STATISTIQUE_EXPLORATOIRE", "classement": results,
            "top3": [x for x in results if x["score_merite"] is not None][:3],
            "statut": "TOP3_DISPONIBLE" if sum(x["score_merite"] is not None for x in results) >= 3
                      else "DONNEES_INSUFFISANTES"}
