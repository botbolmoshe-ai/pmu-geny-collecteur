"""TOP3 expérimental V18, non probabiliste; référence à H-2, recalcul si NP confirmé.

Baseline de secours distincte de l'agent avancé PMU existant, NON validée
statistiquement. Ne jamais utiliser de résultat postérieur à la course.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from .echeances_production import PHASES

def read(file):
    try:return json.loads(Path(file).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def _controle_np(data, expected, now):
    """Un retrait atteste ne devient pas un partant lorsque le controle vieillit."""
    mapping={}
    try:
        checked=datetime.fromisoformat(data['date_controle_utc'])
        if checked.tzinfo is None or checked>now:return {},False
    except (KeyError,ValueError,TypeError):return {},False
    for row in data.get('chevaux',[]):
        try:
            n=int(row['numero'])
            observed=datetime.fromisoformat(row.get('date_verification_np') or data['date_controle_utc'])
            if n not in expected or observed.tzinfo is None or observed>now:continue
        except (KeyError,TypeError,ValueError):continue
        if n in mapping:return {},False
        mapping[n]=row.get('statut_participation')
    recent=(timedelta(0)<=now-checked<=timedelta(minutes=30) and set(mapping)==expected and
            all(v in ('PARTANT','NON_PARTANT') for v in mapping.values()))
    return mapping,recent

def preparer_top3(cache, course, manifest, now=None):
    from .auto_v18 import save
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if depart.tzinfo is None: raise ValueError('Heure de départ sans fuseau')
    echeance = depart - PHASES['H2']
    debut = echeance - timedelta(minutes=15)
    file=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_top3.json"
    if file.exists():return 'DEJA_FIGE'
    if not debut<=now<depart:return 'HORS_FENETRE_AVANT_DEPART'
    cid=manifest['courses'][0]['course_id']
    np=read(Path(cache)/'participations'/f'{cid}.json')
    expected={int(p['numero']) for p in manifest['courses'][0]['partants']}
    # Une verification NP impossible ne doit pas bloquer le TOP3.
    # Seuls les retraits officiellement verifies sont exclus.
    np_by_number,np_recent=_controle_np(np,expected,now)
    scores=[]
    for h in manifest['courses'][0]['partants']:
        n=int(h['numero'])
        if np_by_number.get(n)=='NON_PARTANT':continue
        doc=read(Path(cache)/'historiques'/str(h['id'])/'historique_geny.json')
        perfs=doc.get('performances',[])
        if not perfs:continue
        history=[]
        for p in perfs:
            try:
                date=datetime.fromisoformat(p['date']).date()
                if date>=depart.date():continue
                age=(depart.date()-date).days
                if age>120:continue
                rank=str(p.get('classement','')).strip()
                grade=int(rank) if rank.isdecimal() else None
                points=({1:5,2:3.5,3:2.5,4:1.3,5:1}.get(grade,0))
                history.append((age,points))
            except (ValueError,TypeError):continue
        if not history:continue
        # Baseline non calibrée : moyenne pondérée 120 jours; minimum 2 courses.
        if len(history)<2:continue
        score=sum(v*(1 if age<=30 else .7 if age<=60 else .4) for age,v in history)/len(history)
        scores.append({'numero':n,'cheval_id':str(h['id']),'nom':h['nom'],'score_exploratoire':round(score,4),'historique_120j':len(history)})
    if len(scores)<3:return 'DONNEES_INSUFFISANTES'
    ranked=sorted(scores,key=lambda x:(-x['score_exploratoire'],-x['historique_120j'],x['numero']))
    result={'date_course':course['date'],'course':course['code'],'course_id_geny':cid,
       'created_utc':now.isoformat(),'frozen_at':now.isoformat(),'depart':depart.isoformat(),
       'mode':'BASELINE_EXPERIMENTALE_NON_VALIDEE','note':'Scores non probabilistes; aucune garantie de gain',
       'jalon_reference':'H2',
       'qualite_horaire':'H2' if now<=echeance else 'RATTRAPAGE_AVANT_DEPART',
       'statut_np':'VERIFIE' if np_recent else 'NP_NON_VERIFIE',
       'non_partants_confirmes':sorted(n for n,s in np_by_number.items() if s=='NON_PARTANT'),
       'source_np':'PMU_API' if np_recent else 'NON_VERIFIE',
       'np_verifie_utc':np.get('date_controle_utc','') if np_recent else '',
       'top3':ranked[:3],'classement_complet':ranked}
    save(file,result)
    return 'FIGE_BASELINE_EXPERIMENTALE'


def actualiser_top3_np(cache, course, manifest, now=None):
    """Mise à jour avant départ après nouveau retrait; la référence initiale reste immuable."""
    from .auto_v18 import save
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if now>=depart:return 'APRES_DEPART'
    orig=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_top3.json"
    initial=read(orig)
    if not initial:return 'BASELINE_NON_FIGEE'
    cid=manifest['courses'][0]['course_id']
    data=read(Path(cache)/'participations'/f'{cid}.json')
    latest=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_baseline_latest.json"
    previous=read(latest)
    expected={int(h['numero']) for h in manifest['courses'][0]['partants']}
    mapping,recent=_controle_np(data,expected,now)
    if not mapping:return 'NP_NON_VERIFIE'
    withdrawn={int(n) for n in initial.get('non_partants_confirmes',[])}
    withdrawn.update(int(n) for n in previous.get('non_partants_confirmes',[]))
    withdrawn.update(n for n,s in mapping.items() if s=='NON_PARTANT')
    if recent:withdrawn.difference_update(n for n,s in mapping.items() if s=='PARTANT')
    if not recent and not withdrawn:return 'NP_PERIME'
    # Recalcul du classement via scores initiaux et changement de contexte NP.
    # Pas de faux recalcul des scores tactiques : baseline reste un score de forme.
    remaining=[x for x in initial['classement_complet'] if int(x['numero']) not in withdrawn]
    sufficient=len(remaining)>=3
    new_top=[int(x['numero']) for x in remaining[:3]] if sufficient else []
    if (previous and [int(x['numero']) for x in previous.get('top3',[])]==new_top
            and set(previous.get('non_partants_confirmes',[]))==withdrawn):
        return 'INCHANGE'
    stamp={'date_course':course['date'],'course':course['code'],'depart':course['depart'],
      'created_utc':now.isoformat(),'mode':'BASELINE_RECALCULEE_APRES_NP',
      'origine_baseline_utc':initial['created_utc'],'jalon_reference':initial.get('jalon_reference', 'H1'),'source_np':'PMU_API',
      'statut_np':'VERIFIE' if recent else 'CONTROLE_ANCIEN_RETRAITS_CONSERVES',
      'non_partants_confirmes':sorted(withdrawn),
      'np_verifie_utc':data['date_controle_utc'],'top3':remaining[:3] if sufficient else [],
      'statut':'COMPLET' if sufficient else 'PARTANTS_INSUFFISANTS',
      'classement_complet':remaining if sufficient else []}
    save(latest,stamp)
    archive=Path(cache)/'pronostics'/'versions'/f"{course['date']}_{course['code']}_baseline_{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    save(archive,stamp)
    return 'ACTUALISE' if sufficient else 'PARTANTS_INSUFFISANTS'
