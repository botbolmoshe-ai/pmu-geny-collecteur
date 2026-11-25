"""Lecture défensive des arrivées PMU après la course; aucune inférence de rang."""
from datetime import datetime,timezone
from pathlib import Path
import json

def classement_podium(rows):
    """Valider les rangs de compétition PMU, y compris les ex æquo."""
    try:
        podium = sorted((row['rang'], int(row['numero'])) for row in rows
                        if row.get('rang') in (1, 2, 3))
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return []
    numbers = [number for _, number in podium]
    if len(numbers) != 3 or len(set(numbers)) != 3 or not all(1 <= n <= 30 for n in numbers):
        return []
    ranks = [rank for rank, _ in podium]
    if any(rank != ranks.index(rank) + 1 for rank in ranks):
        return []
    return numbers


def podium_programme(course):
    ordre = course.get('ordreArrivee')
    flags = [course.get(flag) for flag in ('arriveeDefinitive', 'isArriveeDefinitive')]
    if not any(flag is True for flag in flags) or any(flag is False for flag in flags):
        return []
    if not isinstance(ordre, list):
        return []
    rows = []
    for group in ordre:
        rank = len(rows) + 1
        if rank > 3:
            break
        if (not isinstance(group, list) or not group
                or any(type(number) is not int for number in group)):
            return []
        rows.extend({'rang': rank, 'numero': number} for number in group)
    return classement_podium(rows)


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
    if len({row['numero'] for row in rows}) != len(rows):
        return 'ARRIVEE_NON_VERIFIEE'
    rows.sort(key=lambda row: (row['rang'], row['numero']))
    podium = classement_podium(rows)
    if not podium or podium != course.get('podium_definitif_pmu'):
        return 'ARRIVEE_NON_VERIFIEE'
    file=Path(cache)/'arrivees'/f"{course['date']}_{course['code']}.json"
    if file.exists():return 'ARRIVEE_DEJA_ENREGISTREE'
    # Heure de lecture des rangs dans le flux PMU. L'heure de proclamation
    # officielle n'est pas fournie par cette réponse.
    save(file,{'date':course['date'],'course':course['code'],'source':'PMU_API_PARTICIPANTS',
               'verifie_utc':observe.astimezone(timezone.utc).isoformat(),
               'podium_definitif_pmu':podium,'arrivee':rows})
    topfile=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_top3.json"
    if topfile.exists():
        top=json.loads(topfile.read_text(encoding='utf-8'))
        trio={x['numero'] for x in top['top3']};arrivee={x['numero'] for x in rows if x['rang']<=3}
        save(Path(cache)/'evaluations'/f"{course['date']}_{course['code']}.json",
             {'course':course['code'],'date':course['date'],'mode':top['mode'],
              'hits_top3':len(trio & arrivee),'nombre_previsions':3,'frozen_at':top['frozen_at'],
              'source_arrivee':'PMU_API_PARTICIPANTS'})
    return 'ARRIVEE_ENREGISTREE'
