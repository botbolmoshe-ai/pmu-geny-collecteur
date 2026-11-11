"""TOP3 expérimental V18, non probabiliste; figement H-1, recalcul si NP confirmé.

Baseline de secours distincte de l'agent avancé PMU existant, NON validée
statistiquement. Ne jamais utiliser de résultat postérieur à la course.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

def read(file):
    try:return json.loads(Path(file).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def preparer_top3(cache, course, manifest, now=None):
    from .auto_v18 import save
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if depart.tzinfo is None: raise ValueError('Heure de départ sans fuseau')
    # Premiere prevision au plus tot H-1:15; rattrapage autorise jusqu'au depart.
    # Un rattrapage apres H-1 est horodate et ne se fait jamais a posteriori.
    debut=depart-timedelta(minutes=75); fin=depart
    file=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_top3.json"
    if file.exists():return 'DEJA_FIGE'
    if not debut<=now.astimezone(depart.tzinfo)<fin:return 'HORS_FENETRE_AVANT_DEPART'
    cid=manifest['courses'][0]['course_id']
    np=read(Path(cache)/'participations'/f'{cid}.json')
    rows=np.get('chevaux',[])
    expected={int(p['numero']) for p in manifest['courses'][0]['partants']}
    np_by_number={int(r['numero']):r for r in rows if str(r.get('numero','')).isdigit() and int(r['numero']) in expected}
    # Une verification NP impossible ne doit pas bloquer le TOP3.
    # Seuls les retraits officiellement verifies sont exclus.
    try:
        checked=datetime.fromisoformat(np.get('date_controle_utc',''))
        np_recent=(now-checked<=timedelta(minutes=30) and
                   set(np_by_number)==expected and
                   all(r.get('statut_participation') in ('PARTANT','NON_PARTANT') for r in np_by_number.values()))
    except (ValueError,TypeError):
        np_recent=False
    scores=[]
    for h in manifest['courses'][0]['partants']:
        n=int(h['numero'])
        if np_by_number.get(n,{}).get('statut_participation')=='NON_PARTANT' and np_recent:continue
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
       'qualite_horaire':'H1' if now<=depart-timedelta(minutes=60) else 'RATTRAPAGE_AVANT_DEPART',
       'statut_np':'VERIFIE' if np_recent else 'NP_NON_VERIFIE',
       'source_np':'PMU_API' if np_recent else 'NON_VERIFIE',
       'np_verifie_utc':np.get('date_controle_utc','') if np_recent else '',
       'top3':ranked[:3],'classement_complet':ranked}
    save(file,result)
    return 'FIGE_BASELINE_EXPERIMENTALE'


def actualiser_top3_np(cache, course, manifest, now=None):
    """Mise à jour avant départ après nouveau retrait; référence H-1 jamais écrasée."""
    from .auto_v18 import save
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if now>=depart:return 'APRES_DEPART'
    orig=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_top3.json"
    initial=read(orig)
    if not initial:return 'H1_NON_FIGE'
    cid=manifest['courses'][0]['course_id']
    data=read(Path(cache)/'participations'/f'{cid}.json')
    try:
        check=datetime.fromisoformat(data['date_controle_utc'])
        if now-check>timedelta(minutes=30):return 'NP_PERIME'
    except (KeyError,ValueError,TypeError):return 'NP_NON_VERIFIE'
    mapping={int(x['numero']):x.get('statut_participation') for x in data.get('chevaux',[])}
    expected={int(h['numero']) for h in manifest['courses'][0]['partants']}
    if set(mapping)!=expected or any(x not in ('PARTANT','NON_PARTANT') for x in mapping.values()):return 'NP_NON_VERIFIE'
    # Recalcul du classement via scores initiaux et changement de contexte NP.
    # Pas de faux recalcul des scores tactiques : baseline reste un score de forme.
    remaining=[x for x in initial['classement_complet'] if mapping.get(int(x['numero']))=='PARTANT']
    if len(remaining)<3:return 'PARTANTS_INSUFFISANTS'
    latest=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_baseline_latest.json"
    previous=read(latest)
    new_top=[int(x['numero']) for x in remaining[:3]]
    if previous and [int(x['numero']) for x in previous.get('top3',[])]==new_top:
        return 'INCHANGE'
    stamp={'date_course':course['date'],'course':course['code'],'depart':course['depart'],
      'created_utc':now.isoformat(),'mode':'BASELINE_RECALCULEE_APRES_NP',
      'origine_h1':initial['created_utc'],'source_np':'PMU_API',
      'np_verifie_utc':data['date_controle_utc'],'top3':remaining[:3],
      'classement_complet':remaining}
    save(latest,stamp)
    archive=Path(cache)/'pronostics'/'versions'/f"{course['date']}_{course['code']}_baseline_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    save(archive,stamp)
    return 'ACTUALISE'
