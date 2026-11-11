"""Relevé informatif des cotes PMU; hors features prédictives.
Une valeur enregistrée est un instantané, PAS une cote définitive garantie.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .ml_v19 import load, save, numeric

KEYS=('rapportDirect','coteDirect','cote','rapportProbable')

def collecter(cache,course,participants,now=None):
    from .auto_v18 import _list,_num
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if now>depart:return 'APRES_DEPART_SANS_RELEVE'
    raw=_list(participants,'participants','partants')
    if not raw:return 'COTES_INDISPONIBLES'
    data=[]
    for p in raw:
        if not isinstance(p,dict):continue
        n=_num(p,'numPmu','num','numero','numeroPmu')
        if n is None:continue
        cote=None; champ=None
        for key in KEYS:
            value=p.get(key)
            if isinstance(value,dict):
                value=value.get('rapport') or value.get('valeur')
            x=numeric(value)
            if x is not None and x>0:
                cote=x;champ=key;break
        data.append({'numero':n,'cote':cote,'source':'PMU_API_PARTICIPANTS' if cote else '',
                     'champ_pmu':champ or '', 'heure_utc':now.isoformat(),
                     'statut':'RELEVE_HORODATE' if cote else 'NON_DISPONIBLE'})
    if not data:return 'COTES_INDISPONIBLES'
    dest=Path(cache)/'cotes'/f"{course['date']}_{course['code']}.json"
    old=load(dest,{}) or {}
    history=old.get('releves',[])
    history.append({'heure_utc':now.isoformat(),'chevaux':data})
    # Conserver l'ensemble des relevés pour audit. Dernier observé avant le départ.
    count=sum(item['cote'] is not None for item in data)
    save(dest,{'date':course['date'],'course':course['code'],'depart':course['depart'],
         'chevaux':data,'releves':history,'cotes_extraites':count,
         'statut':'COTES_RELEVEES' if count>=3 else 'COTES_NON_EXTRAITES' if count==0 else 'COTES_PARTIELLES',
         'note':'Instantane PMU; absence de cote ne prouve pas indisponibilite chez PMU.'})
    return 'COTES_RELEVEES' if count>=3 else 'COTES_NON_EXTRAITES' if count==0 else 'COTES_PARTIELLES'
