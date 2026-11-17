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
    performance=_load(cache/'ml/performance_prospective.json')
    operational=[]
    for label,field,definition in (
        ('Courses évaluées','courses','Courses communes direct/ML avec certificat de publication antérieur au départ et arrivée PMU vérifiée.'),
        ('Moyenne ML sur 3','moyenne_ml','Moyenne prospective ; vide si aucune course admissible.'),
        ('Moyenne direct comparable sur 3','moyenne_direct','Même ensemble de courses que le ML prospectif.'),
        ('Écart ML contre direct','ecart_ml_direct','Écart moyen sur courses appariées ; aucune garantie de gain futur.'),
        ('TOP3 ML exacts','exact_3_sur_3_ml','Nombre de courses avec trois chevaux retrouvés, sur le dénominateur Courses évaluées.')):
        operational.append(metric('ML prospectif · '+label,performance.get(field) if performance.get(field) is not None else '',definition))
    from .echeances_production import courses_du_jour, PHASES, MARGE, instant
    day,courses=courses_du_jour(cache,now)
    for phase,offset in PHASES.items():
        expected=ontime=missed=0
        for c in courses:
            depart=instant(c.get('depart'))
            if not depart or now<depart-offset-MARGE:continue
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

def plan_kpi(values, metrics):
    """Ne modifie que valeur/definition des indicateurs deja presents dans l'onglet."""
    updates=[]
    for number,row in enumerate(values[1:],start=2):
        if len(row)>1 and row[1] in ('Avis Equidia renseignés','Avis ZEturf renseignés'):
            updates.append({'range':f"'{KPI_TAB}'!A{number}:E{number}",'values':[['','','','','']]})
            continue
        if not any(str(value or '').strip() for value in row[:4]) and len(row)>4 and row[4]!='':
            updates.append({'range':f"'{KPI_TAB}'!E{number}",'values':[['']]})
            continue
        if len(row)>1 and row[1] in metrics:
            value,definition=metrics[row[1]]
            if len(row)<4 or row[2]!=value or row[3]!=definition:
                updates.append({'range':f"'{KPI_TAB}'!C{number}:D{number}",'values':[[value,definition]]})
    present={row[1] for row in values[1:] if len(row)>1}
    last=max((i for i,row in enumerate(values,start=1) if any(str(v or '').strip() for v in row)),default=1)
    for label,(value,definition) in metrics.items():
        if label.startswith(('ML expérimental · ','ML prospectif · ','Échéances · ','Collecte · ')) and label not in present:
            last+=1
            updates.append({'range':f"'{KPI_TAB}'!A{last}:D{last}",
                            'values':[['ML',label,value,definition]]})
    return updates
