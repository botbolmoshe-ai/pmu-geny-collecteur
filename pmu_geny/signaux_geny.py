"""Variables Geny candidates, calculées à partir d'une capture antérieure au relevé."""
from collections import Counter
from datetime import date
from statistics import median

from .departs_trot import mode_pmu
from .echeances_production import PARIS, instant
from .formes_contextuelles_v32 import _classement, _discipline, _distance_factor
from .liaison_chevaux_v22 import nom_normalise
from .profils_partants import LIENS_VERIFIES
from .selection_metier_v20_4 import normaliser, normaliser_hippodrome
from .structure_geny import structurer

FIELDS = (
    'geny_forme_parcours', 'geny_forme_autostart', 'geny_forme_tandem',
    'geny_chrono_parcours', 'geny_forme_niveau',
)


def signaux(course, profil, lien, observation):
    depart = instant(course.get('depart'))
    hist = lien.get('historique') or {}
    captured = instant(hist.get('extrait_utc'))
    discipline = _discipline(course.get('discipline'))
    if (not observation or not observation.tzinfo or not depart or not captured
            or not captured <= observation < depart or not discipline
            or lien.get('methode') not in LIENS_VERIFIES or not lien.get('cheval_id')
            or not str(hist.get('source_url', '')).startswith(('https://www.geny.com/', 'https://geny.com/'))):
        return {}
    cutoff = observation.astimezone(PARIS).date()
    target_day = depart.astimezone(PARIS).date()
    target_site = normaliser_hippodrome(course.get('hippodrome'))
    params = course.get('parametres_pmu') or {}
    target_track = {'gp': 'GP', 'grande piste': 'GP', 'pp': 'PP', 'petite piste': 'PP'}.get(
        normaliser(params.get('parcours') or params.get('typePiste')))
    driver = nom_normalise(profil.get('driver_jockey'))
    allocation = course.get('allocation_eur')
    target_auto = mode_pmu(course)[0] == 'Autostart'
    rows = []
    for row in hist.get('performances', []):
        try:
            day = date.fromisoformat(row['date'])
        except (KeyError, ValueError, TypeError):
            continue
        age = (target_day - day).days
        if day < cutoff and 0 < age <= 365 and _discipline(row.get('discipline')) == discipline:
            rows.append((day, row))
    dates = Counter(day for day, _ in rows)
    values = {field: [] for field in FIELDS}
    for day, row in sorted(rows, key=lambda item: item[0], reverse=True):
        if dates[day] != 1:
            continue
        points = _classement(row.get('classement'))
        if points is None:
            continue
        parsed = structurer(row.get('texte_source'))
        distance, known = _distance_factor(course.get('distance_m'), row.get('distance_m'))
        if not known or distance < .85:
            continue
        same_track = (target_track and parsed.get('piste_geny') == target_track
                      and target_site and normaliser_hippodrome(row.get('hippodrome')) == target_site)
        if same_track:
            values['geny_forme_parcours'].append(points)
            seconds = parsed.get('chrono_geny_sec_km')
            if seconds and 60 <= seconds <= 110 and str(row.get('classement', '')).isdigit():
                values['geny_chrono_parcours'].append(seconds)
        if target_auto and parsed.get('depart_geny') == 'Auto':
            values['geny_forme_autostart'].append(points)
        if driver and driver == nom_normalise(parsed.get('driver_geny')):
            values['geny_forme_tandem'].append(points)
        previous = parsed.get('allocation_geny_eur')
        if isinstance(allocation, (int, float)) and allocation > 0 and previous and .67 <= previous / allocation <= 1.5:
            values['geny_forme_niveau'].append(points)
    return {field: float(median(samples[:5])) for field, samples in values.items() if len(samples) >= 2}


def ajustement(features, reference):
    """Écart de forme sur /5 avec rétrécissement, zéro en l'absence de preuve."""
    supported = [features[field] for field in FIELDS if field != 'geny_chrono_parcours' and field in features]
    if not supported:
        return 0.0
    return (sum(supported) - len(supported) * reference) / (4 * (len(supported) + 2))


def candidat_classement(ranking, features):
    """Départage d'observation sur /5, avec l'ordre d'origine pour les ex æquo."""
    if len(ranking) < 3 or not any(
            ajustement(features.get(number, {}), score) for number, score in ranking):
        return None
    ordered = sorted(ranking, key=lambda row: -(row[1] + ajustement(features.get(row[0], {}), row[1])))
    return {'version': 'geny-contexte-v1', 'top3': [number for number, _ in ordered[:3]],
            'partants_avec_signaux': sum(bool(features.get(number)) for number, _ in ranking)}
