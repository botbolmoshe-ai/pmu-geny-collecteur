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
    return dict([
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
        *[metric('Avis '+label+' renseignés',nonempty(field),'Participations avec texte source non vide.') for label,field in [('PMU','avis_pmu'),('Equidia','avis_equidia'),('ZEturf','avis_zeturf')]],
        metric('Participations recensées',count,'Lignes de partants, distinctes des chevaux et des courses.'),
        metric('Partants sans historique collecté',sum(r.get('historique_statut')=='HISTO_NON_COLLECTE' for r in participants),'Participations explicitement sans historique collecté.'),
        metric('Taux de partants avec historique identifié',linked/count if count else '','Participations HISTO_OK / participations recensées.'),
        metric('Courses avec sélection TOP3 direct',len({r['course_key'] for r in participants if r.get('top3_direct_top3')=='OUI'}),'Courses avec au moins une sélection directe ; préparations J+1 incluses.'),
        metric('Ferrure non récupérée (source explicite)',count-nonempty('ferrure'),'Participations sans valeur de ferrure renseignée.'),
        metric('Taux ferrure renseignée',nonempty('ferrure')/count if count else '','Participations avec ferrure / participations recensées.'),
        *[metric('Lignes sans '+label,count-nonempty(field),'Participations sans valeur renseignée.') for label,field in [('âge','age_ans'),('sexe','sexe'),('gains','gains_euros')]],
    ])

def plan_kpi(values, metrics):
    """Ne modifie que valeur/definition des indicateurs deja presents dans l'onglet."""
    updates=[]
    for number,row in enumerate(values[1:],start=2):
        if len(row)>1 and row[1] in metrics:
            value,definition=metrics[row[1]]
            if len(row)<4 or row[2]!=value or row[3]!=definition:
                updates.append({'range':f"'{KPI_TAB}'!C{number}:D{number}",'values':[[value,definition]]})
    return updates
