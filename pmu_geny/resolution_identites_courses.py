"""Résoudre les identités du rattrapage à partir des pages de partants Geny."""
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import json
import re
from urllib.parse import urlparse

from . import historiques_incrementaux as inc
from . import liens_geny_course as liens
from .cadence_geny import CadenceGeny, REFUS
from .echeances_production import pause_geny_active
from .historique_individuel import observer_http_geny
from .liaison_chevaux_v22 import nom_geny_concordant, nom_normalise

PILOTE = Path('rattrapage_historiques/resolution_identites_courses.json')
LIMITE_COURSES = 10


def identifiant_course(url):
    parsed = urlparse(url or '')
    match = re.fullmatch(r'/course/(\d+)(?:-[^/]+)?(?:/partants-pronostics|/arrivee-rapports)?/?', parsed.path)
    if parsed.scheme == 'https' and parsed.hostname in ('geny.com', 'www.geny.com') and match:
        return match[1]
    return None


def inventaire(cache, state):
    """Repartir du contexte PMU et du rapprochement de course déjà contrôlé."""
    from .rattrapage_historiques import contexte_verifiable, profils_passe

    groups, counts, contexts = {}, Counter(), {}
    for horse in state['chevaux'].values():
        if horse.get('id') or horse.get('cible_equivalente_a'):
            continue
        context = contexte_verifiable(horse)
        if not context:
            counts['CONTEXTE_PMU_INCOMPLET'] += 1
            continue
        if horse.get('conflit_identite') or horse.get('identifiant_externe_non_reconcilie'):
            counts['IDENTITE_A_VERIFIER'] += 1
            continue
        name, engagement, number = context
        if engagement not in contexts:
            contexts[engagement] = (inc.course_geny_connue(cache, engagement),
                                    profils_passe(cache, engagement+'.json'))
        course, participants = contexts[engagement]
        if not name or nom_normalise(participants.get(number, {}).get('nom')) != name:
            counts['PARTANT_PMU_NON_CONFIRME'] += 1
            continue
        if not course:
            counts['COURSE_GENY_A_RAPPROCHER'] += 1
            continue
        ident = course.removeprefix('GENY-')
        if horse.get('course_url') and identifiant_course(horse['course_url']) != ident:
            counts['CONFLIT_COURSE'] += 1
            continue
        group = groups.setdefault(engagement, {'engagement': engagement, 'id': ident,
            'url': f'https://www.geny.com/course/{ident}/partants-pronostics', 'partants': {}})
        group['partants'][number] = participants[number]['nom']

    ids = Counter(g['id'] for g in groups.values())
    selected = []
    for group in groups.values():
        if ids[group['id']] > 1:
            counts['CONFLIT_COURSE'] += len(group['partants'])
        else:
            selected.append(group)
    selected.sort(key=lambda g: (-len(g['partants']), g['engagement']))
    return selected, dict(counts)


def lire_page(course, *, page=None):
    if page is None:
        from playwright.sync_api import Error, sync_playwright
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                mesure = {}
                try:
                    context = browser.new_context(locale='fr-FR', timezone_id='Europe/Paris')
                    mesure = observer_http_geny(context)
                    result = lire_page(course, page=context.new_page())
                except Error as exc:
                    result = {'statut': 'ERREUR_NAVIGATION', 'erreur': type(exc).__name__}
                finally:
                    browser.close()
                if mesure.get('refus'):
                    result['statut'] = next(statut for statut, code in REFUS.items() if code == mesure['refus'])
                return {**result, 'http_geny': mesure}
        except Error as exc:
            return {'statut': 'ERREUR_NAVIGATION', 'erreur': type(exc).__name__}

    from .collecte_geny_v4 import diagnostic_acces
    from .decouverte_partants import get_rows

    response = page.goto(course['url'], wait_until='domcontentloaded', timeout=25000)
    status = response.status if response else None
    if str(status) in REFUS.values():
        verdict = 'ACCES_REFUSE_403' if status == 403 else 'ACCES_LIMITE_429'
        return {'statut': verdict, 'http': status}
    html = page.content()
    verdict = diagnostic_acces(status, page.title(), page.locator('body').inner_text(timeout=5000), html)
    if verdict in REFUS:
        return {'statut': verdict, 'http': status}
    if status != 200 or identifiant_course(page.url) != course['id']:
        return {'statut': 'COURSE_GENY_NON_CONFIRMEE', 'http': status}
    proof = liens.extraire(get_rows(page), html, course['engagement'], course['url'],
                          datetime.now(inc.UTC).isoformat())
    return {'statut': 'PAGE_LUE', 'preuve': proof}


def preuves_concordantes(cache, course, proof, now):
    """Filtrer chaque lien sur le numéro, le nom et les identités déjà prouvées."""
    engagement = course['engagement']
    stamp = inc.instant(proof.get('capture_utc'))
    if (proof.get('http') != 200 or proof.get('engagement') != engagement
            or proof.get('source_url') != course['url'] or proof.get('course_geny_id') != course['id']
            or not stamp or stamp > now):
        raise ValueError('PREUVE_DE_COURSE_INVALIDE')
    path = cache/'sources_geny/liens'/f'{engagement}.json'
    previous = inc.lire(path)
    old = previous.get('chevaux', {})
    if previous and (previous.get('http') != 200 or not inc.instant(previous.get('capture_utc'))
            or inc.instant(previous['capture_utc']) > now or previous.get('engagement') != engagement
            or previous.get('course_geny_id') != course['id']
            or identifiant_course(previous.get('source_url')) != course['id']):
        return {}, {number: 'CONFLIT_PREUVE_ARCHIVEE' for number in course['partants']}
    captured = proof.get('chevaux', {})
    numbers_by_id = defaultdict(set)
    for links in (old, captured):
        for number, horse in links.items():
            numbers_by_id[horse.get('id')].add(number)
    accepted, conflicts = {}, {}
    for number, name in course['partants'].items():
        horse = captured.get(number)
        if not horse:
            continue
        ident = horse.get('id')
        old_link = old.get(number)
        if (not ident or not nom_geny_concordant(name, horse)
                or not liens.lien_valide(horse.get('url_geny'), ident) or len(numbers_by_id[ident]) != 1
                or (old_link and (old_link.get('id') != ident or not nom_geny_concordant(name, old_link)))):
            conflicts[number] = 'NOM_NUMERO_OU_IDENTIFIANT_NON_CONCORDANT'
            continue
        accepted[number] = {**horse, 'nom_pmu': name}
    if accepted:
        inc.ecrire(path, liens.conserver_liens_precedents({**proof, 'chevaux': accepted}, previous))
    return accepted, conflicts


def passage(cache, state, *, stop_requested, checkpoint, collect=None,
            now=lambda: datetime.now(inc.UTC)):
    """Traiter au plus une page par passage et suivre une cohorte fixe de dix courses."""
    pilot = inc.lire(cache/PILOTE)
    if pilot.get('statut') == 'TERMINE' or stop_requested():
        return False
    cadence = CadenceGeny(cache) if collect is None else None
    if cadence:
        if pause_geny_active(cache, now(), back=state) or cadence.delai(now()):
            return False
        collect = lire_page
    groups, exclusions = inventaire(cache, state)
    if not pilot:
        pilot = {'creation_utc': now().isoformat(), 'courses': {
            g['engagement']: {'id': g['id'], 'cibles': len(g['partants']), 'tentatives': 0}
            for g in groups[:LIMITE_COURSES]}}
    by_engagement = {g['engagement']: g for g in groups}
    for engagement, result in pilot['courses'].items():
        if result.get('statut') not in (None, 'DIFFERE_REFUS_GENY') or engagement in by_engagement:
            continue
        result['statut'] = 'AUCUNE_CIBLE_ELIGIBLE_APRES_RELECTURE'
    pending = [(r['tentatives'], e) for e, r in pilot['courses'].items()
               if r.get('statut') in (None, 'DIFFERE_REFUS_GENY') and e in by_engagement]
    attempted = False
    if pending and not stop_requested():
        # L'ordre de la cohorte reste stable en cas d'égalité de tentatives.
        engagement = min(pending, key=lambda item: item[0])[1]
        course = by_engagement[engagement]
        result = pilot['courses'][engagement]
        if result['id'] != course['id']:
            result['statut'] = 'CONFLIT_COURSE_DEPUIS_SELECTION'
        else:
            attempted = True
            if cadence:
                cadence.reserver(now())
                checkpoint()
            response = collect(course)
            stamp = now()
            status = response['statut']
            mesure = response.get('http_geny', {})
            result.update(tentatives=result['tentatives']+1, statut=status, lecture_utc=stamp.isoformat(),
                          http_geny=mesure)
            if cadence:
                cadence.terminer(stamp, refus=status in REFUS)
            if status in REFUS:
                inc.suspendre_geny(cache, state, stamp, REFUS[status], mesure.get('reprise_au_plus_tot_utc'))
                if result['tentatives'] < 2:
                    result.update(statut='DIFFERE_REFUS_GENY', dernier_refus=status)
            elif status == 'PAGE_LUE':
                accepted, conflicts = preuves_concordantes(cache, course, response['preuve'], stamp)
                ids = {link['id'] for link in accepted.values()}
                result.update(identites_confirmees=len(accepted), conflits=conflicts,
                              carrieres_a_collecter=sorted(ident for ident in ids if not inc.capture_valide(cache, ident)),
                              numeros_sans_lien=sorted(set(course['partants']) - accepted.keys() - conflicts.keys()))
    pilot['statut'] = ('EN_COURS' if any(r.get('statut') in (None, 'DIFFERE_REFUS_GENY')
                                       for r in pilot['courses'].values()) else 'TERMINE')
    pilot['exclusions_inventaire'] = exclusions
    pilot['identites_confirmees'] = sum(r.get('identites_confirmees', 0) for r in pilot['courses'].values())
    pilot['conflits'] = sum(len(r.get('conflits', {})) for r in pilot['courses'].values())
    pilot['pages_lues'] = sum(r.get('statut') == 'PAGE_LUE' for r in pilot['courses'].values())
    pilot['carrieres_identifiees_a_collecter'] = len({
        ident for r in pilot['courses'].values() for ident in r.get('carrieres_a_collecter', [])
    })
    inc.ecrire(cache/PILOTE, pilot)
    checkpoint()
    print('BILAN_IDENTITES_COURSES '+json.dumps(pilot, ensure_ascii=False), flush=True)
    return attempted
