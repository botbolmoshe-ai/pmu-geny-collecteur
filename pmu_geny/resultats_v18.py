"""Lecture défensive des arrivées PMU après la course; aucune inférence de rang."""
from datetime import datetime,timezone
from pathlib import Path
import json

def enregistrer_resultats(cache:Path,course:dict,participants:dict,*,observe=None):
    from .auto_v18 import _list,_num,save
    from .echeances_production import instant
    depart = instant(course.get('depart'))
    observe = datetime.now(timezone.utc) if observe is None else instant(observe)
    if not depart or not observe or observe <= depart:
        return 'ARRIVEE_NON_VERIFIEE'
    raw=_list(participants,'participants','partants')
    if not raw:return 'ARRIVEE_NON_VERIFIEE'
    rows=[]
    for item in raw:
        n=_num(item,'numPmu','num','numero','numeroPmu')
        rank=_num(item,'ordreArrivee','rangArrivee','rang')
        if n is None:continue
        if rank is not None and rank>0:rows.append({'numero':n,'rang':rank})
    ranks={x['rang'] for x in rows}
    if not {1,2,3}.issubset(ranks) or len({x['numero'] for x in rows})!=len(rows):
        return 'ARRIVEE_NON_VERIFIEE'
    if len([r for r in rows if r['rang'] in (1,2,3)])!=3:return 'ARRIVEE_NON_VERIFIEE'
    file=Path(cache)/'arrivees'/f"{course['date']}_{course['code']}.json"
    if file.exists():return 'ARRIVEE_DEJA_ENREGISTREE'
    # Heure de lecture des rangs dans le flux PMU. L'heure de proclamation
    # officielle n'est pas fournie par cette réponse.
    save(file,{'date':course['date'],'course':course['code'],'source':'PMU_API_PARTICIPANTS',
               'verifie_utc':observe.astimezone(timezone.utc).isoformat(),'arrivee':sorted(rows,key=lambda r:r['rang'])})
    topfile=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_top3.json"
    if topfile.exists():
        top=json.loads(topfile.read_text(encoding='utf-8'))
        trio={x['numero'] for x in top['top3']};arrivee={x['numero'] for x in rows if x['rang']<=3}
        save(Path(cache)/'evaluations'/f"{course['date']}_{course['code']}.json",
             {'course':course['code'],'date':course['date'],'mode':top['mode'],
              'hits_top3':len(trio & arrivee),'nombre_previsions':3,'frozen_at':top['frozen_at'],
              'source_arrivee':'PMU_API_PARTICIPANTS'})
    return 'ARRIVEE_ENREGISTREE'
