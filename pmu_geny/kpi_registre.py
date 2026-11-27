"""KPI du registre calcules depuis les sources, sans formules dependantes des lignes."""
from collections import defaultdict
from statistics import median
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math

from dashboard.trot_analytics.correspondance_geny import CHAMP, COLONNE, CONFIRMEE, KPI_PREFIX, STATUTS, statut_ligne
from dashboard.trot_analytics.dates import afficher_indicateur, cle_indicateur

KPI_TAB = 'Data Quality & KPI'
PREFIXES_ANCIENNES_ECHEANCES = ('Échéances · H2 ', 'Échéances · H1 ')
PERIMETRE_RESULTATS = 'Registre · Courses distinctes du périmètre résultats et prévisions'
INDICATEURS_RESULTATS = ('Courses avec arrivée officielle', 'Courses avec arrivée vérifiée', 'Courses évaluées')
DIMENSIONS_KPI = {
    KPI_PREFIX: COLONNE,
    'Cotes PMU · ': 'Cotes PMU',
    'Collecte · ': 'Collecte',
    'Registre · ': 'Registre',
    'Historique courant · ': 'Historique courant',
}

def _load(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def _nombre(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None

def calculer_kpi(cache, source=None, now=None, *, sheets_courses=None):
    from .sync_google_sheets import source_rows, limiter_cours_registre
    from .liaison_chevaux_v22 import nom_normalise
    from .partants_actuels_v21 import ferrure_normalisee
    cache=Path(cache);now=now or datetime.now(timezone.utc)
    source=source if source is not None else limiter_cours_registre(source_rows(cache))
    participants=list(source['Courses & Prévisions'].values())
    reports=list(source['Résultats & Analyse'].values())
    courses_previsions = {row['course_key'] for row in participants}
    courses_resultats = {row['course_key'] for row in reports}
    count=len(participants)
    arrived=0;verified=0;scores=[]
    for row in reports:
        if not row.get('arrivee_officielle_numeros'):continue
        arrived+=1
        key=f"{row['date_course']}_{row['rncn']}"
        result=_load(cache/'arrivees'/f'{key}.json')
        forecast=_load(cache/'pronostics'/f'{key}_direct.json')
        try:
            departure=datetime.fromisoformat(row['heure_depart_paris'])
            checked=datetime.fromisoformat(result['verifie_utc'])
            if result.get('source') != 'PMU_API_PARTICIPANTS':continue
            if not departure<checked<=now:continue
            podium={int(h['numero']) for h in result['arrivee'] if h['rang'] in (1,2,3)}
            if len(podium)!=3:continue
            if row.get('reunion_pmu'):
                if row.get('rapprochement_arrivee_statut') != 'ARRIVEE_OFFICIELLE':
                    continue
                verified += 1
                score = row.get('score_direct')
                if row.get('statut_evaluation') == 'EVALUE' and score in (0, 1, 2, 3):
                    scores.append(score)
                continue
            verified+=1
            predicted=[int(h['numero']) for h in forecast.get('top3',[])]
            created=datetime.fromisoformat(forecast['calcul_utc'])
            if len(predicted)==len(set(predicted))==3 and created<departure:
                scores.append(len(set(predicted)&podium))
        except (ValueError,KeyError,TypeError):continue
    history_rows = participants if sheets_courses is None else [
        row for row in sheets_courses if row.get('course_key') and row.get('numero') and row.get('cheval')
    ]
    linked=sum(str(r.get('historique_statut','')).startswith('HISTO_OK') for r in history_rows)
    has_history=sum((_nombre(r.get('historique_nb_courses_datees')) or 0)>0 for r in history_rows)
    def ferrure_sourcee(row):
        code = ferrure_normalisee(row.get('ferrure'))
        if row.get('actuel_statut') in ('CODE_INCONNU', 'NON_RECUPEREE', 'FERRURE_NON_RECUPEREE'):
            return ''
        if code == 'F' and row.get('actuel_statut') not in (
                'CODE_RECONNU', 'CONVENTION_PMU', 'FERRURE_DISPONIBLE_SOURCEE', 'PMU_FERRURE_DISPONIBLE'):
            return ''
        return code
    def nonempty(field):return sum(bool(str(r.get(field) if r.get(field) is not None else '').strip()) for r in participants)
    def metric(label,value,definition):return (label,(value,definition))
    active=_load(cache/'ml/modele_experimental_actif.json')
    ml_metrics=[]
    if active:
        for label,field,definition in (
            ('État','statut','Candidat expérimental distinct du modèle promu ; scores non calibrés.'),
            ('Courses apprises','courses','Courses admissibles effectivement utilisées pour le dernier entraînement.'),
            ('Observations apprises','lignes','Observations cheval-course utilisées ; variables manquantes imputées.'),
            ('Entraînement UTC','entrainement_utc','Date du fit effectif, conservée si les données sont inchangées.'),
            ('Vérification UTC','verification_utc','Dernier contrôle du jeu disponible, distinct du dernier fit.')):
            ml_metrics.append(metric('ML expérimental · '+label,active.get(field,''),definition))
    maturity = _load(cache/'ml/maturite.json')
    if maturity:
        ml_metrics.append(metric('Maturité ML · Contrôle UTC', maturity.get('controle_utc', maturity.get('entrainement_utc', '')),
                                 'Heure du dernier calcul de maturité.'))
        quality = maturity['couverture']
        prospective = maturity.get('prospective', {})
        comparison = prospective.get('comparaison') or {}
        interval = comparison.get('ic95_bootstrap_par_course', ['', ''])
        serving_version = maturity.get('version_en_service', '')
        serving_status = maturity.get('maturite_en_service', 'Aucun modèle disponible.')
        if not serving_version and active.get('statut') == 'ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE':
            serving_version = active.get('sha256_modele', '')
            serving_status = 'EXPÉRIMENTAL · classement non calibré.'
        fields = [
            ('Statut candidat', maturity['maturite'], maturity['etat']),
            ('Version candidate', maturity.get('version', ''), 'SHA-256 du modèle figé pour l’évaluation.'),
            ('Version en service', serving_version, serving_status),
            ('Courses admissibles', maturity['courses'], 'Captures pré-départ appariées à une arrivée admissible.'),
            ('Observations admissibles', maturity['lignes'], 'Une observation par cheval et par course capturée.'),
            ('Courses qualifiantes', maturity['courses_qualifiantes'], 'Courses du schéma courant avec capture et arrivée sourcées.'),
            ('Observations qualifiantes', maturity['observations_qualifiantes'], 'Observations du schéma courant sur les courses qualifiantes.'),
            ('Taux de complétude', quality['completude'] if quality['observations'] else '', 'Part des observations qualifiantes avec forme PMU, distance, discipline, âge, sexe et gains.'),
            ('Courses prospectives appariées', prospective.get('courses', 0), 'Même relevé PMU et preuve de publication du TOP3 direct avant départ.'),
            ('Taux de complétude prospective', prospective.get('completude', ''), 'Six critères essentiels sur les prévisions de la cohorte prospective.'),
            ('Moyenne prospective ML', prospective.get('moyenne_ml'), 'Nombre moyen de chevaux du podium retrouvés sur trois.'),
            ('Moyenne prospective direct', prospective.get('moyenne_direct'), 'Nombre moyen sur les mêmes courses et au même instant de relevé.'),
            ('Écart prospectif ML − direct', comparison.get('ecart_moyen'), 'Écart moyen de chevaux trouvés par course appariée.'),
            ('Borne basse IC 95 %', interval[0], 'Bootstrap apparié par course, différence ML − direct.'),
            ('Borne haute IC 95 %', interval[1], 'Bootstrap apparié par course, différence ML − direct.'),
        ]
        for mode in ('ML', 'direct'):
            fields.extend([
                (f'Taux de 3 sur 3 · {mode}', prospective.get(f'taux_3_sur_3_{mode.lower()}'),
                 'Proportion des courses prospectives avec trois chevaux du podium retrouvés.'),
                (f'Taux d’au moins 2 sur 3 · {mode}', prospective.get(f'taux_au_moins_2_sur_3_{mode.lower()}'),
                 'Proportion des courses prospectives avec au moins deux chevaux du podium retrouvés.'),
            ])
        for stage, thresholds in maturity['seuils'].items():
            fields.append((f'Seuils {stage.lower()}',
                           f"{thresholds['courses']} courses / {thresholds['observations']} observations / "
                           f"{thresholds['prospectives']} prospectives / {thresholds['completude']:.0%}",
                           'Effectifs et complétude minimaux de la cohorte.'))
        for criterion, present in quality['criteres'].items():
            fields.append((f'Couverture · {criterion}', present / quality['observations'] if quality['observations'] else '',
                           f"{present} observations qualifiantes renseignées sur {quality['observations']}."))
        ml_metrics.extend(metric('Maturité ML · '+label, '' if value is None else value, definition)
                          for label, value, definition in fields)
    performance=_load(cache/'ml/performance_prospective.json')
    operational=[]
    if performance:
        operational.append(metric('ML prospectif · Contrôle UTC', performance.get('controle_utc', ''),
                                  'Dernier contrôle des prévisions et des arrivées appariées.'))
    for label,field,definition in (
        ('Courses évaluées','courses','Courses communes direct/ML avec certificat de publication antérieur au départ et arrivée PMU vérifiée.'),
        ('Moyenne ML sur 3','moyenne_ml','Moyenne prospective ; vide si aucune course admissible.'),
        ('Moyenne direct comparable sur 3','moyenne_direct','Même ensemble de courses que le ML prospectif.'),
        ('Écart ML contre direct','ecart_ml_direct','Écart moyen sur courses appariées ; aucune garantie de gain futur.'),
        ('TOP3 ML exacts','exact_3_sur_3_ml','Nombre de courses avec trois chevaux retrouvés, sur le dénominateur Courses évaluées.')):
        operational.append(metric('ML prospectif · '+label,performance.get(field) if performance.get(field) is not None else '',definition))
    start = performance.get('candidat_depart')
    if start:
        interval = (start.get('comparaison') or {}).get('ic95_bootstrap_par_course', (None, None))
        for label, value, definition in (
            ('Contrôle UTC', performance.get('controle_utc'), 'Dernier calcul prospectif.'),
            ('Statut', start['statut'], 'État de l’évaluation de la variante de forme par mode de départ.'),
            ('Courses direct évaluables', start.get('direct_evaluable'), 'TOP3 direct relu dans Sheets avant départ et arrivée PMU vérifiée.'),
            ('Courses appariées', start['courses'], 'Variante et référence conservées dans la même version du TOP3 direct.'),
            ('Moyenne variante sur 3', start.get('moyenne'), 'Chevaux du podium retrouvés, sur les courses appariées.'),
            ('Moyenne direct sur 3', start.get('moyenne_direct'), 'Référence directe sur les mêmes courses.'),
            ('Écart variante − direct', start.get('ecart_moyen'), 'Écart de chevaux retrouvés par course appariée.'),
            ('Borne basse IC 95 %', interval[0], 'Bootstrap des écarts appariés par course.'),
            ('Borne haute IC 95 %', interval[1], 'Bootstrap des écarts appariés par course.'),
            ('Courses avec 3 sur 3', start.get('exact_3_sur_3'), 'Variante expérimentale, sur les courses appariées.'),
            ('Courses avec au moins 2 sur 3', start.get('au_moins_2_sur_3'), 'Variante expérimentale, sur les courses appariées.'),
        ):
            operational.append(metric('Autostart prospectif · ' + label, '' if value is None else value, definition))
    from .echeances_production import PARIS, PHASES, ANTICIPATION, instant, reunions_du_jour
    from .rapprochement_reunions import aggreger
    day = now.astimezone(PARIS).date().isoformat()
    reunions = list(reunions_du_jour(cache, day))
    for phase, offset in PHASES.items():
        expected = ontime = missed = 0
        for reunion in reunions:
            first = reunion['premier_depart']
            if not first or now < first-offset-ANTICIPATION:
                continue
            expected += 1
            proof = _load(cache/'jalons/reunions'/f"{reunion['reunion']}.json").get(phase, {})
            ok = (proof.get('statut') == 'PUBLIE_A_TEMPS'
                  and instant(proof.get('echeance')) == first-offset
                  and (published := instant(proof.get('publication_utc'))) is not None
                  and first-offset-ANTICIPATION <= published <= min(now, first-offset)
                  and instant(proof.get('reference_utc')) == first
                  and proof.get('courses_attendues') == sorted(c['code'] for c in reunion['attendues']))
            ontime += int(ok)
            missed += int(now > first-offset and not ok)
        label = f'H-{phase[1:]}'
        operational.extend([
            metric('Échéances · '+label+' ouvertes', expected, 'Réunions dont la fenêtre est ouverte aujourd’hui.'),
            metric('Échéances · '+label+' publiées à temps', ontime, 'Toutes les courses attendues certifiées à temps.'),
            metric('Échéances · '+label+' dépassées sans preuve à temps', missed, 'Réunions hors délai sans certificat ponctuel.')])
    rapprochements = [_load(path) for path in (cache/'rapprochements').glob('????-??-??_R*.json')]
    operational.append(metric('H+30 · Arrivées à reprendre',
                              sum(len(r.get('arrivees_a_reprendre', [])) for r in rapprochements),
                              'Arrivées manquantes ou non vérifiées des réunions déjà traitées.'))
    for days in (1, 7, 30):
        since = (now.astimezone(PARIS).date() - timedelta(days=days-1)).isoformat()
        results = aggreger(row for r in rapprochements if since <= r.get('date', '') <= day
                           for row in r.get('courses', {}).values())
        for label, values in sorted(results.items()):
            prefix = f'H+30 · {days} j · {label}'
            operational.append(metric(prefix + ' · Moyenne sur 3', values['moyenne_sur_3'],
                                      'Chevaux du podium retrouvés à partir des versions figées et relues.'))
            operational.append(metric(prefix + ' · Courses', values['courses'],
                                      'Courses avec version publiée et arrivée officielle.'))
    if sheets_courses is not None:
        from .echeances_production import PARIS
        today = now.astimezone(PARIS).date()
        operational.append(metric('Registre · Lecture Sheets UTC', now.isoformat(),
                                  'Relecture de Courses & Prévisions utilisée pour les KPI J/J+1.'))
        for offset in (0, 1):
            date = (today + timedelta(days=offset)).isoformat()
            prefix = ('J' if offset == 0 else 'J+1') + ' · '
            cohort = [r for r in sheets_courses if r.get('date_course') == date
                      and r.get('non_partant') == 'PARTANT']
            counts = {
                'Partants confirmés': len(cohort),
                'Ferrures renseignées': sum(bool(ferrure_sourcee(r)) for r in cohort),
                'Modes de départ documentés': sum(bool(r.get('course_mode_depart')) for r in cohort),
                'Partants en départ autostart documenté': sum(r.get('course_mode_depart') == 'Autostart' for r in cohort),
                'Positions autostart renseignées': sum((_nombre(r.get('position_autostart')) or 0) > 0 for r in cohort),
                'Lignes autostart renseignées': sum((_nombre(r.get('ligne_autostart')) or 0) > 0 for r in cohort),
                'Reculs renseignés': sum(_nombre(r.get('recul_depart_m')) is not None for r in cohort),
                'Cotes PMU renseignées': sum((_nombre(r.get('top3_cotes_valeur')) or 0) > 0
                                             and bool(r.get('cote_releve_utc')) for r in cohort),
                'Ferrures inconnues': sum(not ferrure_sourcee(r) for r in cohort),
                'Ferrés (F)': sum(ferrure_sourcee(r) == 'F' for r in cohort),
                'Historiques identifiés': sum(str(r.get('historique_statut', '')).startswith(('HISTO_OK','HISTO_PARTIEL')) for r in cohort),
                'Historiques partiels': sum(str(r.get('historique_statut', '')).startswith('HISTO_PARTIEL') for r in cohort),
                'Historiques complets': sum(str(r.get('historique_statut', '')).startswith('HISTO_OK') for r in cohort),
                'Historiques publiés avec performances': sum((_nombre(r.get('historique_nb_courses_datees')) or 0) > 0 for r in cohort),
            }
            operational.extend(metric(prefix + label, value, f'{date} · Partants confirmés dans Courses & Prévisions.')
                               for label, value in counts.items())
    backfill = _load(cache/'rattrapage_historiques/bilan.json')
    if backfill:
        from .echeances_production import etat_cooldown_geny
        from .rattrapage_historiques import (
            actualiser_cohortes, bilan_lot_96, bornes_cohortes, derniere_acquisition_validee,
        )
        cooldown = etat_cooldown_geny(cache, now)
        incident = cooldown['dernier_incident'] or {}
        for label, value, definition in (
            ('Dernier incident Geny UTC', incident.get('utc'), 'Dernier refus Geny commun aux collecteurs.'),
            ('Dernier code Geny', incident.get('code'), 'Code du dernier refus commun.'),
            ('Cooldown Geny actif', 'OUI' if cooldown['actif'] else 'NON', 'État à la lecture des KPI.'),
            ('Échéance du cooldown Geny UTC', cooldown['echeance_utc'], 'Dernière échéance commune, y compris expirée.'),
            ('Dernière acquisition validée UTC', derniere_acquisition_validee(cache, backfill),
             'Date de capture de la dernière carrière complète validée par le rattrapage.'),
        ):
            operational.append(metric('Rattrapage · ' + label, value or '', definition))
        for name, field in [('Dernière tentative Geny UTC', 'collecte_tentee_utc'),
                            ('Dernière décision UTC', 'controle_ordonnancement_utc'),
                            ('Dernière mise à jour UTC', 'maj_utc'),
                            ('Révision inventaire', 'revision_inventaire')]:
            operational.append(metric('Rattrapage · ' + name, backfill.get(field, ''),
                                      'État durable du lot de rattrapage.'))
        last_reason = backfill.get('motif_fin_passage', '')
        operational.append(metric('Rattrapage · Motif de fin', last_reason,
                                  'Motif historique inscrit au bilan du rattrapage.'))
        decision = backfill.get('motif_ordonnancement')
        if decision is None and backfill.get('controle_ordonnancement_utc'):
            decision = last_reason
        operational.append(metric('Rattrapage · Dernier motif d’ordonnancement', decision or '',
                                  'Décision à la date du dernier contrôle d’ordonnancement.'))
        counts = backfill.get('bilan', {})
        for label, field, definition in (
            ('Chevaux non identifiés (noms distincts)', 'noms_distincts_sans_identifiant',
             'Noms exacts normalisés distincts parmi les contextes sans identifiant Geny.'),
            ('Contextes sans identifiant Geny', 'contextes_distincts_sans_identifiant',
             'Contextes du lot sans identifiant Geny, après dédoublonnage des cibles équivalentes.'),
            ('Chevaux identifiés sans carrière complète', 'identifiants_sans_carriere_complete',
             'Identifiants Geny distincts du lot sans capture complète validée.'),
        ):
            operational.append(metric('Rattrapage · '+label, counts.get(field, ''), definition))
        back_state = _load(cache / 'rattrapage_historiques/etat.json')
        cohorts = backfill.get('cohortes', {})
        if back_state.get('chevaux'):
            actualiser_cohortes(cache, back_state)
            cohorts = bornes_cohortes(back_state)
            lot = bilan_lot_96(back_state)
            if lot:
                cohorts['lot de 96'] = lot
        for cohort, data in cohorts.items():
            for label, value in data.items():
                operational.append(metric(f'Rattrapage · {cohort} · {label}', value,
                                          'Cibles du lot suivies par leur clé d’inventaire.'))
    queue=_load(cache/'collecte_incrementale/etat.json')
    for label,field in [('Captures complètes','captures_validees'),('Captures partielles','captures_partielles'),('Rejets','collectes_rejetees')]:
        operational.append(metric('Collecte · '+label+' dernier passage',queue.get('bilan',{}).get(field,''),
                                  'Compteur du passage horodaté '+str(queue.get('passage_utc','non disponible'))))
    for offset, label in ((0, 'J'), (1, 'J+1')):
        date = (now.astimezone(PARIS).date() + timedelta(days=offset)).isoformat()
        programme = _load(cache/'sources_pmu'/f'programme_{date}.json')
        operational.append(metric(f'Collecte · PMU · Programme {label} UTC', programme.get('date_controle_utc', ''),
                                  'Acquisition du programme PMU, indépendante de sa publication dans Sheets.'))
    pmu = _load(cache/'orchestration/production_etat.json')
    acquisition_geny = instant(queue.get('derniere_acquisition_validee_utc'))
    if not acquisition_geny or acquisition_geny > now:
        journal = _load(cache/'etat_persistant.json')
        acquisition_geny = max((stamp for h in journal.get('chevaux', {}).values()
                                if h.get('origine') == 'COLLECTE_INCREMENTALE_PRODUCTION'
                                and h.get('statut') == 'COMPLET'
                                and (stamp := instant(h.get('historique_complet_au_utc')))
                                and stamp <= now), default=None)
    publication_geny = max((stamp for h in queue.get('chevaux', {}).values()
                            if h.get('sync_details', {}).get('Historique chevaux', {}).get(
                                'controle', {}).get('statut') == 'VALIDE'
                            and (stamp := instant(h.get('sync_utc'))) and stamp <= now), default=None)
    operational.extend([
        metric('Collecte · PMU · Publication globale UTC', pmu.get('dernier_global_publie_utc', ''),
               'Dernière publication globale attestée à partir de la relecture Sheets.'),
        metric('Collecte · Geny · Acquisition incrémentale validée UTC',
               acquisition_geny.isoformat() if acquisition_geny else '',
               'Date source de la dernière carrière complète validée dans la file incrémentale.'),
        metric('Collecte · Geny · Publication incrémentale vérifiée UTC',
               publication_geny.isoformat() if publication_geny else '',
               'Dernière carrière incrémentale relue avec contrôle valide dans Sheets.'),
    ])
    from .cotes_v19 import cote_valide, instant
    from .auto_v18 import PARIS
    odds_cohorts = defaultdict(list)
    ages = []
    eligible = collected = 0
    for row in (sheets_courses if sheets_courses is not None else participants):
        departure = instant(row.get('heure_depart_paris'))
        if not departure or departure.astimezone(PARIS).date() > now.astimezone(PARIS).date():
            continue
        odds_cohorts[row['course_key']].append(row)
        if row.get('non_partant') == 'NON_PARTANT':
            continue
        eligible += 1
        observed = instant(row.get('cote_releve_utc'))
        if cote_valide(row.get('top3_cotes_valeur')) is None or not observed or not observed < departure or observed > now:
            continue
        collected += 1
        reported = instant(row.get('cote_rapport_utc')) or observed
        reported = min(reported, observed)
        ages.append((min(now, departure) - reported).total_seconds() / 60)
    odds_complete = sum(
        {str(row.get('top3_cotes_rang')) for row in rows if row.get('non_partant') != 'NON_PARTANT'
         and row.get('top3_cotes_top3') == 'OUI' and row.get('top3_cotes_statut') == 'COMPLET'} == {'1', '2', '3'}
        for rows in odds_cohorts.values()
    )
    odds_metrics = [
        metric('Cotes PMU · Chevaux éligibles', eligible, 'Participations recensées hors non-partants, à partir du jour J.'),
        metric('Cotes PMU · Cotes collectées', collected, 'Chevaux éligibles avec cote valide et relevé antérieur au départ.'),
        metric('Cotes PMU · Cotes manquantes', eligible-collected, 'Chevaux éligibles sans cote valide horodatée.'),
        metric('Cotes PMU · Taux de couverture', collected/eligible if eligible else '', 'Cotes valides / chevaux éligibles.'),
        metric('Cotes PMU · Fraîcheur médiane (min)', round(median(ages), 1) if ages else '',
               'Âge du rapport PMU ou du relevé, mesuré au contrôle ou au départ si la course est passée.'),
        metric('Cotes PMU · Courses suivies', len(odds_cohorts), 'Courses du registre à partir du jour J.'),
        metric('Cotes PMU · Courses avec TOP3 complet', odds_complete, 'Trois rangs publiés et couverture de tous les chevaux éligibles.'),
        metric('Cotes PMU · Taux de TOP3 complets', odds_complete/len(odds_cohorts) if odds_cohorts else '',
               'Courses avec TOP3 Cotes complet / courses suivies.'),
    ]
    population_geny = participants
    if sheets_courses and any(CHAMP in row for row in sheets_courses):
        preuves = {(row.get('course_key'), str(row.get('numero'))): row for row in participants}
        population_geny = [{**preuves.get((row.get('course_key'), str(row.get('numero'))), {}), **row}
                           for row in sheets_courses if row.get('course_key') and row.get('numero') and row.get('cheval')]
    par_cheval = defaultdict(set)
    liens = defaultdict(set)

    def annee_ou_age(row):
        age = _nombre(row.get('age_ans'))
        year = str(row.get('date_course') or '')[:4]
        return ('naissance', int(year) - int(age)) if year.isdigit() and age is not None else ('âge', age)

    for row in population_geny:
        ident = row.get('_id_geny_correspondance')
        pmu_id = row.get('_id_pmu_correspondance')
        nom = nom_normalise(row.get('cheval'))
        if nom and (ident or pmu_id):
            liens[(nom, annee_ou_age(row))].add(('PMU', pmu_id) if pmu_id else ('Geny', ident))
    for row in population_geny:
        nom = nom_normalise(row.get('cheval'))
        if not nom:
            continue
        pmu_id, ident = row.get('_id_pmu_correspondance'), row.get('_id_geny_correspondance')
        age = annee_ou_age(row)
        possibles = liens[(nom, age)]
        cle = ('PMU', pmu_id) if pmu_id else ('Geny', ident) if ident else ('Nom et âge', nom, age)
        if len(possibles) == 1:
            cle = next(iter(possibles))
        par_cheval[cle].add(statut_ligne(row))
    correspondances = [
        metric(KPI_PREFIX + 'Chevaux distincts', len(par_cheval),
               'Périmètre de Courses & Prévisions. Identifiant PMU ou Geny, sinon nom normalisé et année de naissance estimée avec l’âge.'),
        *[metric(KPI_PREFIX + label, sum(statut in states and (statut == CONFIRMEE or CONFIRMEE not in states)
                                       for states in par_cheval.values()),
                 'Chevaux distincts concernés / chevaux distincts du registre. '
                 'Plusieurs états non confirmés sont possibles selon les engagements.')
          for statut, (label, _) in STATUTS.items()],
    ]
    return dict([
        *correspondances,
        metric('Historique courant · Participations contrôlées', len(history_rows),
               'Lignes cheval-course dans Courses & Prévisions.'),
        metric('Historique courant · Publications en attente',
               sum(r.get('historique_statut') == 'HISTO_PUBLICATION_EN_ATTENTE' for r in history_rows),
               'Captures validées dont la publication complète reste à confirmer dans Sheets.'),
        metric('Historique courant · Identités sans carrière',
               sum(r.get('historique_statut') == 'GENY_IDENTIFIE_CARRIERE_MANQUANTE' for r in history_rows),
               'Identités Geny confirmées sans données de carrière utilisables.'),
        *ml_metrics,
        *odds_metrics,
        *operational,
        metric('Chevaux distincts rencontrés',len({nom_normalise(r.get('cheval')) for r in participants if nom_normalise(r.get('cheval'))}),'Noms normalisés distincts ; identifiant stable à privilégier.'),
        metric('Courses distinctes collectées',len(courses_previsions),'Courses présentes dans Courses & Prévisions, préparations J+1 incluses.'),
        metric(PERIMETRE_RESULTATS, len(courses_previsions | courses_resultats),
               'Union des clés distinctes de Courses & Prévisions et Résultats & Analyse, préparations J+1 incluses.'),
        metric('Partants avec historique identifié (nom/ID)',linked,'Participations dont le statut commence par HISTO_OK.'),
        metric('Chevaux avec historique partiel',sum('PARTIEL' in str(r.get('historique_statut','')) for r in history_rows),'Participations avec statut partiel ; distinct du stock de fichiers partiels.'),
        metric('Partants avec historique disponible',has_history,'Nombre de performances strictement positif, valeur numérique contrôlée.'),
        metric('Partants sélectionnés TOP3 direct',sum(r.get('top3_direct_top3')=='OUI' for r in participants),'Participations sélectionnées ; préparations J+1 incluses.'),
        metric('Courses avec arrivée officielle',arrived,'Bilans avec arrivée PMU présente ; finalité officielle à contrôler séparément.'),
        metric('Courses avec arrivée vérifiée',verified,'Trois chevaux au podium et lecture horodatée après départ, non future.'),
        metric('Courses évaluées',len(scores),'TOP3 direct de trois chevaux uniques, horodaté avant départ, arrivée vérifiée.'),
        metric('Moyenne de chevaux TOP3 retrouvés',sum(scores)/len(scores) if scores else '','Moyenne du nombre retrouvé (0–3), uniquement TOP3 directs évaluables.'),
        metric('Taux de TOP3 exact (3 sur 3)',sum(s==3 for s in scores)/len(scores) if scores else '','Courses avec les trois chevaux retrouvés / courses directes évaluables.'),
        metric('Partants avec âge, sexe, gains et ferrure',sum(all(str(r.get(f) if r.get(f) is not None else '').strip() for f in ('age_ans','sexe','gains_euros','ferrure')) for r in participants),'Participations avec les quatre champs renseignés ; 0 est une valeur.'),
        metric('Taux critères essentiels renseignés',sum(all(str(r.get(f) if r.get(f) is not None else '').strip() for f in ('age_ans','sexe','gains_euros','ferrure')) for r in participants)/count if count else '','Participations avec quatre champs / participations recensées.'),
        metric('Avis PMU renseignés',nonempty('avis_pmu'),'Participations avec texte source PMU non vide.'),
        metric('Participations avec sélection ML publiée',sum(r.get('ml_top3')=='OUI' for r in participants),
               'Participations sélectionnées ML (OUI), distinctes des simples rangs et des expériences rétrospectives.'),
        metric('Participations avec modèle ML non entraîné',sum(r.get('ml_modele_statut')=='ML_NON_ENTRAINE' for r in participants),
               'Participations dont le statut ML est explicitement ML_NON_ENTRAINE ; même périmètre que les participations recensées.'),
        metric('Participations recensées',count,'Lignes de partants, distinctes des chevaux et des courses.'),
        metric('Partants sans historique collecté',sum(r.get('historique_statut')=='HISTO_NON_COLLECTE' for r in history_rows),'Participations explicitement sans historique collecté.'),
        metric('Taux de partants avec historique identifié',linked/len(history_rows) if history_rows else '','Participations HISTO_OK / participations recensées.'),
        metric('Courses avec sélection TOP3 direct',len({r['course_key'] for r in participants if r.get('top3_direct_top3')=='OUI'}),'Courses avec au moins une sélection directe ; préparations J+1 incluses.'),
        metric('Musique PMU renseignée',nonempty('musique_pmu'),'Lignes dont la musique PMU a ete recuperee; n atteste pas son interpretation.'),
        metric('TOP3 direct avec score calculable',sum(_nombre(r.get('top3_direct_score')) is not None for r in participants),
               'Participations avec score direct numerique y compris 0; inclut uniquement les courses deja calculees.'),
        metric('TOP3 direct avec historique contextuel',sum((_nombre(r.get('top3_direct_historiques_exploites')) or 0)>0 for r in participants),
               'Participations ayant utilise au moins une performance Geny anterieure et comparable.'),
        metric('TOP3 direct sur musique PMU seule',sum(r.get('top3_direct_source_forme')=='PMU_MUSIQUE_SEULE' for r in participants),
               'Score sans contexte historique exploitable, a ne pas confondre avec un resultat fiable.'),
        metric('Ferrure non récupérée (source explicite)',sum(not ferrure_sourcee(r) for r in participants),'Participations sans code de ferrure reconnu et documenté.'),
        metric('Taux ferrure renseignée',sum(bool(ferrure_sourcee(r)) for r in participants)/count if count else '','Participations avec code reconnu et documenté / participations recensées.'),
        *[metric('Lignes sans '+label,count-nonempty(field),'Participations sans valeur renseignée.') for label,field in [('âge','age_ans'),('sexe','sexe'),('gains','gains_euros')]],
    ])

def totaux_reference(metrics):
    """Références explicites, issues du même snapshot que les numérateurs."""
    def value(label):
        return metrics[label][0] if label in metrics else None
    participants=value('Participations recensées')
    courses=value('Courses distinctes collectées')
    evaluated=value('Courses évaluées')
    totals={label: value(KPI_PREFIX + 'Chevaux distincts')
            for label in metrics if label.startswith(KPI_PREFIX) and label != KPI_PREFIX + 'Chevaux distincts'}
    for suffix in ('Cotes collectées', 'Cotes manquantes', 'Taux de couverture'):
        if 'Cotes PMU · Chevaux éligibles' in metrics:
            totals['Cotes PMU · '+suffix] = value('Cotes PMU · Chevaux éligibles')
    for suffix in ('Courses avec TOP3 complet', 'Taux de TOP3 complets'):
        if 'Cotes PMU · Courses suivies' in metrics:
            totals['Cotes PMU · '+suffix] = value('Cotes PMU · Courses suivies')
    for label in (
        'Chevaux distincts rencontrés','Partants avec historique identifié (nom/ID)',
        'Chevaux avec historique partiel','Partants avec historique disponible',
        'Partants sélectionnés TOP3 direct','Partants avec âge, sexe, gains et ferrure',
        'Taux critères essentiels renseignés','Avis PMU renseignés','Participations recensées',
        'Partants sans historique collecté','Taux de partants avec historique identifié',
        'Ferrure non récupérée (source explicite)','Taux ferrure renseignée',
        'Lignes sans âge','Lignes sans sexe','Lignes sans gains','Musique PMU renseignée',
        'TOP3 direct avec score calculable','TOP3 direct avec historique contextuel',
        'TOP3 direct sur musique PMU seule','Participations avec sélection ML publiée',
        'Participations avec modèle ML non entraîné'):
        if participants is not None:totals[label]=participants
    history_total = value('Historique courant · Participations contrôlées')
    if history_total is not None:
        for label in ('Partants avec historique identifié (nom/ID)', 'Chevaux avec historique partiel',
                      'Partants avec historique disponible', 'Partants sans historique collecté',
                      'Taux de partants avec historique identifié', 'Historique courant · Publications en attente',
                      'Historique courant · Identités sans carrière'):
            totals[label] = history_total
    for label in ('Courses distinctes collectées', 'Courses avec sélection TOP3 direct'):
        if courses is not None:totals[label]=courses
    if (perimetre := value(PERIMETRE_RESULTATS)) is not None:
        totals.update(dict.fromkeys(INDICATEURS_RESULTATS, perimetre))
    if evaluated is not None:
        totals['Taux de TOP3 exact (3 sur 3)']=evaluated
        totals['Moyenne de chevaux TOP3 retrouvés']=3
    from .echeances_production import PHASES
    for phase in PHASES:
        phase = f'H-{phase[1:]}'
        opened=value('Échéances · '+phase+' ouvertes')
        if opened is not None:
            totals['Échéances · '+phase+' publiées à temps']=opened
            totals['Échéances · '+phase+' dépassées sans preuve à temps']=opened
    qualifying=value('Maturité ML · Observations qualifiantes')
    if qualifying is not None:
        totals.update({label: qualifying for label in metrics if label.startswith(
            ('Maturité ML · Couverture · ', 'Maturité ML · Taux de complétude')) and not label.endswith('prospective')})
    for prefix in ('J · ', 'J+1 · '):
        total = value(prefix + 'Partants confirmés')
        if total is not None:
            totals.update({label: total for label in metrics if label.startswith(prefix)})
            auto = value(prefix + 'Partants en départ autostart documenté')
            if auto is not None:
                totals[prefix + 'Positions autostart renseignées'] = auto
                totals[prefix + 'Lignes autostart renseignées'] = auto
    for cohort in ('initiale', 'extensions', 'lot de 96'):
        prefix = f'Rattrapage · {cohort} · '
        total = value(prefix + 'cibles')
        if total is not None:
            totals.update({label: total for label in metrics if label.startswith(prefix) and not label.endswith(' · checkpoint')})
    prospective_maturity=value('Maturité ML · Courses prospectives appariées')
    if prospective_maturity is not None:
        totals.update({label: prospective_maturity for label in metrics if label.startswith(
            ('Maturité ML · Taux de 3 sur 3', 'Maturité ML · Taux d’au moins 2 sur 3'))})
    direct = value('Autostart prospectif · Courses direct évaluables')
    paired = value('Autostart prospectif · Courses appariées')
    if direct is not None:
        totals['Autostart prospectif · Courses appariées'] = direct
    if paired is not None:
        totals['Autostart prospectif · Courses avec 3 sur 3'] = paired
        totals['Autostart prospectif · Courses avec au moins 2 sur 3'] = paired
    prospective=value('ML prospectif · Courses évaluées')
    if prospective is not None:totals['ML prospectif · TOP3 ML exacts']=prospective
    return totals


PUBLISHED_PREFIXES = ('ML expérimental · ', 'ML prospectif · ', 'Maturité ML · ', 'Autostart prospectif · ',
                      'Échéances · ', 'H+30 · ', 'Collecte · ', 'Cotes PMU · ', 'Registre · ', 'J · ', 'J+1 · ', 'Rattrapage · ', 'Historique courant · ', KPI_PREFIX)


def plan_kpi(values, metrics):
    """Actualise valeur, définition et référence connue ensemble ; préserve les autres formules."""
    updates=[]
    totals=totaux_reference(metrics)
    def dimension(label):
        return next((name for prefix, name in DIMENSIONS_KPI.items() if label.startswith(prefix)), None)

    for number,row in enumerate(values[1:],start=2):
        if len(row)>1 and row[1] in ('Avis Equidia renseignés','Avis ZEturf renseignés'):
            updates.append({'range':f"'{KPI_TAB}'!A{number}:E{number}",'values':[['','','','','']]})
            continue
        if not any(str(value or '').strip() for value in row[:4]) and len(row)>4 and row[4]!='':
            updates.append({'range':f"'{KPI_TAB}'!E{number}",'values':[['']]})
            continue
        if len(row)>1 and (label := cle_indicateur(row[1])) in metrics:
            value,definition=metrics[label]
            visible = afficher_indicateur(label)
            desired=[value,definition]+([totals[label]] if label in totals else [])
            end='E' if label in totals else 'D'
            categorie = dimension(label)
            if visible != row[1] or (categorie and row[0] != categorie):
                updates.append({'range': f"'{KPI_TAB}'!A{number}:{end}{number}",
                                'values': [[categorie or row[0], visible, *desired]]})
            elif row[2:2+len(desired)]!=desired:
                updates.append({'range':f"'{KPI_TAB}'!C{number}:{end}{number}",'values':[desired]})
    present={cle_indicateur(row[1]) for row in values[1:] if len(row)>1}
    last=max((i for i,row in enumerate(values,start=1) if any(str(v or '').strip() for v in row)),default=1)
    for label,(value,definition) in metrics.items():
        if label.startswith(PUBLISHED_PREFIXES) and label not in present:
            last+=1
            desired=[dimension(label) or 'ML',afficher_indicateur(label),value,definition]+([totals[label]] if label in totals else [])
            end='E' if label in totals else 'D'
            updates.append({'range':f"'{KPI_TAB}'!A{last}:{end}{last}",'values':[desired]})
    return updates
