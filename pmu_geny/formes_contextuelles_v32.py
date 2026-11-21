"""Analyse de forme contextuelle V32 pour le TOP3 direct.

Source primaire: musique PMU; source supplementaire/de secours: historique
Geny relie de maniere certaine. Les seules performances exploitees ont eu
lieu AVANT la course cible. Jamais de cote, d'arrivee future ni d'estimation
arbitraire de ferrure absente. Score heuristique (0-5), non probabiliste.
"""
from __future__ import annotations

from datetime import datetime
import re

from .selection_metier_v20_4 import normaliser, normaliser_hippodrome
from .partants_actuels_v21 import ferrure_normalisee

POINTS = {1: 5.0, 2: 3.5, 3: 2.5, 4: 1.5, 5: 1.0}
ECHELLE = 5.0


def _discipline(value):
    s = normaliser(value)
    if "attele" in s or s == "a":
        return "a"
    if "monte" in s or s == "m":
        return "m"
    return None


def _classement(value):
    s = str(value or "").strip().casefold()
    if s in ("d", "da", "dai", "di", "disq", "dpg", "dist", "ta", "tm", "arr", "r", "nc", "a", "t"):
        return 0.0
    if s in ("np", "non partant", ""):
        return None
    m = re.fullmatch(r"(\d{1,2})(?:er|e|eme|ème)?", s)
    return POINTS.get(int(m.group(1)), 0.0) if m else None


def _musique_pmu(participant, discipline):
    """Le PMU indique la discipline par 'a'/'m'; ne pas melanger les deux."""
    from .top3_independants_v22 import _musique
    value = next((participant[key] for key in
                  ("musique", "musiqueCheval", "derniereMusique")
                  if participant.get(key)), None)
    tokens = _musique(value)
    filtered = []
    for token in tokens:
        token = token.casefold()
        suffix = token[-1] if token[-1] in ("a", "m") else None
        if discipline and suffix and suffix != discipline:
            continue
        points = _classement(token[:-1] if suffix else token)
        if points is not None:
            filtered.append(points)
    if not filtered:
        return None, 0
    # Anciennete relative dans la musique (l'ordre PMU est decroissant).
    weights = [max(0.4, 1 - 0.12 * i) for i in range(len(filtered))]
    score = sum(p * w for p, w in zip(filtered, weights)) / sum(weights)
    return round(score, 4), len(filtered)


def _distance_factor(d1, d2):
    try:
        if d1 is None or d2 is None:
            return 0.75, False
        a, b = int(d1), int(d2)
        if not (1000 <= a <= 5000 and 1000 <= b <= 5000):
            return 0.75, False
    except (ValueError, TypeError):
        return 0.75, False
    ecart = abs(a - b)
    return (1.0 if ecart <= 100 else 0.85 if ecart <= 250
            else 0.55 if ecart <= 500 else 0.25), True


def _facteur_niveau(course, row):
    """L'allocation est un proxy imparfait du niveau, jamais un classement etabli."""
    try:
        cible = float(course.get("allocation_eur"))
    except (TypeError, ValueError):
        return 1.0, False
    source = str(row.get("texte_source") or "")
    montants = re.findall(r"(?<!\d)(\d{1,3}(?:[ \u00a0]\d{3})+)\s*€", source)
    # On ne deduit rien lorsque plusieurs montants sont possibles.
    if cible <= 0 or len(montants) != 1:
        return 1.0, False
    montant = float(re.sub(r"\s+", "", montants[0]))
    if montant <= 0:
        return 1.0, False
    ratio = cible / montant
    return (0.70 if ratio > 2 else 0.85 if ratio > 1.35 else 1.0), True


def _historique_contextuel(historique, course, profil, *, ferrure_differente=.65,
                          ferrure_inconnue=.85, mode_depart=None, observation=None):
    """Pondere les performances passees selon les conditions de la course cible."""
    from .echeances_production import instant

    try:
        depart = datetime.fromisoformat(course["depart"])
    except (KeyError, TypeError, ValueError):
        return None
    discipline = _discipline(course.get("discipline"))
    hippodrome = normaliser_hippodrome(course.get("hippodrome"))
    current_ferrure = ferrure_normalisee(profil.get("ferrure"))
    poids_total = total = 0.0
    n = n_proches = 0
    dates = set()
    facteurs = []
    ferrures_comparees = niveaux_documentes = 0
    for row in historique.get("performances", []):
        if not isinstance(row, dict):
            continue
        try:
            date = datetime.fromisoformat(row["date"]).date()
        except (KeyError, TypeError, ValueError):
            continue
        age_jours = (depart.date() - date).days
        if not 1 <= age_jours <= 365:
            continue
        disc_histo = _discipline(row.get("discipline"))
        if discipline and disc_histo != discipline:
            continue  # Ne pas traiter une victoire montee comme une victoire attelee.
        if mode_depart:
            proof = row.get('depart_trot') or {}
            capture = instant(proof.get('capture_utc'))
            if (not discipline or proof.get('source') != 'GENY_DONNEES_STRUCTUREES'
                    or proof.get('mode') != mode_depart or not capture or capture > observation
                    or not str(proof.get('url', '')).startswith(('https://www.geny.com/', 'https://geny.com/'))):
                continue
        points = _classement(row.get("classement"))
        if points is None:
            continue
        distance, distance_documentee = _distance_factor(
            course.get("distance_m"), row.get("distance_m"))
        piste_histo = normaliser_hippodrome(row.get("hippodrome"))
        piste_factor = (1.0 if hippodrome and piste_histo == hippodrome
                        else 0.70 if hippodrome and piste_histo else 0.80)
        ferrure_histo = ferrure_normalisee(row.get("ferrure")) if row.get('ferrure_qualification')!='CONFLIT' else ''
        if current_ferrure and ferrure_histo:
            ferrures_comparees += 1
            ferrure_factor = 1.0 if current_ferrure == ferrure_histo else ferrure_differente
        else:
            ferrure_factor = ferrure_inconnue  # Incertitude, pas une ferrure inventee.
        niveau_factor, niveau_connu = _facteur_niveau(course, row)
        niveaux_documentes += int(niveau_connu)
        temps = (1.0 if age_jours <= 30 else 0.85 if age_jours <= 90
                 else 0.65 if age_jours <= 180 else 0.40)
        poids = distance * piste_factor * ferrure_factor * niveau_factor * temps
        total += poids * points
        poids_total += poids
        n += 1
        n_proches += int(distance_documentee and distance >= 0.85)
        dates.add(date.isoformat())
        facteurs.append(round(distance * piste_factor * ferrure_factor * niveau_factor, 3))
    if n == 0:
        return None
    # Evite qu'une victoire isolee sur un parcours different vaille 5/5.
    prior = 1.5
    score = (total + prior * 2.0) / (poids_total + prior)
    return {
        "score": round(min(ECHELLE, max(0.0, score)), 4),
        "performances_valides": n,
        "courses_distance_proche": n_proches,
        "jours_distincts": len(dates),
        "ferrures_comparees": ferrures_comparees,
        "niveaux_documentes": niveaux_documentes,
        "poids_total": round(poids_total, 4),
        "comparabilite_moyenne": round(sum(facteurs) / n, 4),
    }


def chronos_comparables(historique, course):
    """Médiane des réductions Geny sur le même hippodrome, discipline et distance proche."""
    from statistics import median

    departure = datetime.fromisoformat(course['depart']).date()
    discipline = _discipline(course.get('discipline'))
    piste = normaliser_hippodrome(course.get('hippodrome'))
    if discipline is None or not piste:
        return {}
    relevés = {}
    for row in historique.get('performances', []):
        if (_discipline(row.get('discipline')) != discipline
                or normaliser_hippodrome(row.get('hippodrome')) != piste
                or not re.fullmatch(r'[1-9]\d*(?:e|er)?', str(row.get('classement') or '').strip().lower())):
            continue
        distance, documentee = _distance_factor(course.get('distance_m'), row.get('distance_m'))
        if not documentee or distance < .85:
            continue
        try:
            jour = datetime.fromisoformat(row['date']).date()
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= (departure - jour).days <= 365:
            continue
        chrono = re.fullmatch(r"""([1-2])['’](\d{2})(?:['’]{2}|")([0-9])""",
                              str(row.get('chrono') or '').strip())
        if not chrono or int(chrono[2]) >= 60:
            continue
        seconds = 60 * int(chrono[1]) + int(chrono[2]) + int(chrono[3]) / 10
        if 60 <= seconds <= 110:
            relevés.setdefault(jour, set()).add(seconds)
    chronos = [next(iter(relevés[jour])) for jour in sorted(relevés, reverse=True)
               if len(relevés[jour]) == 1][:5]
    if len(chronos) < 2:
        return {}
    return {'chrono_comparable_mediane_sec_km': median(chronos),
            'chrono_comparable_nb_sorties': len(chronos)}


def forme_meme_depart(historique, course, profil, observation):
    from .departs_trot import mode_pmu
    from .echeances_production import instant

    mode, _ = mode_pmu(course)
    captured = instant(historique.get('extrait_utc'))
    if (not mode or not captured or not observation or captured > observation
            or not str(historique.get('source_url', '')).startswith(('https://www.geny.com/', 'https://geny.com/'))):
        return None
    return _historique_contextuel(historique, course, profil, mode_depart=mode, observation=observation)


def noter_partant(participant, course, lien, profil):
    """Score toujours explicable: PMU seul, Geny seul ou melange prudent.

    Le numero sert a retrouver la ligne du partant, jamais son identite
    historique. Le lien Geny doit avoir ete verifie par le nom exact/ID.
    """
    discipline = _discipline(course.get("discipline"))
    pmu, n_pmu = _musique_pmu(participant, discipline)
    hist = None
    if lien.get("cheval_id") and lien.get("methode") in (
        "NOM_EXACT_UNIQUE", "NOM_EXACT_ET_ID_GENY_CONFIRME",
        "NOM_AMBIGU_ID_CONFIRME", "ID_GENY_MANIFESTE_VERIFIE"
    ):
        document = lien.get("historique") or {}
        if document.get("statut") in ("COMPLET", "PARTIEL", "PARTIEL_HISTORIQUE",
                                      "DONNEES_INCOMPLETES"):
            hist = _historique_contextuel(document, course, profil)
    if hist and pmu is not None:
        # Plus la profondeur du contexte est grande, moins la musique non-contextuelle pese.
        poids_histo = 0.70 if hist["performances_valides"] >= 3 else 0.45
        score = poids_histo * hist["score"] + (1 - poids_histo) * pmu
        source = "PMU+GENY_CONTEXTUEL"
    elif hist:
        score = hist["score"]
        source = "GENY_CONTEXTUEL_SEUL"
    elif pmu is not None:
        score = pmu
        source = "PMU_MUSIQUE_SEULE"
    else:
        return {"score": None, "source_forme": "AUCUNE", "musique_exploitable": 0,
                "historique_exploitable": 0, "qualite": "INSUFFISANTE"}
    n_histo = hist["performances_valides"] if hist else 0
    qualite = ("CONTEXTE_DOCUMENTE" if n_histo >= 3 and hist["courses_distance_proche"] >= 2
               and (not profil.get("ferrure") or hist["ferrures_comparees"] >= 2)
               else "CONTEXTE_PARTIEL" if hist else "PMU_NON_CONTEXTUALISE")
    return {"score": round(score, 4), "source_forme": source,
            "musique_exploitable": n_pmu, "historique_exploitable": n_histo,
            "distance_proche": hist["courses_distance_proche"] if hist else 0,
            "comparabilite_moyenne": hist["comparabilite_moyenne"] if hist else None,
            "ferrures_historiques_comparees": hist["ferrures_comparees"] if hist else 0,
            "niveaux_historiques_documentes": hist["niveaux_documentes"] if hist else 0,
            "qualite": qualite,
            "identifiant_historique": lien.get("cheval_id") if hist else None}
