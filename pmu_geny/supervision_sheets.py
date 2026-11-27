"""Vues de consultation calculées depuis pmu-data et les preuves de publication."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import math
import re

from dashboard.trot_analytics.correspondance_geny import AMBIGUE, CHAMP, CONFIRMEE, NON_EFFECTUEE
from dashboard.trot_analytics.dates import PARIS, nombre_paris, vers_nombre
from .echeances_production import (
    creneau_nocturne, etat_cooldown_geny, instant, lire, planifier,
)

SUPERVISION = 'PMU_DATA'
REFERENTIEL = 'Referentiel_pmu_data'
PROVENANCE = 'https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/pmu-data/'
CHECKPOINT = 'orchestration/production_etat.json'
CONTROLE = 'qualite/dernier_controle_production.json'
INCREMENTAL = 'collecte_incrementale/etat.json'
RATTRAPAGE = 'rattrapage_historiques/bilan.json'
MAPPING = 'orchestration/correspondances_geny.json'
SUIVI_COURSES = 'rattrapage_historiques/resolution_identites_courses.json'

SUPERVISION_HEADERS = (
    'Traitement', 'Indicateur', 'État', 'Dernière preuve (Paris)', 'Prochaine échéance (Paris)',
    'Mesure', 'Âge (min)', 'Cause / reprise', 'Définition', 'Source pmu-data',
)
REFERENTIEL_HEADERS = (
    'Type', 'Clé', 'Date course', 'Course PMU', 'Nom PMU', 'ID PMU', 'Nom Geny', 'ID Geny',
    'URL Geny', 'Correspondance', 'Historique courant', 'Performances relues',
    'Dernière recherche (Paris)', 'Dernière collecte (Paris)', 'Prochaine reprise (Paris)',
    'Motif / action', 'Preuve', 'Source pmu-data',
)


def prochain_tick(now, minutes, *, debut=None, jour=False):
    debut = max(now, debut or now).astimezone(timezone.utc)
    cursor = debut.replace(second=0, microsecond=0)
    while True:
        if cursor >= debut:
            local = cursor.astimezone(PARIS)
            if local.minute in minutes and (not jour or 7 <= local.hour < 21):
                return cursor.isoformat()
        cursor += timedelta(minutes=1)


def lignes_supervision(cache, now):
    state = lire(cache/CHECKPOINT)
    report = lire(cache/CONTROLE)
    increment = lire(cache/INCREMENTAL)
    backlog = lire(cache/RATTRAPAGE)
    plan = planifier(cache, now)
    cooldown = etat_cooldown_geny(cache, now, prod=increment)
    rows = [list(SUPERVISION_HEADERS)]

    def add(domaine, indicateur, statut, source, definition, *, last=None, next_at=None,
            mesure='', motif=''):
        stamp = instant(last)
        if stamp and stamp > now:
            statut = 'Horodatage futur'
            motif = 'Comparer la preuve UTC à l’instant de lecture du registre. ' + motif
        age = int((now-stamp).total_seconds()//60) if stamp else ''
        rows.append([domaine, indicateur, statut, nombre_paris(last) if stamp else '',
                     nombre_paris(next_at) if instant(next_at) else '', mesure, age, motif,
                     definition, PROVENANCE + source])

    tick = prochain_tick(now, (7, 22, 37, 52))
    global_at = instant(state.get('dernier_global_publie_utc'))
    nuit = creneau_nocturne(now)
    global_status = ('Créneau de jour fermé' if nuit else 'À reprendre' if report.get('global', {}).get('statut') == 'A_REPRENDRE'
                     else 'En retard' if global_at and now-global_at >= timedelta(hours=2)
                     else 'À exécuter' if plan['global_du'] else 'À jour')
    add('PMU', 'Cycle global J/J+1', global_status, CHECKPOINT,
        'Relecture Sheets après acquisition des deux programmes au cours du même cycle.',
        last=state.get('dernier_global_publie_utc'),
        next_at=prochain_tick(now, (7, 22, 37, 52),
                              debut=global_at+timedelta(hours=1) if global_at and global_at <= now else now, jour=True),
        motif='Reprise au prochain tick PMU éligible.' if global_status in ('À reprendre', 'En retard') else '')
    jalons = plan['jalons_dus']
    add('Prévisions', 'Jalons H-3 / H-2', 'À publier' if jalons else 'À surveiller', CHECKPOINT,
        'Couples course–jalon dus au moment de la lecture. Les versions certifiées restent dans jalons/.',
        last=state.get('dernier_jalon_publie_utc'), next_at=tick if jalons else plan['prochain_jalon_utc'],
        mesure=len(jalons))
    rapprochements = plan['rapprochements_dus']
    prochaines = []
    from .rapprochement_reunions import planifier_rapprochements
    planifier_rapprochements(cache, now, prochaines=prochaines)
    add('Résultats', 'Rapprochements H+30', 'À rapprocher' if rapprochements else 'À surveiller', CHECKPOINT,
        'Nombre de réunions à traiter. Échéance 30 minutes après le dernier départ de chaque réunion.',
        last=state.get('dernier_rapprochement_publie_utc'),
        next_at=tick if rapprochements else min(prochaines, default=None), mesure=len(rapprochements))
    add('Résultats', 'Arrivée officielle', 'Vérifiée' if state.get('derniere_arrivee_verifiee_utc') else 'Preuve attendue',
        CHECKPOINT, 'Dernière observation PMU d’un podium relu dans les résultats Sheets.',
        last=state.get('derniere_arrivee_verifiee_utc'))
    add('Sheets', 'Publication PMU', 'Relue' if report.get('publication_reussie') else 'À vérifier',
        CHECKPOINT, 'Dernière relecture d’une publication métier PMU, y compris ciblée.',
        last=state.get('derniere_publication_pmu_utc'), next_at=tick)
    status = Counter(error.get('motif', 'Motif non renseigné') for error in report.get('erreurs', []))
    add('Supervision', 'Contrôle PMU', 'Écart détecté' if status else 'Contrôle enregistré' if report else 'Non observé',
        CONTROLE, 'Anomalies détectées lors du dernier contrôle de production.',
        last=report.get('controle_utc'), mesure=sum(status.values()),
        motif=' · '.join(f'{motif} ({n})' for motif, n in sorted(status.items())))
    incident = cooldown.get('dernier_incident') or {}
    add('Geny', 'Accès à la source', 'En pause' if cooldown['actif'] else 'Disponible pour la reprise',
        'etat_persistant.json', 'Dernier refus observé et fin du délai commun de suspension.',
        last=incident.get('utc'), next_at=cooldown['echeance_utc'] if cooldown['actif'] else None,
        mesure=str(incident.get('code', '')), motif='Respecter le délai de reprise Geny.' if cooldown['actif'] else '')
    for domain, path, queue in (('Geny incrémental', INCREMENTAL, increment), ('Geny rattrapage', RATTRAPAGE, backlog)):
        cycle, bilan = queue.get('collecte_cycle') or {}, queue.get('bilan') or {}
        add(domain, 'Carrières acquises', queue.get('statut', 'Non observé'), path,
            'Carrières distinctes complètes validées pendant le dernier passage.',
            last=queue.get('derniere_acquisition_validee_utc') or cycle.get('controle_utc'),
            mesure=cycle.get('carrieres_completes_distinctes', ''),
            next_at=cooldown['echeance_utc'] if cooldown['actif'] else None,
            motif=queue.get('motif_ordonnancement') or queue.get('motif_fin_passage', ''))
        publication = queue.get('publication_cycle') or {}
        dernier_passage = instant(cycle.get('controle_utc'))
        derniere_publication = instant(publication.get('controle_utc'))
        if ('performances_ajoutees_et_confirmees_sheets' in cycle and dernier_passage
                and (not derniere_publication or dernier_passage >= derniere_publication)):
            publication = cycle
        add(domain, 'Performances publiées', queue.get('sync_kpi', 'Non observé'), path,
            'Performances ajoutées et confirmées pendant le dernier passage de publication.',
            last=publication.get('controle_utc'), mesure=publication.get('performances_ajoutees_et_confirmees_sheets', ''),
            motif=f"Synchronisations en attente : {bilan['synchronisations_en_attente']}"
            if 'synchronisations_en_attente' in bilan else '')
        add(domain, 'Requêtes Geny', 'Mesuré' if 'requetes_http_geny' in cycle else 'Non mesuré', path,
            'Requêtes réseau Geny observées lors du dernier passage, hors réponses servies du cache HTTP.',
            last=cycle.get('controle_utc'), mesure=cycle.get('requetes_http_geny', ''))
    bilan = backlog.get('bilan') or {}
    lot = backlog.get('lot_96') or {}
    total = bilan.get('cibles_inventoriees')
    add('Geny rattrapage', 'Inventaire global', backlog.get('phase_reprise', 'Non observé'), RATTRAPAGE,
        'Cibles complétées / cibles de l’inventaire. Plusieurs contextes peuvent désigner un même cheval.',
        last=backlog.get('maj_utc'), mesure=f"{bilan['cibles_completees']} / {total}" if total else '',
        motif=backlog.get('motif_fin_passage', ''))
    add('Geny rattrapage', 'Lot de référence', 'Suivi' if lot else 'Non observé', RATTRAPAGE,
        'Cibles dont la publication est attestée / taille du lot de référence.',
        last=backlog.get('maj_utc'), mesure=f"{lot['publiees']} / {lot['cibles']}" if lot else '')
    return rows


def lignes_referentiel(cache, history, now):
    from .historiques_incrementaux import course_geny_connue
    from .identites_chevaux import courses_verifiees, preuve_resolution_valide
    from .liaison_chevaux_v22 import nom_normalise
    from .rattrapage_historiques import QUEUE, cle_contexte, engagement_canonique
    from .reconciliation_historiques import ReconciliationHistoriques

    diagnostic = ReconciliationHistoriques(cache, history, now=now)
    mapping = lire(cache/MAPPING)
    suivi = lire(cache/SUIVI_COURSES).get('courses', {})
    preuves = {p['engagement']: p for p in courses_verifiees()}
    rows = [list(REFERENTIEL_HEADERS)]
    courses = {}
    for path in sorted((cache/'orchestration').glob('????-??-??.json')):
        courses.update({f'{path.stem}_{code}': course
                        for code, course in lire(path).get('courses', {}).items()})
    for engagement in sorted(mapping.keys() | courses.keys() | suivi.keys() | preuves.keys()):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}_R\d+C\d+', engagement):
            continue
        day, code = engagement.split('_')
        course = courses.get(engagement, {})
        decision = course.get('rapprochement_geny') or {}
        cid = course_geny_connue(cache, engagement).removeprefix('GENY-')
        manifeste = lire(cache/'manifestes'/f'GENY-{cid}.json') if cid else {}
        proof = preuves.get(engagement, {})
        recherche = suivi.get(engagement, {})
        statut = CONFIRMEE if cid else decision.get('statut') or NON_EFFECTUEE
        source = (MAPPING if engagement in mapping else SUIVI_COURSES if engagement in suivi
                  else f'orchestration/{day}.json')
        rows.append(['Course', 'course:'+engagement, vers_nombre('Date', day), code, course.get('nom', ''),
                     '', '', cid, proof.get('source_url') or manifeste.get('course_url')
                     or (f'https://www.geny.com/course/{cid}/partants-pronostics' if cid else ''),
                     statut, '', '', nombre_paris(recherche['lecture_utc']) if instant(recherche.get('lecture_utc')) else '',
                     '', '', recherche.get('statut') or decision.get('motif', ''),
                     decision.get('methode') or ('Correspondance archivée' if cid else ''), PROVENANCE+source])

    stock = lire(cache/QUEUE).get('chevaux', {})
    observations = [(horse, str(QUEUE)) for horse in stock.values()]
    observations.extend((horse, INCREMENTAL) for horse in lire(cache/INCREMENTAL).get('chevaux', {}).values())
    for path in sorted((cache/'sources_geny/identites').glob('*.json')):
        proof = lire(path)
        if preuve_resolution_valide(proof):
            observations.append(({
                'nom': proof['nom_attendu'], 'id_pmu': proof.get('id_pmu'),
                'geny': proof['geny'], 'engagement': proof.get('engagement'), 'numero': proof.get('numero'),
                'resolution_utc': proof.get('resolution_utc'),
            }, str(path.relative_to(cache))))
    chevaux = {}
    for horse, source in observations:
        name = horse.get('nom')
        if not nom_normalise(name):
            continue
        engagement = engagement_canonique(horse.get('engagement'))
        number = str(horse.get('numero') or '')
        pmu_id = str(horse.get('_id_pmu_correspondance') or horse.get('id_pmu') or '')
        if not horse.get(CHAMP):
            horse = {**horse, **diagnostic.stock_entry(horse)}
            pmu_id = str(horse.get('_id_pmu_correspondance') or pmu_id)
        gid = horse.get('_id_geny_correspondance') or ''
        link = diagnostic.index.noms[nom_normalise(name)].get(gid, {})
        tentative = diagnostic.tentatives.retrouver(engagement, number, name, pmu_id)
        search = max(filter(None, (instant(tentative.get('utc')), instant(horse.get('resolution_utc')))), default=None)
        acquisition = instant(horse.get('historique_maj_utc'))
        retry = instant(tentative.get('reprise_utc') or horse.get('prochain_essai_utc') or horse.get('prochaine_sync_utc'))
        echec = horse.get('dernier_echec_collecte') or {}
        key = 'geny:'+gid if gid else 'pmu:'+pmu_id if pmu_id else cle_contexte(horse)
        day, _, code = engagement.partition('_')
        row = ['Cheval', key, vers_nombre('Date', day) if code else '', code, name, pmu_id,
               link.get('nom', ''), gid, link.get('url_geny', ''), horse.get(CHAMP) or NON_EFFECTUEE,
               horse.get('historique_statut', 'HISTO_NON_COLLECTE'),
               horse.get('historique_nb_courses_datees', 0), nombre_paris(search) if search else '',
               nombre_paris(acquisition) if acquisition else '', nombre_paris(retry) if retry else '',
               tentative.get('motif') or echec.get('statut') or horse.get('motif_actualisation', ''),
               link.get('preuve', ''), PROVENANCE+source]
        score = (row[9] == CONFIRMEE, bool(pmu_id), search or datetime.min.replace(tzinfo=timezone.utc),
                 bool(link), bool(code))
        previous = chevaux.get(key)
        if not previous or score > previous[0]:
            chevaux[key] = (score, row)
    confirmed_ids = {row[5] for _, row in chevaux.values() if row[7] and row[5]}
    rows.extend(row for key, (_, row) in sorted(chevaux.items())
                if not (key.startswith('pmu:') and row[5] in confirmed_ids and row[9] != AMBIGUE))
    return rows


def _style(name, sheet_id, cols, timestamps):
    from dashboard.trot_analytics.dates import DATE_PATTERN, DATETIME_PATTERN
    cell_range = {'sheetId': sheet_id, 'startColumnIndex': 0, 'endColumnIndex': cols}
    header = {**cell_range, 'startRowIndex': 0, 'endRowIndex': 1}
    requests = [
        {'repeatCell': {'range': header, 'cell': {'userEnteredFormat': {
            'backgroundColor': {'red': .08, 'green': .24, 'blue': .31},
            'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True},
            'verticalAlignment': 'MIDDLE', 'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat'}},
        {'updateDimensionProperties': {'range': {'sheetId': sheet_id, 'dimension': 'ROWS',
            'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 42}, 'fields': 'pixelSize'}},
        {'addFilterView': {'filter': {'title': 'Tous les indicateurs' if name == SUPERVISION else 'Toutes les correspondances',
                                    'range': cell_range}}},
    ]
    if name == REFERENTIEL:
        requests.extend({'addFilterView': {'filter': {'title': title, 'range': cell_range, 'filterSpecs': [
            {'columnIndex': 0, 'filterCriteria': {'hiddenValues': [hide]}}]}}}
            for title, hide in (('Courses PMU–Geny', 'Cheval'), ('Chevaux PMU–Geny', 'Course')))
    for col in range(cols):
        kind = ('DATE', DATE_PATTERN) if name == REFERENTIEL and col == 2 else (
            ('DATE_TIME', DATETIME_PATTERN) if col in timestamps else None)
        col_range = {'sheetId': sheet_id, 'startColumnIndex': col, 'endColumnIndex': col+1}
        if kind:
            requests.append({'repeatCell': {'range': {**col_range, 'startRowIndex': 1},
                'cell': {'userEnteredFormat': {'numberFormat': {'type': kind[0], 'pattern': kind[1]}}},
                'fields': 'userEnteredFormat.numberFormat'}})
        width = ((135, 205, 170, 165, 175, 105, 85, 270, 335, 190) if name == SUPERVISION else
                 (85, 155, 105, 100, 200, 105, 205, 100, 205, 230, 240, 110, 170, 170, 170, 270, 170, 190))[col]
        requests.append({'updateDimensionProperties': {'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
            'startIndex': col, 'endIndex': col+1}, 'properties': {'pixelSize': width}, 'fields': 'pixelSize'}})
    return requests


def _publier_vue(engine, name, rows, props, timestamps):
    from .moteur_sheets import ErreurSynchronisation
    from .sync_google_sheets import colname, lire_feuille_complete

    width = len(rows[0])
    rows = [['' if value is None else value for value in row] for row in rows]
    if props is None:
        used_ids = {item['sheetId'] for item in engine.metadata().values()}
        sheet_id = next(i for i in range(1, len(used_ids)+2) if i not in used_ids)
        props = {'sheetId': sheet_id, 'title': name, 'gridProperties': {
            'rowCount': max(50, len(rows)), 'columnCount': width, 'frozenRowCount': 1,
            'frozenColumnCount': 2, 'hideGridlines': True}}
        engine.check(engine.session.post(engine.base+':batchUpdate', json={'requests': [
            {'addSheet': {'properties': props}}, *_style(name, sheet_id, width, timestamps),
        ]}, timeout=30))
        previous = []
    else:
        previous = lire_feuille_complete(engine.session, engine.base, name, props, raw_dates=True)
        if previous and (previous[0] != rows[0] or any(len(row) > width for row in previous)):
            raise ErreurSynchronisation(f'En-têtes inattendus dans {name}')
    sheet_id = props['sheetId']
    structure = []
    height = props['gridProperties']['rowCount']
    if len(rows) > height:
        structure.insert(0, {'appendDimension': {'sheetId': sheet_id, 'dimension': 'ROWS',
                                                 'length': len(rows)-height}})
        props['gridProperties']['rowCount'] = len(rows)
    if structure:
        engine.check(engine.session.post(engine.base+':batchUpdate', json={'requests': structure}, timeout=30))

    def equal(a, b):
        return all(x == y or (type(x) in (int, float) and type(y) in (int, float)
                              and math.isclose(x, y, rel_tol=0, abs_tol=1e-10))
                   for x, y in zip(a+['']*(width-len(a)), b+['']*(width-len(b))))

    n = max(len(previous), len(rows))
    data = []
    for start in range(0, n, 300):
        stop = min(start+300, n)
        before = [previous[i] if i < len(previous) else [] for i in range(start, stop)]
        after = [rows[i] if i < len(rows) else ['']*width for i in range(start, stop)]
        if any(not equal(a, b) for a, b in zip(before, after)):
            data.append({'range': f"'{name}'!A{start+1}:{colname(width)}{stop}", 'values': after})
    for start in range(0, len(data), 4):
        engine.check(engine.session.post(engine.base+'/values:batchUpdate',
            json={'valueInputOption': 'RAW', 'data': data[start:start+4]}, timeout=60))
    if data:
        final = lire_feuille_complete(engine.session, engine.base, name, props, raw_dates=True)
        if len(final) != len(rows) or any(not equal(a, b) for a, b in zip(rows, final)):
            raise ErreurSynchronisation(f'Relecture de {name} différente de la projection')
    print(f'SUPERVISION_SHEETS onglet={name} lignes_verifiees={len(rows)-1} plages_ecrites={len(data)}', flush=True)


def synchroniser(engine, *, avec_referentiel, now=None):
    from .moteur_sheets import ErreurSynchronisation, verrou_local
    from .sync_google_sheets import SHEET_TABS

    now = now or datetime.now(timezone.utc)
    with verrou_local(engine.spreadsheet):
        tables = engine.metadata()
        _publier_vue(engine, SUPERVISION, lignes_supervision(engine.cache, now), tables.get(SUPERVISION), {3, 4})
        if avec_referentiel or REFERENTIEL not in tables:
            history = tables.get(SHEET_TABS[1])
            if not history:
                raise ErreurSynchronisation('Historique source absent du registre')
            published = engine._lire_historique_courant(history)
            publier_referentiel(engine, published, tables.get(REFERENTIEL), now)


def publier_referentiel(engine, published, properties, now=None):
    rows = lignes_referentiel(engine.cache, published, now or datetime.now(timezone.utc))
    _publier_vue(engine, REFERENTIEL, rows, properties, {12, 13, 14})
