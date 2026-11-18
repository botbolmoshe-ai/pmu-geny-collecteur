"""Validation prospective d'un modèle figé avant toute promotion."""
from datetime import datetime
import hashlib
import os
from pathlib import Path

from .echeances_production import instant, prevision_valide
from .ml_v19 import load, numeric, save

REPORT = Path('ml/maturite.json')
CANDIDATE = Path('ml/candidat_preproduction.json')
CRITERIA = {
    'Forme PMU': ('pmu_score_direct', 'forme_pmu_discipline'),
    'Historique comparable': ('forme_geny_comparable',),
    'Distance': ('distance_m',),
    'Discipline': ('discipline_montee',),
    'Ferrure sourcée': ('ferrure_d4', 'ferrure_dp', 'ferrure_da', 'ferrure_p4', 'ferrure_pa', 'ferrure_pp'),
    'Âge': ('age_ans',),
    'Sexe': ('sexe_male', 'sexe_femelle', 'sexe_hongre'),
    'Gains': ('gains_euros',),
    'Driver': ('driver_score',),
    'Entraîneur': ('entraineur_score',),
    'Tandem cheval-driver': ('tandem_podium_lisse', 'tandem_courses'),
    'Comparaison ferrures historiques': ('forme_ferrure_actuelle',),
    'Avis PMU structuré': ('avis_pmu_structure',),
}
ESSENTIAL = ('Forme PMU', 'Distance', 'Discipline', 'Âge', 'Sexe', 'Gains')


def thresholds():
    stages = {}
    for stage, defaults in [('PREPRODUCTION', (150, 1500, 30, .80)),
                            ('PRODUCTION', (300, 3000, 100, .90))]:
        values = {}
        for name, default in zip(('courses', 'observations', 'prospectives', 'completude'), defaults):
            cast = type(default)
            value = cast(os.getenv(f'ML_{stage}_{name.upper()}') or default)
            if not (0 < value <= 1 if name == 'completude' else value >= 1):
                raise ValueError(f'Seuil ML invalide : {stage} {name}')
            values[name] = value
        stages[stage] = values
    if any(stages['PRODUCTION'][key] < stages['PREPRODUCTION'][key]
           for key in stages['PRODUCTION']):
        raise ValueError('Les seuils de production doivent couvrir ceux de préproduction')
    return stages


def coverage(rows):
    counts = {criterion: 0 for criterion in CRITERIA}
    complete = 0
    for row in rows:
        present = {criterion for criterion, keys in CRITERIA.items()
                   if all(numeric(row['features'].get(key)) is not None for key in keys)}
        for criterion in present:
            counts[criterion] += 1
        complete += all(criterion in present for criterion in ESSENTIAL)
    return {'observations': len(rows), 'completes': complete,
            'completude': complete / len(rows) if rows else 0,
            'criteres': counts}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_path(cache, candidate):
    digest = candidate.get('sha256', '')
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        return None
    path = cache / 'ml/candidats' / digest / 'modele.joblib'
    return path if path.is_file() and sha(path) == digest else None


def score_shadow(cache, course, raw, observed, clock, *, prepared=None):
    """Figer une seule comparaison par course et version, avant son départ."""
    from .ml_v19 import pmu_rows, ranking_for
    import joblib

    cache = Path(cache)
    candidate = load(cache / CANDIDATE, {}) or {}
    if candidate.get('decision'):
        return
    path = candidate_path(cache, candidate)
    if path is None:
        return
    key = f"{course['date']}_{course['code']}"
    target = cache / 'ml/prospectif' / candidate['sha256'] / f'{key}.json'
    if target.with_suffix('.publication.json').exists():
        return
    direct_path = cache / 'pronostics' / f'{key}_direct.json'
    direct = load(direct_path, {}) or {}
    depart = instant(course['depart'])
    trained = instant(candidate.get('entrainement_utc'))
    if not trained or not trained <= observed < depart:
        return
    if instant(direct.get('donnees_observees_utc')) != observed:
        return
    status, rows, metadata = prepared if prepared is not None else pmu_rows(cache, course, raw, observed)
    if status != 'OK' or metadata['np_non_verifies']:
        return
    packed = joblib.load(path)
    if not {h['numero'] for h in direct.get('top3', [])} <= {h['numero'] for h in rows}:
        return
    ranking = ranking_for(packed, rows)
    created = clock()
    if not prevision_valide(direct, depart, created, key=key):
        return
    save(target, {
        'course': key, 'depart': depart.isoformat(), 'calcul_utc': created.isoformat(),
        'observation_utc': observed.isoformat(), 'direct_sha256': sha(direct_path),
        'direct': [h['numero'] for h in direct['top3']],
        'ml': [h['numero'] for h in ranking[:3]], 'couverture': coverage(rows),
    })


def certify_shadow(cache, key, proof, now):
    candidate = load(cache / CANDIDATE, {}) or {}
    if not candidate or candidate.get('decision'):
        return
    path = cache / 'ml/prospectif' / candidate['sha256'] / f'{key}.json'
    doc = load(path, {}) or {}
    if not doc or doc.get('direct_sha256') != proof['sha256']:
        return
    created, depart = instant(doc['calcul_utc']), instant(doc['depart'])
    if created <= now < depart:
        certificate = path.with_suffix('.publication.json')
        if not certificate.exists():
            save(certificate, {'sha256': sha(path), 'publication_utc': now.isoformat(),
                               'direct': proof})


def comparisons(cache, candidate, now):
    folder = cache / 'ml/prospectif' / candidate['sha256']
    results = []
    for cert_path in folder.glob('*.publication.json'):
        key = cert_path.name.removesuffix('.publication.json')
        path = folder / f'{key}.json'
        cert = load(cert_path, {}) or {}
        doc = load(path, {}) or {}
        arrival = load(cache / 'arrivees' / f'{key}.json', {}) or {}
        direct_proof = cert.get('direct') or {}
        if (not doc or doc.get('direct_sha256') != direct_proof.get('sha256')
                or cert.get('publication_utc') != direct_proof.get('publication_utc')
                or cert.get('sha256') != sha(path) or doc.get('course') != key
                or arrival.get('source') != 'PMU_API_PARTICIPANTS'
                or arrival.get('date', key[:10]) + '_' + arrival.get('course', key[11:]) != key):
            continue
        times = [instant(value) for value in (
            candidate.get('dernier_label_entrainement_utc'), candidate.get('entrainement_utc'),
            doc.get('observation_utc'), doc.get('calcul_utc'), cert.get('publication_utc'),
            doc.get('depart'), arrival.get('verifie_utc'))]
        if not all(times) or not times[0] <= times[1] <= times[2] <= times[3] <= times[4] < times[5] < times[6] <= now:
            continue
        try:
            podium = [(int(h['numero']), h['rang']) for h in arrival['arrivee'] if h['rang'] in (1, 2, 3)]
            numbers = {n for n, _ in podium}
            if len(podium) != 3 or len(numbers) != 3 or {rang for _, rang in podium} != {1, 2, 3}:
                continue
            if any(len(doc[kind]) != 3 or len(set(doc[kind])) != 3 for kind in ('ml', 'direct')):
                continue
            scores = {kind: len(numbers.intersection(doc[kind])) for kind in ('ml', 'direct')}
        except (KeyError, TypeError, ValueError):
            continue
        results.append({'course': key, 'arrivee_verifiee_utc': times[6].isoformat(),
                        'scores': scores, 'couverture': doc['couverture'],
                        'sha256_prevision': cert['sha256'], 'sha256_arrivee': sha(cache / 'arrivees' / f'{key}.json')})
    return sorted(results, key=lambda row: (datetime.fromisoformat(row['arrivee_verifiee_utc']), row['course']))


def prospective(rows):
    from .experience_ml import paired_interval
    n = len(rows)
    paired = {kind: {r['course']: r['scores'][kind] for r in rows} for kind in ('ml', 'direct')}
    observations = sum(r['couverture']['observations'] for r in rows)
    return {'courses': n, 'completude': sum(r['couverture']['completes'] for r in rows) / observations if observations else 0,
            **{f'moyenne_{kind}': sum(hits.values()) / n if n else None for kind, hits in paired.items()},
            **{f'taux_3_sur_3_{kind}': sum(v == 3 for v in hits.values()) / n if n else None
               for kind, hits in paired.items()},
            **{f'taux_au_moins_2_sur_3_{kind}': sum(v >= 2 for v in hits.values()) / n if n else None
               for kind, hits in paired.items()},
            'comparaison': paired_interval(paired['ml'], paired['direct'])}
