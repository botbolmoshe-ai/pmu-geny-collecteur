"""Quality by race date versus genuine dated observations: distinct populations."""
from collections import OrderedDict
from datetime import date,datetime,timezone
from statistics import median
from .dates import PARIS
from .logic import number, selected,timestamp

VALUE='Valeur (automatique)'
TOTAL='Total de référence (automatique)'
OBSERVED='Date du relevé'
FERRURES={'F','D4','DA','DP','P4','PA','PP','DP/PA','DA/PP'}


def day(value):
    try:return date.fromisoformat(str(value))
    except (ValueError,TypeError):return None


def date_rows(rows,field,start,end):
    if start>end:raise ValueError('Période inversée')
    return [r for r in rows if day(r.get(field)) and start<=day(r[field])<=end]


def cohort_metrics(courses,start,end,now=None):
    rows=date_rows(courses,'Date',start,end)
    active=[r for r in rows if r.get('Non-partant (NP)')=='PARTANT']
    n=len(active);groups=OrderedDict()
    for r in rows:
        key=r.get('Clé course (technique)')
        if key:groups.setdefault(key,[]).append(r)
    result=[]
    def add(d,label,value,total,definition):
        result.append({'Dimension':d,'Indicateur':label,VALUE:value,TOTAL:total,'Définition / réserve':definition})
    add('Couverture','Participations recensées',len(rows),len(rows),'Lignes des courses de la période, non-partants inclus.')
    add('Couverture','Partants confirmés',n,len(rows),'Statut PARTANT explicitement renseigné.')
    add('Couverture','Statuts de participation à confirmer',sum(r.get('Non-partant (NP)') not in ('PARTANT','NON_PARTANT') for r in rows),len(rows),'Ni PARTANT ni NON_PARTANT explicitement renseigné.')
    add('Couverture','Courses recensées',len(groups),len(groups),'Clés de course distinctes de la période.')
    available=sum((number(r.get('Historique · Nb performances récupérées')) or 0)>0 for r in active)
    add('Historique','Partants avec historique disponible',available,n,'Partants confirmés avec au moins une performance disponible aujourd’hui.')
    add('Historique','Taux de partants avec historique disponible',available/n if n else '',n,'Couverture actuelle des partants confirmés de la période ; pas une observation passée.')
    identified = sum(str(r.get('Historique · État', '')).startswith(('HISTO_OK', 'HISTO_PARTIEL')) for r in active)
    partial = sum(str(r.get('Historique · État', '')).startswith('HISTO_PARTIEL') for r in active)
    complete = sum(str(r.get('Historique · État', '')).startswith('HISTO_OK') for r in active)
    add('Historique','Partants avec historique identifié',identified,n,'Association au cheval reconnue dans le registre.')
    add('Historique','Partants avec historique partiel',partial,n,'Historique Geny explicitement partiel.')
    add('Historique','Partants avec historique complet',complete,n,'Historique Geny lié avec un statut HISTO_OK.')
    def ferrure(row):
        code = str(row.get('Ferrure · Course du jour') or row.get('Ferrure') or '').strip().upper()
        status = row.get('PMU · État ferrure') or row.get('PMU · Complétude fiche')
        if status in ('CODE_INCONNU', 'NON_RECUPEREE', 'FERRURE_NON_RECUPEREE'):
            return ''
        if code == 'F' and status not in ('CODE_RECONNU', 'CONVENTION_PMU',
                                          'FERRURE_DISPONIBLE_SOURCEE', 'PMU_FERRURE_DISPONIBLE'):
            return ''
        return code if code in FERRURES else ''
    shoes=sum(bool(ferrure(r)) for r in active)
    add('Qualité','Partants avec ferrure inconnue',n-shoes,n,'Ferrure absente ou code inconnu dans le registre.')
    add('Qualité','Partants ferrés (F)',sum(ferrure(r) == 'F' for r in active),n,
        'Code F issu du profil participant ou de la convention PMU documentée.')
    add('Qualité','Partants avec ferrure reconnue',shoes,n,'Code de ferrure reconnu ; ne prouve pas à lui seul une provenance historique complète.')
    add('Qualité','Taux de ferrure reconnue',shoes/n if n else '',n,'Partants confirmés avec code reconnu / partants confirmés de la période.')
    essentials=sum(number(r.get('Âge (ans)')) is not None and bool(r.get('Sexe'))
                   and number(r.get('Gains carrière (€)')) is not None
                   and bool(ferrure(r)) for r in active)
    add('Qualité','Partants avec critères essentiels renseignés',essentials,n,'Âge, sexe, gains (zéro accepté) et ferrure reconnue.')
    add('Qualité','Taux de critères essentiels renseignés',essentials/n if n else '',n,'Complétude actuelle des quatre critères sur les partants confirmés.')
    for method,title in [('direct','direct'),('ml','ML')]:
        add('Prévisions','Courses avec TOP3 '+title+' complet',sum(bool(selected(r,method)) for r in groups.values()),len(groups),
            'Sélection stockée de trois numéros distincts avec rangs 1/2/3, tous partants confirmés ; ne certifie pas sa publication passée.')
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(PARIS).date()
    eligible = collected = 0
    ages = []
    complete = followed = 0
    for group in groups.values():
        depart = timestamp(group[0].get('Départ (Paris)'))
        if not depart or depart.astimezone(PARIS).date() > today:
            continue
        followed += 1
        picked = selected(group, 'cotes')
        complete += bool(picked and picked[0].get('Cotes · État') == 'COMPLET')
        for row in group:
            if row.get('Non-partant (NP)') == 'NON_PARTANT':
                continue
            eligible += 1
            observed = timestamp(row.get('Cotes · Relevé UTC'))
            if (number(row.get('Cotes · Valeur')) or 0) <= 0 or not observed or not observed < depart or observed > now:
                continue
            collected += 1
            reported = timestamp(row.get('Cotes · Rapport PMU UTC')) or observed
            reported = min(reported, observed)
            ages.append((min(now, depart) - reported).total_seconds() / 60)
    add('Cotes PMU','Chevaux éligibles',eligible,eligible,'Participations recensées hors non-partants, à partir du jour J.')
    add('Cotes PMU','Cotes collectées',collected,eligible,'Cotes valides relevées avant le départ.')
    add('Cotes PMU','Cotes manquantes',eligible-collected,eligible,'Chevaux éligibles sans cote valide horodatée.')
    add('Cotes PMU','Taux de couverture',collected/eligible if eligible else '',eligible,'Cotes valides / chevaux éligibles.')
    add('Cotes PMU','Fraîcheur médiane (min)',round(median(ages), 1) if ages else '', '',
        'Âge du rapport PMU ou du relevé au contrôle ou au départ si la course est passée.')
    add('Cotes PMU','Taux de TOP3 complets',complete/followed if followed else '',followed,
        'TOP3 publié couvrant tous les chevaux éligibles / courses suivies.')
    return result


def daily_series(courses,start,end):
    days=sorted({day(r.get('Date')) for r in date_rows(courses,'Date',start,end)})
    return [{**m,'Date':d.isoformat()} for d in days for m in cohort_metrics(courses,d,d)]


def history_series(history,start,end,as_of=None):
    rows=date_rows(history,OBSERVED,start,end)
    as_of=as_of or datetime.now(timezone.utc)
    seen=set()
    for r in rows:
        captured=timestamp(r.get('Relevé UTC'))
        if (not captured or captured>as_of or captured.astimezone(PARIS).date()!=day(r[OBSERVED])
                or not str(r.get('Indicateur') or '').strip()):
            raise ValueError('Horodatage ou indicateur du relevé invalide')
        key=(r[OBSERVED],r.get('Indicateur'))
        if key in seen:raise ValueError('Plusieurs relevés pour un indicateur et une date')
        seen.add(key)
    return [{**r,'Date':r[OBSERVED]} for r in rows]


def latest_history(rows):
    if not rows:return [],None
    latest=max(r['Date'] for r in rows)
    return [r for r in rows if r['Date']==latest],latest
