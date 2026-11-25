"""Mesurer uniquement les versions publiées avant départ et les arrivées vérifiées."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from .departs_trot import POIDS_FORME_MEME_DEPART
from .echeances_production import lire, sauver, instant


def retrouver(cache,key,kind,proof):
    path=cache/proof.get('fichier','')
    if cache.resolve() not in path.resolve().parents:return None
    # Le dernier calcul peut avoir changé avant un échec Sheets. Rechercher la
    # version effectivement publiée, sans lui substituer un nouveau classement.
    candidates=[path,*sorted((cache/'pronostics/versions').glob(f'{key}_{kind}_*.json'))]
    for p in candidates:
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==proof.get('sha256'):
            return lire(p)
    return None


def prevision_publiee(cache, key, kind, proof, depart, *, depart_programme=None):
    published = instant(proof.get('publication_utc'))
    created = instant(proof.get('calcul_utc'))
    doc = retrouver(cache, key, kind, proof)
    cutoff = min(depart, depart_programme) if depart_programme else depart
    if not doc or not published or not created or not created <= published < cutoff:
        raise ValueError('PREUVE_PUBLICATION_INVALIDE')
    if doc.get('calcul_utc') != proof['calcul_utc']:
        raise ValueError('VERSION_INCOHERENTE')
    if doc.get('date', '') + '_' + doc.get('course', '') != key or instant(doc.get('depart')) != (depart_programme or depart):
        raise ValueError('COURSE_INCOHERENTE')
    if kind == 'ml' and doc.get('experimental'):
        fitted = instant(doc.get('entrainement_utc'))
        label = instant(doc.get('dernier_label_entrainement_utc'))
        if not fitted or not label or not label <= fitted <= created:
            raise ValueError('FUITE_TEMPORELLE')
    numbers = {int(h['numero']) for h in doc['top3']}
    if len(doc['top3']) != 3 or len(numbers) != 3 or min(numbers) <= 0:
        raise ValueError('TOP3_INVALIDE')
    return doc, numbers


def evaluer_depart(cache, key, certificate, departure, podium):
    proof = certificate.get('versions', {}).get('direct', {})
    created = instant(proof.get('calcul_utc'))
    observed = instant(proof.get('lecture_sheets_utc'))
    published = instant(proof.get('publication_utc'))
    if (instant(certificate.get('depart')) != departure or not created or not observed or not published
            or not created <= observed <= published < departure):
        return None
    doc, baseline = prevision_publiee(cache, key, 'direct', proof, departure)
    candidate = doc.get('candidat_depart', {})
    proposed = candidate.get('top3', [])
    eligible = {h.get('numero') for h in doc.get('classement_complet', [])}
    if (candidate.get('poids') == POIDS_FORME_MEME_DEPART and candidate.get('partants_avec_forme_meme_depart', 0) > 0
            and len(proposed) == len(set(proposed)) == 3 and set(proposed) <= eligible):
        return len(baseline & podium), len(set(proposed) & podium)
    return len(baseline & podium), None


def mesurer(cache, now=None):
    cache = Path(cache)
    now = now or datetime.now(timezone.utc)
    results, rejected, depart_rejected = [], [], []
    depart_candidate, depart_baseline = {}, {}
    direct_evaluable = 0
    publications = cache / 'publications'
    paired = {path.stem: path for path in publications.glob('*.json')}
    direct = {path.stem: path for path in (publications / 'direct').glob('*.json')}
    for key in sorted(paired.keys() | direct.keys()):
        certificate = lire(paired[key]) if key in paired else {}
        direct_certificate = lire(direct[key]) if key in direct else certificate
        paired_departure = instant(certificate.get('depart'))
        direct_departure = instant(direct_certificate.get('depart'))
        arrival = lire(cache / 'arrivees' / f'{key}.json')
        checked = instant(arrival.get('verifie_utc'))
        if not checked or checked > now:
            continue
        paired_ready = paired_departure is not None and paired_departure < checked
        direct_ready = direct_departure is not None and direct_departure < checked
        if not (paired_ready or direct_ready):
            continue
        if arrival.get('source') != 'PMU_API_PARTICIPANTS':
            rejected.append({'course': key, 'motif': 'SOURCE_ARRIVEE_NON_VERIFIEE'})
            continue
        try:
            ranks = [(int(h['numero']), h['rang']) for h in arrival['arrivee'] if h['rang'] in (1, 2, 3)]
            podium = {numero for numero, _ in ranks}
            if len(ranks) != 3 or len(podium) != 3 or {rank for _, rank in ranks} != {1, 2, 3}:
                raise ValueError('ARRIVEE_INVALIDE')
        except (KeyError, ValueError, TypeError) as exc:
            rejected.append({'course': key, 'motif': str(exc) or 'ARRIVEE_INVALIDE'})
            continue
        try:
            comparison = evaluer_depart(cache, key, direct_certificate, direct_departure, podium) if direct_ready else None
            if comparison:
                direct_evaluable += 1
                base, alternate = comparison
                if alternate is not None:
                    depart_baseline[key], depart_candidate[key] = base, alternate
        except (AttributeError, KeyError, ValueError, TypeError) as exc:
            depart_rejected.append({'course': key, 'motif': str(exc) or 'VARIANTE_DEPART_INVALIDE'})
        if not paired_ready:
            continue
        try:
            scores, versions = {}, {}
            for kind in ('direct', 'ml'):
                proof = certificate['versions'][kind]
                _, numbers = prevision_publiee(cache, key, kind, proof, paired_departure)
                scores[kind] = len(numbers & podium)
                versions[kind] = proof['sha256']
            results.append({'course': key, 'depart': paired_departure.isoformat(), 'arrivee_verifiee_utc': checked.isoformat(),
                            'scores': scores, 'versions': versions,
                            'empreinte_modele': certificate['versions']['ml'].get('empreinte_modele')})
        except (AttributeError, KeyError, ValueError, TypeError) as exc:
            rejected.append({'course': key, 'motif': str(exc) or 'ARRIVEE_INVALIDE'})
    n = len(results)
    report = {
        'nature': 'PREVISIONS_PUBLIEES_AVANT_DEPART', 'controle_utc': now.isoformat(), 'courses': n,
        'moyenne_ml': sum(r['scores']['ml'] for r in results) / n if n else None,
        'moyenne_direct': sum(r['scores']['direct'] for r in results) / n if n else None,
        'ecart_ml_direct': sum(r['scores']['ml'] - r['scores']['direct'] for r in results) / n if n else None,
        'exact_3_sur_3_ml': sum(r['scores']['ml'] == 3 for r in results),
        'au_moins_2_sur_3_ml': sum(r['scores']['ml'] >= 2 for r in results),
        'resultats': results, 'rejets': rejected,
        'regle_ajustement': 'Réentraînement sur nouveaux labels admissibles ; choix sur validation temporelle, sans promotion sur ces seuls scores.',
    }
    count = len(depart_candidate)
    report['candidat_depart'] = {
        'courses': count, 'direct_evaluable': direct_evaluable, 'rejets': depart_rejected,
        'statut': 'EXPERIMENTAL' if count else 'DONNEES_INSUFFISANTES',
    }
    if count:
        from .experience_ml import paired_interval
        scores = depart_candidate.values()
        report['candidat_depart'].update(
            moyenne=sum(scores) / count, moyenne_direct=sum(depart_baseline.values()) / count,
            ecart_moyen=(sum(scores) - sum(depart_baseline.values())) / count,
            exact_3_sur_3=sum(score == 3 for score in scores),
            au_moins_2_sur_3=sum(score >= 2 for score in scores),
            comparaison=paired_interval(depart_candidate, depart_baseline) if count > 1 else None,
            scores_candidat_par_course=depart_candidate, scores_direct_par_course=depart_baseline,
        )
    sauver(cache / 'ml/performance_prospective.json', report)
    return report
