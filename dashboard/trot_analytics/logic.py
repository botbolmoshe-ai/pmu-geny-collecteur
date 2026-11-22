"""Read-only presentation helpers. No prediction or collection."""
from datetime import datetime, timedelta, timezone
import math
from .dates import depuis_nombre, instant_iso

def number(value):
    try:
        x=float(str(value).replace(',', '.'))
        return x if math.isfinite(x) else None
    except (ValueError,TypeError): return None

def timestamp(value):
    return instant_iso(value)

def matching(value):
    x=number(value)
    return round(x*100/3,2) if x in (0,1,2,3) else None

def records(values):
    if not values or not values[0]: return []
    headers=list(values[0])
    if len(set(headers))!=len(headers): raise ValueError('En-têtes non uniques')
    return [{field: depuis_nombre(field, value) for field, value in zip(headers, row)} for row in values[1:] if row and any(v not in ('',None) for v in row)]

def selected(rows, method):
    selection,rank={'direct':('TOP3 direct · Sélection','TOP3 direct · Rang'),
                    'ml':('ML · Sélection','ML · Rang'),
                    'cotes':('Cotes · Sélection','Cotes · Rang')}[method]
    picked=[r for r in rows if str(r.get(selection,'')).upper()=='OUI']
    if len(picked)!=3 or any(r.get('Non-partant (NP)') == 'NON_PARTANT' or
                             (method != 'cotes' and r.get('Non-partant (NP)') != 'PARTANT')
                             for r in picked):
        return []
    nums=[number(r.get('N°')) for r in picked]
    ranks=[number(r.get(rank)) for r in picked]
    if None in nums or len(set(nums))!=3 or set(ranks)!={1,2,3}: return []
    return sorted(picked,key=lambda r:number(r[rank]))

def podium(value):
    try:
        nums=[int(n.strip()) for n in str(value).split(',')]
        return set(nums) if len(nums)==3 and len(set(nums))==3 and min(nums)>0 else set()
    except (ValueError,TypeError): return set()

def result_matching(row,method,now=None):
    """Use recorded scores, validate the visible evidence; no new prediction."""
    now=now or datetime.now(timezone.utc)
    depart=timestamp(row.get('Départ (Paris)'))
    arrival=timestamp(row.get('Arrivée · Vérifiée UTC'))
    actual=podium(row.get('Arrivée · N° officiels'))
    if not depart or not arrival or not depart<arrival<=now or not actual: return None
    prefix='TOP3 direct' if method=='direct' else 'TOP3 ML'
    chosen=podium(row.get(prefix+' · Chevaux'))
    if not chosen: return None
    if method=='direct':
        created=timestamp(row.get('TOP3 direct · Heure calcul UTC'))
        if not created or not created<depart: return None
    else:
        state=str(row.get('ML · Statut',''))
        if 'ENTRAINE_NON_CALIBRE' not in state and state not in ('ML_ENTRAINE','ML_CALCULE','ML_PRODUCTION_ENTRAINE','ML_ENTRAINE_CALIBRE'): return None
        # Current sheet has no independent ML calculation timestamp.
        # Accept only the stored matching field produced by the guarded engine,
        # otherwise leave it unknown instead of claiming pre-departure proof.
        if number(row.get(prefix+' · Matching (%)')) is None: return None
    hits=number(row.get(prefix+' · Chevaux à l’arrivée (0–3)'))
    if hits!=len(chosen&actual): return None
    derived=matching(hits)
    published=number(row.get(prefix+' · Matching (%)'))
    if published is not None and abs(published-derived)>0.02: return None
    return derived

def couverture_reunions(groups, now):
    reunions = {}
    for rows in groups.values():
        if not rows:
            continue
        first = rows[0]
        reunion, sep, _ = str(first.get('Course R/C', '')).partition('C')
        depart = timestamp(first.get('Départ (Paris)'))
        if not (sep and reunion.startswith('R') and reunion[1:].isdigit() and depart):
            continue
        key = (str(first.get('Hippodrome', '')), reunion)
        entry = reunions.setdefault(key, {'depart': depart, 'partants': []})
        entry['depart'] = min(entry['depart'], depart)
        entry['partants'].extend(row for row in rows if row.get('Non-partant (NP)') == 'PARTANT')
    result = []
    for (hippodrome, reunion), entry in sorted(reunions.items(), key=lambda item: (item[1]['depart'], item[0])):
        if entry['depart'] <= now:
            continue
        horses = entry['partants']
        histories = sum(str(row.get('Historique · État', '')).startswith('HISTO_OK')
                        and (number(row.get('Historique · Nb performances récupérées')) or 0) > 0
                        for row in horses)
        ferrures = sum(bool(row.get('Ferrure · Course du jour')) and row.get('PMU · État ferrure') in {
            'CODE_RECONNU', 'CONVENTION_PMU', 'FERRURE_DISPONIBLE_SOURCEE', 'PMU_FERRURE_DISPONIBLE'}
            for row in horses)
        minutes = (entry['depart'] - timedelta(hours=2) - now).total_seconds() / 60
        result.append({
            'Réunion': reunion, 'Hippodrome': hippodrome, 'Partants confirmés': len(horses),
            'Historiques exploitables': histories, 'Ferrures sourcées': ferrures,
            'Historiques manquants': len(horses) - histories, 'Ferrures manquantes': len(horses) - ferrures,
            'Couverture historique': f'{histories / len(horses):.0%}' if horses else '—',
            'Temps avant H-2': f'{math.ceil(minutes)} min' if minutes > 0 else 'Échu',
        })
    return result
