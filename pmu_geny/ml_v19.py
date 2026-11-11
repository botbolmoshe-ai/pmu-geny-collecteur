"""PMU V19: features temporelles, apprentissage supervisé et audit sans fuite de cote.

Source d'apprentissage: instantanés de *prévisions antérieures au départ* et
arrivées PMU vérifiées; aucune reconstitution a posteriori des variables.
Les cotes, rapports, prix et rangs à l'arrivée ne sont JAMAIS des features.
"""
from __future__ import annotations
import csv, json, math, os
from datetime import datetime, timedelta, timezone
from pathlib import Path

FEATURES = ('courses_30j','courses_60j','courses_120j','podiums_30j','podiums_120j',
            'victoires_120j','disqualifications_120j','score_forme','forme_30j','forme_ancien',
            'jours_repos','distance_m','distance_ecart_m','aptitude_hippodrome',
            'taux_podium_distance','nb_partants','meteo_pluie_mm','meteo_vent_kmh','meteo_temperature_c','meteo_humidite_pct',
            'avis_experts_score','info_ecurie_score','driver_score','entraineur_score','pmu_score_direct')
MIN_COURSES_TRAIN = 100
MIN_ROWS_TRAIN = 700

def load(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return default

def save(path, doc):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def numeric(v):
    try:
        x=float(str(v).replace(',','.'))
        return x if math.isfinite(x) else None
    except (ValueError,TypeError): return None

def features(horse, history, course, context=None):
    """Strictement les informations antérieures à la course; champs absents = None."""
    context=context or {}
    departure=datetime.fromisoformat(course['depart'])
    date=departure.date()
    rows=[]
    for p in history.get('performances',[]):
        try: d=datetime.fromisoformat(p['date']).date()
        except (KeyError,ValueError,TypeError):continue
        age=(date-d).days
        if age<=0 or age>730:continue
        rank=str(p.get('classement','')).strip()
        num=int(rank) if rank.isdecimal() else None
        dist=numeric(p.get('distance_m'))
        rows.append((age,num,rank.casefold(),dist,str(p.get('hippodrome','')).casefold()))
    def pts(rank):return {1:5.,2:3.5,3:2.5,4:1.3,5:1.}.get(rank,0.)
    recent=[r for r in rows if r[0]<=120]
    early=[r for r in rows if 30<r[0]<=120]
    last=[r for r in rows if r[0]<=30]
    target_dist=numeric(course.get('distance_m'))
    target_hip=str(course.get('hippodrome','')).casefold()
    comparable=[r for r in rows if target_dist is not None and r[3] is not None and abs(r[3]-target_dist)<=250]
    hip=[r for r in rows if target_hip and target_hip in r[4]]
    def avg(seq):return round(sum(pts(r[1]) for r in seq)/len(seq),5) if seq else None
    def pct(seq):return round(sum(r[1] is not None and r[1]<=3 for r in seq)/len(seq),5) if seq else None
    # Données contextuelles acceptées uniquement si provenance et heure de collecte valides.
    out={
      'courses_30j':len(last),'courses_60j':sum(r[0]<=60 for r in recent),
      'courses_120j':len(recent),'podiums_30j':pct(last),'podiums_120j':pct(recent),
      'victoires_120j':sum(r[1]==1 for r in recent),
      'disqualifications_120j':sum(r[2] in ('dai','di','da','disq') for r in recent),
      'score_forme':avg(recent),'forme_30j':avg(last),'forme_ancien':avg(early),
      'jours_repos':min((r[0] for r in rows),default=None),
      'distance_m':target_dist,
      'distance_ecart_m':min((abs(r[3]-target_dist) for r in rows if r[3] is not None),default=None) if target_dist is not None else None,
      'aptitude_hippodrome':pct(hip),'taux_podium_distance':pct(comparable),
      'nb_partants':numeric(course.get('nombre_declares')),
    }
    for key in FEATURES:
        if key not in out:out[key]=numeric(context.get(key))
    return out

def _valid_context(cache,course,now):
    """Contexte facultatif saisi/importé et sourcé, antérieur au départ."""
    path=Path(cache)/'contextes'/f"{course['date']}_{course['code']}.json"
    d=load(path,{}) or {}; results={}
    for item in d.get('observations',[]):
        if not isinstance(item,dict):continue
        key=item.get('champ'); value=numeric(item.get('valeur'))
        try: stamp=datetime.fromisoformat(item['collecte_utc'])
        except (KeyError,TypeError,ValueError):continue
        if stamp.tzinfo is None or not item.get('source_url'):continue
        if stamp>now or stamp>=datetime.fromisoformat(course['depart']):continue
        if key in FEATURES and value is not None:
            # Pour les observations individuelles, prioriser l'index du cheval.
            numero=item.get('numero')
            results[(str(numero) if numero is not None else '*',key)]=value
    return results

def snapshot(cache,course,manifest,now=None):
    """Capture immuable pré-départ; ne remplace jamais une capture existante."""
    now=now or datetime.now(timezone.utc)
    departure=datetime.fromisoformat(course['depart'])
    if now>=departure:return 'TROP_TARD'
    base=Path(cache)/'ml'/'instantanes'/f"{course['date']}_{course['code']}.json"
    if base.exists():return 'DEJA_CAPTURE'
    cid=manifest['courses'][0]['course_id']
    np=load(Path(cache)/'participations'/f'{cid}.json',{}) or {}
    states={str(x.get('numero')):x.get('statut_participation') for x in np.get('chevaux',[])}
    eligible=[h for h in manifest['courses'][0]['partants'] if states.get(str(h['numero']))=='PARTANT']
    if len(eligible)<3:return 'NP_NON_VERIFIE'
    if len(states)!=len(manifest['courses'][0]['partants']) or any(x not in ('PARTANT','NON_PARTANT') for x in states.values()):return 'NP_NON_VERIFIE'
    context=_valid_context(cache,course,now)
    rows=[]
    for h in eligible:
        doc=load(Path(cache)/'historiques'/str(h['id'])/'historique_geny.json',{}) or {}
        c={key:v for (num,key),v in context.items() if num in ('*',str(h['numero']))}
        rows.append({'numero':int(h['numero']),'cheval_id':str(h['id']),'nom':h['nom'],
                     'features':features(h,doc,course,c)})
    save(base,{'date':course['date'],'code':course['code'],'depart':course['depart'],
               'capture_utc':now.isoformat(),'features_schema':'v19.1','chevaux':rows,
               'regle':'snapshot anterieur au depart; cotes et arrivees exclues des features'})
    return 'CAPTURE'


def snapshot_pmu(cache,course,raw,now=None):
    """Capture ML avant depart depuis les partants PMU, sans manifeste Geny.

    Reutilise seulement les historiques Geny COMPLETS relies par un nom
    normalise unique dans le journal persistant; aucun appariement approximatif.
    """
    import unicodedata
    from .auto_v18 import _list, _num
    from .top3_independants_v22 import _form_score
    now=now or datetime.now(timezone.utc)
    departure=datetime.fromisoformat(course['depart'])
    if now.tzinfo is None or now>=departure:return 'TROP_TARD'
    cache=Path(cache)
    base=cache/'ml'/'instantanes'/f"{course['date']}_{course['code']}.json"
    if base.exists():return 'DEJA_CAPTURE'
    participants=_list(raw,'participants','partants')
    if len(participants)<3:return 'PARTANTS_INSUFFISANTS'
    journal=(load(cache/'etat_persistant.json',{}) or {}).get('chevaux',{})
    def canonical(value):
        value=unicodedata.normalize('NFKD',str(value).casefold())
        return ''.join(ch for ch in value if not unicodedata.combining(ch) and ch.isalnum())
    matched={}
    for ident,item in journal.items():
        if item.get('statut')!='COMPLET':continue
        filepath=cache/'historiques'/str(ident)/'historique_geny.json'
        if not filepath.exists():continue
        doc=load(filepath,{}) or {}
        if doc.get('statut')!='COMPLET' or not isinstance(doc.get('performances'),list):continue
        name=canonical(item.get('nom',''))
        if not name:continue
        matched.setdefault(name,[]).append((str(ident),doc))
    context=_valid_context(cache,course,now)
    rows=[];seen=set();with_history=0;unknown_np=0
    for item in participants:
        if not isinstance(item,dict):continue
        numero=_num(item,'numPmu','num','numero','numeroPmu')
        if numero is None or numero in seen:return 'NUMEROS_PMU_INCOHERENTS'
        seen.add(numero)
        if item.get('nonPartant') is True or str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):
            continue
        if item.get('nonPartant') is not False and str(item.get('statut','')).upper()!='PARTANT':
            unknown_np+=1
        name=next((str(item[k]).strip() for k in ('nomCheval','nom','nomParticipant') if isinstance(item.get(k),str) and item[k].strip()),'')
        match=matched.get(canonical(name),[])
        ident,histo=match[0] if len(match)==1 else ('',{})
        if ident:with_history+=1
        c={key:value for (num,key),value in context.items() if num in ('*',str(numero))}
        direct=_form_score(item)
        if direct is not None:c['pmu_score_direct']=direct
        features_values=features({'numero':numero,'nom':name},histo,course,c)
        rows.append({'numero':numero,'cheval_id':ident,'nom':name,
                     'historique_ok':bool(ident),'score_direct_pmu':direct,
                     'features':features_values})
    if len(rows)<3:return 'PARTANTS_INSUFFISANTS'
    if course.get('nombre_declares') and len(seen)!=int(course['nombre_declares']):
        return 'LISTE_PARTANTS_INCOMPLETE'
    save(base,{'date':course['date'],'code':course['code'],'depart':course['depart'],
               'capture_utc':now.isoformat(),'features_schema':'v22.0',
               'source':'PMU_API_PARTICIPANTS','nombre_chevaux':len(rows),
               'historiques_complets_reutilises':with_history,
               'np_non_verifies':unknown_np,'chevaux':rows,
               'regle':'capture PMU pre-depart immutable, ni cote ni arrivee utilisee'})
    return 'CAPTURE_PMU'

def dataset(cache):
    """Reconstitue uniquement des exemples étiquetés via arrivée vérifiée postérieure à la capture."""
    examples=[]; course_count=0
    for snap in sorted((Path(cache)/'ml'/'instantanes').glob('*.json')) if (Path(cache)/'ml'/'instantanes').exists() else []:
        s=load(snap,{}) or {};arr=load(Path(cache)/'arrivees'/snap.name,{}) or {}
        if not arr:continue
        try:
            depart=datetime.fromisoformat(s['depart']);capt=datetime.fromisoformat(s['capture_utc'])
            checked=datetime.fromisoformat(arr['verifie_utc'])
            if not capt<depart<checked:continue
        except (KeyError,ValueError,TypeError):continue
        placed={int(x['numero']) for x in arr.get('arrivee',[]) if x.get('rang') in (1,2,3)}
        if len(placed)!=3:continue
        horses=s.get('chevaux',[])
        if len(horses)<3 or len({int(x['numero']) for x in horses})!=len(horses):continue
        course_count+=1
        for row in horses:
            examples.append({'course':s['date']+'_'+s['code'],'depart':s['depart'],
              'numero':int(row['numero']),'y':int(int(row['numero']) in placed),'features':row['features']})
    return examples,course_count

def train(cache, min_courses=MIN_COURSES_TRAIN, min_rows=MIN_ROWS_TRAIN):
    """Validation temporelle par courses entières. Promotion seulement si cohérente."""
    records,n=dataset(cache)
    status={'entrainement_utc':datetime.now(timezone.utc).isoformat(), 'courses':n,'lignes':len(records),
            'minimum_courses':min_courses,'minimum_lignes':min_rows,'etat':'INSUFFISANT'}
    if n<min_courses or len(records)<min_rows:
        save(Path(cache)/'ml'/'entrainement.json',status);return status
    try:
        import joblib
        import numpy as np
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import make_pipeline
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import log_loss, brier_score_loss
    except ImportError:
        status['etat']='DEPENDANCES_ML_ABSENTES';save(Path(cache)/'ml'/'entrainement.json',status);return status
    ordered=sorted({r['course']:r['depart'] for r in records}.items(),key=lambda x:x[1]);split=int(len(ordered)*.8)
    train_ids={k for k,v in ordered[:split]};valid_ids={k for k,v in ordered[split:]}
    a=[r for r in records if r['course'] in train_ids];b=[r for r in records if r['course'] in valid_ids]
    X=lambda r:[[numeric(z['features'].get(k)) if numeric(z['features'].get(k)) is not None else float('nan') for k in FEATURES] for z in r]
    x1,x2=np.asarray(X(a)),np.asarray(X(b));y1=np.asarray([r['y'] for r in a]);y2=np.asarray([r['y'] for r in b])
    candidates={
      'regression_logistique':make_pipeline(SimpleImputer(strategy='constant',fill_value=-1),LogisticRegression(max_iter=500,class_weight='balanced')),
      'gradient_boosting':make_pipeline(SimpleImputer(strategy='constant',fill_value=-1),HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=9,l2_regularization=2,random_state=42))
    }
    scores={}
    for name,model in candidates.items():
        model.fit(x1,y1);prob=np.clip(model.predict_proba(x2)[:,1],1e-6,1-1e-6)
        scores[name]={'brier':round(float(brier_score_loss(y2,prob)),6),
                      'logloss':round(float(log_loss(y2,prob,labels=[0,1])),6)}
    winner=min(scores,key=lambda key:scores[key]['brier']);model=candidates[winner]
    model.fit(np.asarray(X(records)),np.asarray([r['y'] for r in records]))
    target=Path(cache)/'ml'/'modele.joblib';target.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({'model':model,'features':FEATURES,'modele':winner,'schema':'v19.1'},target)
    status.update({'etat':'ENTRAINE','modele':winner,'validation_temporelle':scores,
                   'courses_validation':len(valid_ids),'note':'Validation hors echantillon; pas de garantie de resultat'})
    save(Path(cache)/'ml'/'entrainement.json',status);return status

def predict(cache,course,manifest,now=None):
    """Prévision live: filtre NP, modèle entraîné ou absence déclarée."""
    now=now or datetime.now(timezone.utc)
    if now>=datetime.fromisoformat(course['depart']):return 'APRES_DEPART'
    cid=manifest['courses'][0]['course_id'];np=load(Path(cache)/'participations'/f'{cid}.json',{}) or {}
    states={str(x['numero']):x.get('statut_participation') for x in np.get('chevaux',[])}
    horses=manifest['courses'][0]['partants']
    if len(states)!=len(horses) or any(states.get(str(h['numero'])) not in ('PARTANT','NON_PARTANT') for h in horses):return 'NP_NON_VERIFIE'
    eligible=[h for h in horses if states[str(h['numero'])]=='PARTANT']
    if len(eligible)<3:return 'PARTANTS_INSUFFISANTS'
    model_path=Path(cache)/'ml'/'modele.joblib'
    if not model_path.exists():return 'ML_NON_ENTRAINE'
    try:
        import joblib, numpy as np
        packed=joblib.load(model_path)
    except (ImportError,OSError,ValueError,KeyError) as ex:return f'MODELE_INDISPONIBLE_{type(ex).__name__}'
    if tuple(packed.get('features',()))!=FEATURES:return 'MODELE_SCHEMA_OBSOLETE_REENTRAINEMENT_REQUIS'
    context=_valid_context(cache,course,now)
    rows=[]; vectors=[]
    for h in eligible:
        doc=load(Path(cache)/'historiques'/str(h['id'])/'historique_geny.json',{}) or {}
        c={key:v for (num,key),v in context.items() if num in ('*',str(h['numero']))}
        vector=features(h,doc,course,c)
        rows.append({'numero':int(h['numero']),'nom':h['nom'],'cheval_id':str(h['id'])})
        vectors.append([numeric(vector.get(k)) if numeric(vector.get(k)) is not None else float('nan') for k in FEATURES])
    probabilities=packed['model'].predict_proba(np.asarray(vectors))[:,1]
    for row,p in zip(rows,probabilities):row['proba_podium_estimee']=round(float(p),5)
    rows.sort(key=lambda r:(-r['proba_podium_estimee'],r['numero']))
    base=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_ml_latest.json"
    save(base,{'date':course['date'],'course':course['code'],'calcul_utc':now.isoformat(),
               'depart':course['depart'],'modele':packed['modele'],'statut':'ML_ENTRAINE_NON_CALIBRE',
               'top3':rows[:3],'classement_complet':rows,'np_utc':np.get('date_controle_utc'),
               'note':'Cotes exclues; probabilities non garanties'})
    return 'ML_CALCULE'

def export_comparatif(cache,course,manifest):
    """CSV par partant: baseline, ML, NP, cote à l'approche du départ, arrivée."""
    key=f"{course['date']}_{course['code']}";cid=manifest['courses'][0]['course_id']
    base=load(Path(cache)/'pronostics'/f'{key}_top3.json',{}) or {}
    ml=load(Path(cache)/'pronostics'/f'{key}_ml_latest.json',{}) or {}
    baseline_final=load(Path(cache)/'pronostics'/f'{key}_baseline_latest.json',{}) or base
    np=load(Path(cache)/'participations'/f'{cid}.json',{}) or {}
    odds=load(Path(cache)/'cotes'/f'{key}.json',{}) or {}
    arrived=load(Path(cache)/'arrivees'/f'{key}.json',{}) or {}
    b_rank={int(x['numero']):i for i,x in enumerate(base.get('classement_complet',[]),1)}
    bf_rank={int(x['numero']):i for i,x in enumerate(baseline_final.get('classement_complet',[]),1)}
    m_rank={int(x['numero']):i for i,x in enumerate(ml.get('classement_complet',[]),1)}
    m_proba={int(x['numero']):x.get('proba_podium_estimee') for x in ml.get('classement_complet',[])}
    np_map={int(x['numero']):x for x in np.get('chevaux',[])}
    odd_map={int(x['numero']):x for x in odds.get('chevaux',[])}
    arank={int(x['numero']):x['rang'] for x in arrived.get('arrivee',[])}
    contexte=load(Path(cache)/'contextes'/f"{course['date']}_{course['code']}.json",{}) or {}
    meteo={x.get('champ'):x.get('valeur') for x in contexte.get('observations',[]) if isinstance(x,dict) and x.get('numero') is None}
    cols=['date','course','depart','numero','nom','statut_np','baseline_rang','baseline_top3',
          'baseline_final_rang','baseline_final_top3','ml_rang','ml_top3','ml_proba_podium','cote_avant_depart','cote_heure_utc',
          'cote_source','cote_statut','arrivee_rang','arrivee_podium','baseline_hits_course','baseline_final_hits_course',
          'ml_hits_course','ml_etat','version_baseline_utc','version_ml_utc','meteo_pluie_mm','meteo_vent_kmh','meteo_temperature_c','meteo_humidite_pct','meteo_capture_utc','meteo_source']
    ar3={n for n,r in arank.items() if r in (1,2,3)}
    baseline_hits=len(ar3&{n for n,v in b_rank.items() if v<=3}) if len(ar3)==3 and b_rank else ''
    baseline_final_hits=len(ar3&{n for n,v in bf_rank.items() if v<=3}) if len(ar3)==3 and bf_rank else ''
    ml_hits=len(ar3&{n for n,v in m_rank.items() if v<=3}) if len(ar3)==3 and m_rank else ''
    output=[]
    for h in manifest['courses'][0]['partants']:
        n=int(h['numero']);o=odd_map.get(n,{})
        output.append({'date':course['date'],'course':course['code'],'depart':course['depart'],
          'numero':n,'nom':h['nom'],'statut_np':np_map.get(n,{}).get('statut_participation','NP_NON_VERIFIE'),
          'baseline_rang':b_rank.get(n,''),'baseline_top3':'OUI' if n in b_rank and b_rank[n]<=3 else '',
          'baseline_final_rang':bf_rank.get(n,''),'baseline_final_top3':'OUI' if n in bf_rank and bf_rank[n]<=3 else '',
          'ml_rang':m_rank.get(n,''),'ml_top3':'OUI' if n in m_rank and m_rank[n]<=3 else '',
          'ml_proba_podium':m_proba.get(n,''),
          'cote_avant_depart':o.get('cote',''),'cote_heure_utc':o.get('heure_utc',''),
          'cote_source':o.get('source',''),'cote_statut':o.get('statut','NON_DISPONIBLE'),
          'arrivee_rang':arank.get(n,''),'arrivee_podium':'OUI' if n in ar3 else ('NON' if len(ar3)==3 else ''),
          'baseline_hits_course':baseline_hits,'baseline_final_hits_course':baseline_final_hits,'ml_hits_course':ml_hits,
          'ml_etat':ml.get('statut','ML_NON_ENTRAINE'),
          'version_baseline_utc':base.get('created_utc',''),'version_ml_utc':ml.get('calcul_utc',''),
          'meteo_pluie_mm':meteo.get('meteo_pluie_mm',''),'meteo_vent_kmh':meteo.get('meteo_vent_kmh',''),
          'meteo_temperature_c':meteo.get('meteo_temperature_c',''),'meteo_humidite_pct':meteo.get('meteo_humidite_pct',''),
          'meteo_capture_utc':contexte.get('meteo_collecte_utc',''),'meteo_source':contexte.get('meteo_source','')})
    path=Path(cache)/'exports'/cid/'comparatif_predictions.csv';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=cols,delimiter=';');w.writeheader();w.writerows(output)
    return path

# Les cotes sont EXCLUES explicitement de FEATURES et des modèles.
assert not any('cote' in x or 'rapport' in x or 'arrivee' in x for x in FEATURES)
