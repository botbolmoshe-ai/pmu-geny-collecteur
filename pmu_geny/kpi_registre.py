"""KPI du registre calcules depuis les sources, sans formules dependantes des lignes."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math

KPI_TAB = 'Data Quality & KPI'

def _load(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def _nombre(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None

def calculer_kpi(cache, source=None, now=None):
    from .sync_google_sheets import source_rows, limiter_cours_registre
    from .liaison_chevaux_v22 import nom_normalise
    cache=Path(cache);now=now or datetime.now(timezone.utc)
    source=source if source is not None else limiter_cours_registre(source_rows(cache))
    participants=list(source['Courses & Prévisions'].values())
    reports=list(source['Résultats & Analyse'].values())
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
            if not departure<checked<=now:continue
            podium={int(h['numero']) for h in result['arrivee'] if h['rang'] in (1,2,3)}
            if len(podium)!=3:continue
            verified+=1
            predicted=[int(h['numero']) for h in forecast.get('top3',[])]
            created=datetime.fromisoformat(forecast['calcul_utc'])
            if len(predicted)==len(set(predicted))==3 and created<departure:
                scores.append(len(set(predicted)&podium))
        except (ValueError,KeyError,TypeError):continue
    linked=sum(str(r.get('historique_statut','')).startswith('HISTO_OK') for r in participants)
    has_history=sum((_nombre(r.get('historique_nb_courses_datees')) or 0)>0 for r in participants)
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
        quality = maturity['couverture']
        prospective = maturity.get('prospective', {})
        comparison = prospective.get('comparaison') or {}
        interval = comparison.get('ic95_bootstrap_par_course', ['', ''])
        fields = [
            ('Statut candidat', maturity['maturite'], maturity['etat']),
            ('Version candidate', maturity.get('version', ''), 'SHA-256 du modèle figé pour l’évaluation.'),
            ('Version en service', maturity.get('version_en_service', ''), maturity.get('maturite_en_service', 'Aucun modèle promu.')),
            ('Courses admissibles', maturity['courses'], 'Captures pré-départ appariées à une arrivée admissible.'),
            ('Observations admissibles', maturity['lignes'], 'Une observation par cheval et par course capturée.'),
            ('Courses qualifiantes', maturity['courses_qualifiantes'], 'Courses du schéma courant avec capture et arrivée sourcées.'),
            ('Observations qualifiantes', maturity['observations_qualifiantes'], 'Observations du schéma courant sur les courses qualifiantes.'),
            ('Taux de complétude', quality['completude'], 'Part des observations qualifiantes avec forme PMU, distance, discipline, âge, sexe et gains.'),
            ('Courses prospectives appariées', prospective.get('courses', 0), 'Même relevé PMU et preuve de publication du TOP3 direct avant départ.'),
            ('Taux de complétude prospective', prospective.get('completude', ''), 'Six critères essentiels sur les prévisions de la cohorte prospective.'),
            ('Moyenne prospective ML', prospective.get('moyenne_ml'), 'Nombre moyen de chevaux du podium retrouvés sur trois.'),
            ('Moyenne prospective direct', prospective.get('moyenne_direct'), 'Nombre moyen sur les mêmes courses et au même instant de relevé.'),
            ('Écart prospectif ML − direct', comparison.get('ecart_moyen'), 'Écart moyen de chevaux trouvés par course appariée.'),
            ('Borne basse IC 95 %', interval[0], 'Bootstrap apparié par course, différence ML − direct.'),
            ('Borne haute IC 95 %', interval[1], 'Bootstrap apparié par course, différence ML − direct.'),
        ]
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
    for label,field,definition in (
        ('Courses évaluées','courses','Courses communes direct/ML avec certificat de publication antérieur au départ et arrivée PMU vérifiée.'),
        ('Moyenne ML sur 3','moyenne_ml','Moyenne prospective ; vide si aucune course admissible.'),
        ('Moyenne direct comparable sur 3','moyenne_direct','Même ensemble de courses que le ML prospectif.'),
        ('Écart ML contre direct','ecart_ml_direct','Écart moyen sur courses appariées ; aucune garantie de gain futur.'),
        ('TOP3 ML exacts','exact_3_sur_3_ml','Nombre de courses avec trois chevaux retrouvés, sur le dénominateur Courses évaluées.')):
        operational.append(metric('ML prospectif · '+label,performance.get(field) if performance.get(field) is not None else '',definition))
    from .echeances_production import courses_du_jour, PHASES, ANTICIPATION, instant
    day,courses=courses_du_jour(cache,now)
    for phase,offset in PHASES.items():
        expected=ontime=missed=0
        for c in courses:
            depart=instant(c.get('depart'))
            if not depart or now<depart-offset-ANTICIPATION:continue
            expected+=1
            proof=_load(cache/'jalons'/f"{day}_{c['code']}.json").get(phase,{})
            ok=proof.get('statut')=='PUBLIE_A_TEMPS'
            ontime+=int(ok)
            missed+=int(now>depart-offset and not ok)
        operational.extend([
            metric('Échéances · '+phase+' ouvertes',expected,'Fenêtres de préparation ouvertes aujourd’hui, courses passées incluses.'),
            metric('Échéances · '+phase+' publiées à temps',ontime,'Deux TOP3 certifiés après publication Sheets dans les délais.'),
            metric('Échéances · '+phase+' dépassées sans preuve à temps',missed,'Échéances déjà dépassées sans certificat à temps ; aucun rattrapage rétroactif.')])
    queue=_load(cache/'collecte_incrementale/etat.json')
    for label,field in [('Captures complètes','captures_validees'),('Captures partielles','captures_partielles'),('Rejets','collectes_rejetees')]:
        operational.append(metric('Collecte · '+label+' dernier passage',queue.get('bilan',{}).get(field,''),
                                  'Compteur du passage horodaté '+str(queue.get('passage_utc','non disponible'))))
    return dict([
        *ml_metrics,
        *operational,
        metric('Chevaux distincts rencontrés',len({nom_normalise(r.get('cheval')) for r in participants if nom_normalise(r.get('cheval'))}),'Noms normalisés distincts ; identifiant stable à privilégier.'),
        metric('Courses distinctes collectées',len({r['course_key'] for r in participants}),'Courses présentes, préparations J+1 incluses.'),
        metric('Partants avec historique identifié (nom/ID)',linked,'Participations dont le statut commence par HISTO_OK.'),
        metric('Chevaux avec historique partiel',sum('PARTIEL' in str(r.get('historique_statut','')) for r in participants),'Participations avec statut partiel ; distinct du stock de fichiers partiels.'),
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
        metric('Partants sans historique collecté',sum(r.get('historique_statut')=='HISTO_NON_COLLECTE' for r in participants),'Participations explicitement sans historique collecté.'),
        metric('Taux de partants avec historique identifié',linked/count if count else '','Participations HISTO_OK / participations recensées.'),
        metric('Courses avec sélection TOP3 direct',len({r['course_key'] for r in participants if r.get('top3_direct_top3')=='OUI'}),'Courses avec au moins une sélection directe ; préparations J+1 incluses.'),
        metric('Musique PMU renseignée',nonempty('musique_pmu'),'Lignes dont la musique PMU a ete recuperee; n atteste pas son interpretation.'),
        metric('TOP3 direct avec score calculable',sum(_nombre(r.get('top3_direct_score')) is not None for r in participants),
               'Participations avec score direct numerique y compris 0; inclut uniquement les courses deja calculees.'),
        metric('TOP3 direct avec historique contextuel',sum((_nombre(r.get('top3_direct_historiques_exploites')) or 0)>0 for r in participants),
               'Participations ayant utilise au moins une performance Geny anterieure et comparable.'),
        metric('TOP3 direct sur musique PMU seule',sum(r.get('top3_direct_source_forme')=='PMU_MUSIQUE_SEULE' for r in participants),
               'Score sans contexte historique exploitable, a ne pas confondre avec un resultat fiable.'),
        metric('Ferrure non récupérée (source explicite)',count-nonempty('ferrure'),'Participations sans valeur de ferrure renseignée.'),
        metric('Taux ferrure renseignée',nonempty('ferrure')/count if count else '','Participations avec ferrure / participations recensées.'),
        *[metric('Lignes sans '+label,count-nonempty(field),'Participations sans valeur renseignée.') for label,field in [('âge','age_ans'),('sexe','sexe'),('gains','gains_euros')]],
    ])

def totaux_reference(metrics):
    """Références explicites, issues du même snapshot que les numérateurs."""
    def value(label):
        return metrics[label][0] if label in metrics else None
    participants=value('Participations recensées')
    courses=value('Courses distinctes collectées')
    evaluated=value('Courses évaluées')
    totals={}
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
    for label in ('Courses distinctes collectées','Courses avec arrivée officielle',
                  'Courses avec arrivée vérifiée','Courses évaluées','Courses avec sélection TOP3 direct'):
        if courses is not None:totals[label]=courses
    if evaluated is not None:
        totals['Taux de TOP3 exact (3 sur 3)']=evaluated
        totals['Moyenne de chevaux TOP3 retrouvés']=3
    for phase in ('H2','H1'):
        opened=value('Échéances · '+phase+' ouvertes')
        if opened is not None:
            totals['Échéances · '+phase+' publiées à temps']=opened
            totals['Échéances · '+phase+' dépassées sans preuve à temps']=opened
    qualifying=value('Maturité ML · Observations qualifiantes')
    if qualifying is not None:
        totals.update({label: qualifying for label in metrics if label.startswith(
            ('Maturité ML · Couverture · ', 'Maturité ML · Taux de complétude')) and not label.endswith('prospective')})
    prospective=value('ML prospectif · Courses évaluées')
    if prospective is not None:totals['ML prospectif · TOP3 ML exacts']=prospective
    return totals


def plan_kpi(values, metrics):
    """Actualise valeur, définition et référence connue ensemble ; préserve les autres formules."""
    updates=[]
    totals=totaux_reference(metrics)
    for number,row in enumerate(values[1:],start=2):
        if len(row)>1 and row[1] in ('Avis Equidia renseignés','Avis ZEturf renseignés'):
            updates.append({'range':f"'{KPI_TAB}'!A{number}:E{number}",'values':[['','','','','']]})
            continue
        if not any(str(value or '').strip() for value in row[:4]) and len(row)>4 and row[4]!='':
            updates.append({'range':f"'{KPI_TAB}'!E{number}",'values':[['']]})
            continue
        if len(row)>1 and row[1] in metrics:
            value,definition=metrics[row[1]]
            label=row[1]
            desired=[value,definition]+([totals[label]] if label in totals else [])
            if row[2:2+len(desired)]!=desired:
                end='E' if label in totals else 'D'
                updates.append({'range':f"'{KPI_TAB}'!C{number}:{end}{number}",'values':[desired]})
    present={row[1] for row in values[1:] if len(row)>1}
    last=max((i for i,row in enumerate(values,start=1) if any(str(v or '').strip() for v in row)),default=1)
    for label,(value,definition) in metrics.items():
        if label.startswith(('ML expérimental · ','ML prospectif · ','Maturité ML · ','Échéances · ','Collecte · ')) and label not in present:
            last+=1
            desired=['ML',label,value,definition]+([totals[label]] if label in totals else [])
            end='E' if label in totals else 'D'
            updates.append({'range':f"'{KPI_TAB}'!A{last}:{end}{last}",'values':[desired]})
    return updates
