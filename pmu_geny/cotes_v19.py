"""Relevé informatif des cotes PMU; hors features prédictives.
Une valeur enregistrée est un instantané, PAS une cote définitive garantie.
"""
from datetime import datetime,timezone
from pathlib import Path
from math import isfinite
from .ml_v19 import load, save, numeric

KEYS=('dernierRapportDirect','rapportDirect','coteDirect','cote','rapportProbable')

def extraire_cote(participant):
    """Rapport probable simple gagnant direct; aucune estimation inventee."""
    for key in KEYS:
        value=participant.get(key)
        if isinstance(value,dict):
            if (value.get('indisponible') is True
                    or value.get('typePari') not in (None, 'SIMPLE_GAGNANT')
                    or value.get('typeRapport') not in (None, 'DIRECT')):
                continue
            value=value.get('rapport',value.get('valeur'))
        if isinstance(value,bool):
            continue
        if isinstance(value,str):
            value=value.strip().replace(',','.')
        x=numeric(value)
        if x is not None and isfinite(x) and x>0:
            return x,key
    return None,None

def collecter(cache,course,participants,now=None):
    from .auto_v18 import _list,_num
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if now>=depart:return 'APRES_DEPART_SANS_RELEVE'
    raw=_list(participants,'participants','partants')
    if not raw:return 'COTES_INDISPONIBLES'
    data=[]
    for p in raw:
        if not isinstance(p,dict):continue
        n=_num(p,'numPmu','num','numero','numeroPmu')
        if (n is None or p.get('nonPartant') is True
                or str(p.get('statut', '')).upper() in ('NP', 'NON_PARTANT')):
            continue
        cote,champ=extraire_cote(p)
        data.append({'numero':n,'cote':cote,'source':'PMU_API_PARTICIPANTS' if cote else '',
                     'champ_pmu':champ or '', 'heure_utc':now.isoformat(),
                     'statut':'RELEVE_HORODATE' if cote else 'NON_DISPONIBLE'})
    if not data:return 'COTES_INDISPONIBLES'
    dest=Path(cache)/'cotes'/f"{course['date']}_{course['code']}.json"
    old=load(dest,{}) or {}
    history=old.get('releves',[])
    if history and history[-1].get('heure_utc') == now.isoformat() and history[-1].get('chevaux') == data:
        return old.get('statut','COTES_INDISPONIBLES')
    history.append({'heure_utc':now.isoformat(),'chevaux':data})
    # Conserver l'ensemble des relevés pour audit. Dernier observé avant le départ.
    count=sum(item['cote'] is not None for item in data)
    save(dest,{'date':course['date'],'course':course['code'],'depart':course['depart'],
         'chevaux':data,'releves':history,'cotes_extraites':count,
         'statut':'COTES_RELEVEES' if count>=3 else 'COTES_NON_EXTRAITES' if count==0 else 'COTES_PARTIELLES',
         'note':'Instantane PMU; absence de cote ne prouve pas indisponibilite chez PMU.'})
    return 'COTES_RELEVEES' if count>=3 else 'COTES_NON_EXTRAITES' if count==0 else 'COTES_PARTIELLES'
