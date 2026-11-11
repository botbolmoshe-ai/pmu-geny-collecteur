"""V22: deux TOP3 independants de Geny, de l'historique et du modele ML.
Analyse directe = musique/forme visible sur fiche PMU actuelle uniquement.
Marche = cotes PMU horodatees uniquement. Jamais de resultats futurs.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path
from .ml_v19 import load, save, numeric
from .auto_v18 import _list, _num

def _musique(value):
    if isinstance(value,dict):
        value=value.get('musique') or value.get('libelle') or ''
    if not isinstance(value,str):return []
    # PMU: 1a 2a Da 4m / 1-2-3 etc. 0 et lettres de disqualification = 0 point.
    tokens=re.findall(r'(?<![a-zA-Z])(?:[1-9]|0|D|d)(?:[amAM])?(?![a-zA-Z])',value)
    return tokens[:5]

def _form_score(participant):
    value=next((participant[k] for k in ('musique','musiqueCheval','derniereMusique')
                if participant.get(k)),None)
    series=_musique(value)
    if not series:return None
    points={1:5.0,2:3.5,3:2.5,4:1.5,5:1.0}
    ranks=[int(t[0]) if t[0].isdigit() else 0 for t in series]
    return round(sum(points.get(r,0.0)*(1-0.12*i) for i,r in enumerate(ranks)),3)

def calculer(cache,course,raw,now=None):
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if now.tzinfo is None or depart.tzinfo is None:raise ValueError('Fuseau obligatoire')
    if now>=depart:return {'direct':'APRES_DEPART','cotes':'APRES_DEPART'}
    participants=_list(raw,'participants','partants')
    if not participants:return {'direct':'PARTANTS_ABSENTS','cotes':'PARTANTS_ABSENTS'}
    base=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}"
    _,expected= set(),course.get('nombre_declares')
    all_numbers=set()
    eligible=[];direct=[];market=[]
    for item in participants:
        if not isinstance(item,dict):continue
        n=_num(item,'numPmu','num','numero','numeroPmu')
        if n is None or n in all_numbers:continue
        all_numbers.add(n)
        if item.get('nonPartant') is True or str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):
            continue
        eligible.append(n)
        label=next((str(item.get(k,'')) for k in ('nomCheval','nom','nomParticipant') if item.get(k)),'')
        score=_form_score(item)
        if score is not None:direct.append({'numero':n,'nom':label,'score_direct':score})
        cote=None
        for field in ('rapportDirect','coteDirect','cote','rapportProbable'):
            raw_cote=item.get(field)
            if isinstance(raw_cote,dict):raw_cote=raw_cote.get('rapport') or raw_cote.get('valeur')
            x=numeric(raw_cote)
            if x is not None and x>0:cote=x;break
        if cote is not None:market.append({'numero':n,'nom':label,'cote':cote})
    output={}
    for mode,ranking,key,reverse in [('direct',direct,'score_direct',True),('cotes',market,'cote',False)]:
        if len(eligible)<3 or len(ranking)<3:
            output[mode]='DONNEES_INSUFFISANTES'
            continue
        ranking.sort(key=lambda x:((-x[key] if reverse else x[key]),x['numero']))
        doc={'date':course['date'],'course':course['code'],'depart':course['depart'],
             'calcul_utc':now.isoformat(),'mode':mode.upper(),
             'statut':'COMPLET' if len(ranking)==len(eligible) else 'PARTIEL',
             'observations':len(ranking),'partants_eligibles':len(eligible),
             'classement_complet':ranking,'top3':ranking[:3],
             'note':'Classement exploratoire, pas une probabilite. Sources PMU du jour.'}
        filename=Path(str(base)+f'_{mode}.json')
        # Conserver le premier classement si une nouvelle collecte perd des informations.
        # En avant-course, actualiser seulement avec des observations au moins aussi completes.
        old=load(filename,{}) or {}
        if old.get('observations',0)>doc['observations']:
            output[mode]='ANCIEN_RELEVE_PLUS_COMPLET'
            continue
        doc['premier_calcul_utc']=old.get('premier_calcul_utc',doc['calcul_utc'])
        save(filename,doc)
        output[mode]='CALCULE_'+doc['statut']
    return output
