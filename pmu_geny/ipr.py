"""Indice hippique d'observation, fondé sur les preuves disponibles au relevé."""
from collections import Counter
from datetime import date, timedelta, timezone
from math import exp
import os
from pathlib import Path
import re

from dashboard.trot_analytics.usages import IPR
from .departs_trot import entier, mode_pmu
from .echeances_production import PARIS, instant, lire, sauver
from .formes_contextuelles_v32 import _classement, _discipline, _distance_factor, _facteur_niveau
from .partants_actuels_v21 import extraire_partants, ferrure_normalisee
from .profils_partants import LIENS_VERIFIES
from .selection_metier_v20_4 import normaliser, normaliser_hippodrome

VERSION = 'ipr-v1'
GENY = ('https://www.geny.com/', 'https://geny.com/')
DAI = {'d', 'da', 'dai', 'di', 'disq', 'dpg', 'dist'}


def actif():
    return os.getenv('IPR_SHADOW_ENABLED', '').strip().lower() == 'true'


def piste(value):
    label = normaliser(value)
    if label in ('gp', 'grande piste'):
        return 'GP'
    if label in ('pp', 'petite piste'):
        return 'PP'
    return None


def evaluer_cheval(course, profil, lien, observation):
    """Score sur 100, confiance descriptive et motifs explicites."""
    depart = instant(course.get('depart'))
    discipline = _discipline(course.get('discipline'))
    vide = {'ipr_score': None, 'ipr_confiance': 'NON ÉVALUABLE',
            'ipr_n_historiques_comparables': None, 'ipr_couverture': None}
    if not depart or not observation.tzinfo or observation >= depart or not discipline:
        return {**vide, 'ipr_motifs': 'Coupure ou discipline non vérifiée'}
    if profil.get('statut_np') != 'PARTANT':
        motif = 'Non-partant PMU' if profil.get('statut_np') == 'NON_PARTANT' else 'Participation non vérifiée'
        return {**vide, 'ipr_motifs': motif}
    if lien.get('methode') not in LIENS_VERIFIES or not lien.get('cheval_id'):
        return {**vide, 'ipr_motifs': 'Identité Geny absente ou ambiguë'}
    hist = lien.get('historique', {})
    stamp = instant(hist.get('extrait_utc'))
    if (not stamp or stamp > observation or not str(hist.get('source_url', '')).startswith(GENY)
            or not isinstance(hist.get('performances'), list)):
        return {**vide, 'ipr_motifs': 'Historique Geny absent ou postérieur au relevé'}
    day = depart.astimezone(PARIS).date()
    cutoff_day = observation.astimezone(PARIS).date()
    candidates = []
    for row in hist['performances']:
        try:
            jour = date.fromisoformat(row['date'])
        except (ValueError, KeyError, TypeError):
            continue
        age = (day - jour).days
        # Une date seule ne prouve pas qu'une sortie du même jour précédait le relevé.
        if 0 < age <= 365 and jour < cutoff_day and _discipline(row.get('discipline')) == discipline:
            candidates.append((jour, age, row))
    days = Counter(jour for jour, _, _ in candidates)
    params = course.get('parametres_pmu', {})
    target_track = piste(params.get('parcours')) or piste(params.get('typePiste'))
    target_mode = mode_pmu(course)[0]
    target_site = normaliser_hippodrome(course.get('hippodrome'))
    target_shoe = ferrure_normalisee(profil.get('ferrure'))
    evidence = []
    for jour, age, row in sorted(candidates, key=lambda triplet: triplet[0], reverse=True):
        if days[jour] != 1:
            continue
        distance, sourced_distance = _distance_factor(course.get('distance_m'), row.get('distance_m'))
        if not sourced_distance or distance < .55:
            continue
        result = str(row.get('classement') or '').strip().lower()
        points = _classement(result)
        if points is None:
            continue
        rank_match = re.fullmatch(r'([1-9]\d?)(?:er|e|eme|ème)?', result)
        rank = int(rank_match[1]) if rank_match else None
        field = entier(row.get('nombre_partants'), minimum=2, maximum=40)
        if rank and field and rank > field:
            continue
        relative = bool(rank and field)
        merit = (field - rank) / (field - 1) if relative else points / 5
        site = normaliser_hippodrome(row.get('hippodrome'))
        track = piste(row.get('piste')) or piste(row.get('parcours'))
        hist_start = row.get('depart_trot') or {}
        start_stamp = instant(hist_start.get('capture_utc'))
        mode = hist_start.get('mode') if (
            start_stamp and start_stamp <= observation and str(hist_start.get('url', '')).startswith(GENY)
            and hist_start.get('source') == 'GENY_DONNEES_STRUCTUREES') else None
        shoe = ferrure_normalisee(row.get('ferrure')) if row.get('ferrure_qualification') != 'CONFLIT' else ''
        level, level_known = _facteur_niveau(course, row)
        same_site = target_site and site
        same_track = target_track and track
        same_mode = target_mode and mode
        same_shoe = target_shoe and shoe
        similarity = distance * level
        for known, equal, mismatch in (
            (same_site, target_site == site, .85), (same_track, target_track == track, .8),
            (same_mode, target_mode == mode, .8), (same_shoe, target_shoe == shoe, .85),
        ):
            if known and not equal:
                similarity *= mismatch
        factor = similarity * exp(-age / 180)
        coverage = sum(map(bool, (relative, same_site, same_track, same_mode, same_shoe, level_known))) / 6
        evidence.append({'jour': jour.isoformat(), 'rang': rank, 'effectif': field,
                         'merite': merit, 'poids': factor, 'couverture': coverage, 'dai': result in DAI})
        if len(evidence) == 10:
            break
    if not evidence:
        return {**vide, 'ipr_n_historiques_comparables': 0,
                'ipr_motifs': 'Aucune sortie comparable et datée'}
    total = sum(row['poids'] for row in evidence)
    sample = total ** 2 / sum(row['poids'] ** 2 for row in evidence)
    coverage = sum(r['couverture'] * r['poids'] for r in evidence) / total
    merit = sum(row['merite'] * row['poids'] for row in evidence) / total
    # Un DAI vaut zéro sur la sortie et réduit la confiance, sans confondre un NP avec un DAI.
    dai = sum(row['dai'] * row['poids'] for row in evidence) / total
    confidence = ('ÉLEVÉE' if sample >= 5 and coverage >= .67 and dai <= .2 else
                  'MOYENNE' if sample >= 3 and coverage >= .33 and dai <= .4 else 'FAIBLE')
    relative = sum(bool(r['rang'] and r['effectif']) for r in evidence)
    return {'ipr_score': round(100 * merit, 2), 'ipr_confiance': confidence,
            'ipr_n_historiques_comparables': len(evidence), 'ipr_couverture': round(100 * coverage, 1),
            'ipr_motifs': (f'{relative}/{len(evidence)} avec effectif · échantillon effectif {sample:.1f} · '
                           f'DAI pondérés {dai:.0%}' + (' · rang ordinal en secours' if relative < len(evidence) else '')),
            'source': hist['source_url'], 'historique_extrait_utc': stamp.isoformat(), 'sorties': evidence}


def calculer(course, profils, liens, observation, calcul):
    depart = instant(course.get('depart'))
    if not depart or not observation.tzinfo or not calcul.tzinfo or not observation <= calcul < depart:
        return None
    partants = [str(n) for n, p in profils.items() if p.get('statut_np') == 'PARTANT']
    np_connus = len(profils) == course.get('nombre_declares') and all(
        p.get('statut_np') in ('PARTANT', 'NON_PARTANT') and p.get('nom') for p in profils.values())
    preparation = observation.astimezone(PARIS).date() < depart.astimezone(PARIS).date()
    rows = {}
    for n, p in profils.items():
        link = liens.get(str(n), {})
        result = evaluer_cheval(course, p, link, observation)
        motif = result['ipr_motifs']
        if preparation:
            motif = 'Préparation J+1 · ' + motif
        if not np_connus:
            motif = 'Liste PMU ou NP non vérifiés · ' + motif
            result.update(ipr_score=None, ipr_confiance='NON ÉVALUABLE')
        rows[str(n)] = {**result, 'nom': p.get('nom'), 'statut_np': p.get('statut_np'),
                        'ipr_statut': IPR.usage, 'ipr_version': VERSION,
                        'ipr_calcul_utc': calcul.isoformat(), 'ipr_rang_shadow': None, 'ipr_motifs': motif}
    scores = [n for n, row in rows.items() if row['ipr_score'] is not None]
    scores.sort(key=lambda n: (-rows[n]['ipr_score'], int(n)))
    for rang, n in enumerate(scores, start=1):
        rows[n]['ipr_rang_shadow'] = rang
    candidate = None
    if not preparation and len(scores) >= 3:
        from .signaux_geny import candidat_classement, signaux
        candidate = candidat_classement(
            [(int(n), rows[n]['ipr_score'] / 20) for n in scores],
            {int(n): signaux(course, profils.get(n, profils.get(int(n), {})), liens.get(n, {}), observation)
             for n in scores},
        )
    return {**({'candidat_geny': candidate} if candidate else {}),
            'date': course['date'], 'course': course['code'], 'depart': depart.isoformat(),
            'observation_utc': observation.isoformat(), 'calcul_utc': calcul.isoformat(),
            'version': VERSION, 'usage': IPR.usage, 'preparation': preparation,
            'discipline': _discipline(course.get('discipline')), 'distance': course.get('distance_m'),
            'mode_depart': mode_pmu(course)[0], 'partants': sorted(partants, key=int), 'chevaux': rows,
            'top3': list(map(int, scores[:3])) if len(scores) >= 3 and not preparation else []}


def enregistrer(cache, course, raw, observation, clock):
    from .auto_v18 import _list
    from .liaison_chevaux_v22 import etablir

    depart = instant(course.get('depart'))
    now = clock()
    if not depart or not observation.tzinfo or not observation <= now < depart:
        return 'HORS_COUPURE'
    if (now - observation > timedelta(minutes=30)
            or depart.astimezone(PARIS).date() - observation.astimezone(PARIS).date() > timedelta(days=1)):
        return 'RELEVE_NON_FRAIS'
    profiles = extraire_partants(raw, course=course)
    if not profiles or len(profiles) != len(_list(raw, 'participants', 'partants')):
        return 'PARTANTS_PMU_INCOHERENTS'
    cache = Path(cache)
    key = f"{course['date']}_{course['code']}"
    latest = cache / 'ipr' / f'{key}.json'
    old = lire(latest)
    previous = instant(old.get('observation_utc'))
    if old.get('version') == VERSION and previous and observation <= previous:
        return 'DEJA_CALCULE'
    links = etablir(cache, course, [{'numero': n, **p} for n, p in profiles.items()])
    doc = calculer(course, profiles, links, observation, clock())
    if doc is None:
        return 'HORS_COUPURE'
    stamp = observation.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    version = cache / 'ipr' / 'versions' / key / VERSION / f'{stamp}.json'
    if not version.exists():
        sauver(version, doc)
    sauver(latest, lire(version))
    print(f'IPR_SHADOW course={key} scores={sum(r["ipr_score"] is not None for r in doc["chevaux"].values())}'
          f' partants={len(doc["partants"])} preparation={int(doc["preparation"])}', flush=True)
    return 'CALCULE'
