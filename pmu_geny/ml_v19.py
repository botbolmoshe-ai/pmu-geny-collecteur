"""PMU V19: features temporelles, apprentissage supervisé et audit sans fuite de cote.

Source d'apprentissage: instantanés de *prévisions antérieures au départ* et
arrivées PMU vérifiées; aucune reconstitution a posteriori des variables.
Les cotes, rapports, prix et rangs à l'arrivée ne sont JAMAIS des features.
"""
from __future__ import annotations
import csv, json, math
from datetime import datetime, timezone
from pathlib import Path

FEATURES = ('courses_30j','courses_60j','courses_120j','podiums_30j','podiums_120j',
            'victoires_120j','disqualifications_120j','score_forme','forme_30j','forme_ancien',
            'jours_repos','distance_m','distance_ecart_m','aptitude_hippodrome',
            'taux_podium_distance','nb_partants','meteo_pluie_mm','meteo_vent_kmh','meteo_temperature_c','meteo_humidite_pct',
            'avis_experts_score','info_ecurie_score','driver_score','entraineur_score','pmu_score_direct',
            'age_ans','gains_euros','sexe_male','sexe_femelle','sexe_hongre',
            'ferrure_d4','ferrure_dp','ferrure_da','ferrure_p4','ferrure_pa','ferrure_pp')
MIN_COURSES_TRAIN = 100
MIN_ROWS_TRAIN = 700
MODEL_SCHEMA = 'pmu-podium-v33'

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


def pmu_rows(cache,course,raw,now):
    """Meme extraction PMU pour capture et inference; aucune requete reseau."""
    from .auto_v18 import _list, _num
    from .top3_independants_v22 import _form_score
    from .partants_actuels_v21 import extraire_partants
    cache=Path(cache)
    participants=_list(raw,'participants','partants')
    if len(participants)<3:return 'PARTANTS_INSUFFISANTS',[],{}
    from .liaison_chevaux_v22 import etablir
    names=[{'numero':h.get('numPmu',h.get('numero')),
            'nom':h.get('nomCheval',h.get('nom',h.get('nomParticipant','')))}
           for h in participants if isinstance(h,dict)]
    association=etablir(cache,course,names)
    context=_valid_context(cache,course,now)
    profils=extraire_partants(raw)
    rows=[];seen=set();with_history=0;with_partial=0;unknown_np=0
    for item in participants:
        if not isinstance(item,dict):continue
        numero=_num(item,'numPmu','num','numero','numeroPmu')
        if numero is None or numero in seen:return 'NUMEROS_PMU_INCOHERENTS',[],{}
        seen.add(numero)
        if item.get('nonPartant') is True or str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):
            continue
        if item.get('nonPartant') is not False and str(item.get('statut','')).upper()!='PARTANT':
            unknown_np+=1
        name=next((str(item[k]).strip() for k in ('nomCheval','nom','nomParticipant') if isinstance(item.get(k),str) and item[k].strip()),'')
        if not name:return 'IDENTITE_PMU_ABSENTE',[],{}
        link=association.get(str(numero),{})
        ident,histo=link.get('cheval_id',''),link.get('historique',{})
        if ident:
            if histo.get('statut')=='PARTIEL_HISTORIQUE':with_partial+=1
            else:with_history+=1
        c={key:value for (num,key),value in context.items() if num in ('*',str(numero))}
        direct=_form_score(item)
        if direct is not None:c['pmu_score_direct']=direct
        profil=profils.get(numero,{})
        for feature in ('age_ans','gains_euros'):
            value=profil.get(feature)
            if value is not None:c[feature]=value
        sexe=profil.get('sexe','')
        if sexe:
            for label,feature in (('Mâle','sexe_male'),('Femelle','sexe_femelle'),('Hongre','sexe_hongre')):
                c[feature]=1 if sexe==label else 0
        ferrure=profil.get('ferrure','')
        if ferrure:
            code=str(ferrure).upper()
            for ferrure_code,indicator in [('D4','ferrure_d4'),('DP','ferrure_dp'),
                                   ('DA','ferrure_da'),('P4','ferrure_p4'),
                                   ('PA','ferrure_pa'),('PP','ferrure_pp')]:
                c[indicator]=1 if ferrure_code in code.split('/') else 0
        features_values=features({'numero':numero,'nom':name},histo,course,c)
        rows.append({'numero':numero,'cheval_id':ident,'nom':name,
                     'historique_ok':bool(ident),'historique_complet':bool(ident) and histo.get('statut')=='COMPLET',
                     'methode_liaison':link.get('methode','NON_ASSOCIE'),
                     'score_direct_pmu':direct,
                     'features':features_values})
    if len(rows)<3:return 'PARTANTS_INSUFFISANTS',[],{}
    if course.get('nombre_declares') and len(seen)!=int(course['nombre_declares']):
        return 'LISTE_PARTANTS_INCOMPLETE',[],{}
    return 'OK',rows,{'historiques_complets_reutilises':with_history,
                      'historiques_partiels_reutilises':with_partial,'np_non_verifies':unknown_np}


def snapshot_pmu(cache,course,raw,now=None):
    """Capture immutable; les anciennes captures ne sont jamais enrichies apres coup."""
    now=now or datetime.now(timezone.utc)
    departure=datetime.fromisoformat(course['depart'])
    if now.tzinfo is None or departure.tzinfo is None or now>=departure:return 'TROP_TARD'
    base=Path(cache)/'ml'/'instantanes'/f"{course['date']}_{course['code']}.json"
    if base.exists():return 'DEJA_CAPTURE'
    status,rows,metadata=pmu_rows(cache,course,raw,now)
    if status!='OK':return status
    save(base,{'date':course['date'],'code':course['code'],'depart':course['depart'],
               'capture_utc':now.isoformat(),'features_schema':'v22.1',
               'source':'PMU_API_PARTICIPANTS','nombre_chevaux':len(rows),
               **metadata,'chevaux':rows,
               'regle':'capture PMU pre-depart immutable, ni cote ni arrivee utilisee'})
    return 'CAPTURE_PMU'

def dataset(cache, now=None):
    """Exemples pre-depart avec podium complet et labels deja observes."""
    now=now or datetime.now(timezone.utc)
    examples=[];course_count=0
    for snap in sorted((Path(cache)/'ml'/'instantanes').glob('*.json')):
        s=load(snap,{}) or {};arr=load(Path(cache)/'arrivees'/snap.name,{}) or {}
        try:
            depart=datetime.fromisoformat(s['depart']);capt=datetime.fromisoformat(s['capture_utc'])
            checked=datetime.fromisoformat(arr['verifie_utc'])
            if any(t.tzinfo is None for t in (depart,capt,checked,now)):continue
            if not capt<depart<checked<=now or s.get('np_non_verifies',0):continue
            key=s['date']+'_'+s['code']
            if snap.stem!=key or arr.get('date',s['date'])!=s['date'] or arr.get('course',s['code'])!=s['code']:continue
            podium=[x for x in arr.get('arrivee',[]) if x.get('rang') in (1,2,3)]
            placed={int(x['numero']) for x in podium}
            if len(podium)!=3 or len(placed)!=3 or {x['rang'] for x in podium}!={1,2,3}:continue
            horses=s.get('chevaux',[]);numbers={int(x['numero']) for x in horses}
            if len(horses)<3 or len(numbers)!=len(horses) or not placed<=numbers:continue
            if any(not isinstance(x.get('features'),dict) for x in horses):continue
        except (AttributeError,KeyError,ValueError,TypeError):continue
        course_count+=1
        for row in horses:
            examples.append({'course':key,'depart':s['depart'],'capture_utc':s['capture_utc'],
                'verifie_utc':arr['verifie_utc'],'numero':int(row['numero']),
                'y':int(int(row['numero']) in placed),'features':row['features']})
    return examples,course_count


def train(cache, min_courses=MIN_COURSES_TRAIN, min_rows=MIN_ROWS_TRAIN, now=None):
    """Entrainement commun avec test temporel et promotion conditionnelle."""
    now=now or datetime.now(timezone.utc);cache=Path(cache)
    records,n=dataset(cache,now)
    status={'entrainement_utc':now.isoformat(),'courses':n,'lignes':len(records),
            'minimum_courses':min_courses,'minimum_lignes':min_rows,'etat':'INSUFFISANT',
            'promotion_production':False}
    status_path=cache/'ml'/'entrainement.json'
    if n<min_courses or len(records)<min_rows:
        save(status_path,status);return status
    days=sorted({r['depart'][:10] for r in records})
    if len(days)<3:
        status['etat']='PERIODES_TEMPORELLES_INSUFFISANTES'
        save(status_path,status);return status
    try:
        import joblib
        from .experience_ml import run
    except ImportError:
        status['etat']='DEPENDANCES_ML_ABSENTES';save(status_path,status);return status
    output=cache/'ml'/'experiences'/now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    try:
        report=run(cache,output,days[-2],days[-1],now=now)
    except ValueError as exc:
        status.update(etat='VALIDATION_TEMPORELLE_IMPOSSIBLE',motif=str(exc))
        save(status_path,status);return status
    status.update(rapport=str(output.relative_to(cache)/'rapport.json'),
                  modele=report['modele_choisi_avant_test'],
                  courses_validation=report['decoupage']['validation']['courses'],
                  courses_test=report['decoupage']['test']['courses'],
                  comparaison_test=report.get('ecart_ml_forme_capture'))
    # Benchmark a la meme capture, sur TOUTES les courses test. L'experience
    # seule ne promeut rien; un avantage strict avec IC positif est necessaire.
    comparison=report.get('ecart_ml_forme_capture')
    if not comparison or comparison['courses']!=status['courses_test']:
        status['etat']='NON_PROMU_BENCHMARK_INCOMPLET'
    elif comparison['ic95_bootstrap_par_course'][0]<=0:
        status['etat']='NON_PROMU_AVANTAGE_NON_DEMONTRE'
    else:
        packed=joblib.load(output/'modele_experimental.joblib')
        packed.update(schema=MODEL_SCHEMA,statut='ML_ENTRAINE_NON_CALIBRE',promotion_utc=now.isoformat())
        target=cache/'ml'/'modele.joblib'
        temporary=target.with_suffix('.tmp')
        joblib.dump(packed,temporary);temporary.replace(target)
        status.update(etat='ENTRAINE',promotion_production=True)
    save(status_path,status)
    return status


def predict_pmu(cache,course,raw,now=None):
    """Inference jour J 07h-21h, meme extraction que les captures PMU."""
    from .planification_v20_2 import decision_autorisee
    now=now or datetime.now(timezone.utc)
    departure=datetime.fromisoformat(course['depart'])
    if not decision_autorisee(now,course['date'],departure):return 'HORS_FENETRE_DECISION'
    path=Path(cache)/'ml'/'modele.joblib'
    if not path.exists():return 'ML_NON_ENTRAINE'
    try:
        import joblib
        import numpy as np
        packed=joblib.load(path)
    except (ImportError,OSError,ValueError,KeyError) as exc:return f'MODELE_INDISPONIBLE_{type(exc).__name__}'
    if packed.get('schema')!=MODEL_SCHEMA or tuple(packed.get('features',()))!=FEATURES:
        return 'MODELE_SCHEMA_OBSOLETE_REENTRAINEMENT_REQUIS'
    if packed.get('statut')!='ML_ENTRAINE_NON_CALIBRE':return 'MODELE_NON_PROMU'
    status,rows,metadata=pmu_rows(cache,course,raw,now)
    if status!='OK':return status
    if metadata['np_non_verifies']:return 'NP_NON_VERIFIE'
    vectors=[[numeric(h['features'].get(k)) if numeric(h['features'].get(k)) is not None
              else float('nan') for k in FEATURES] for h in rows]
    scores=packed['model'].predict_proba(np.asarray(vectors))[:,1]
    ranking=[{'numero':h['numero'],'nom':h['nom'],'cheval_id':h['cheval_id'],
              'proba_podium_estimee':round(float(score),5)} for h,score in zip(rows,scores)]
    ranking.sort(key=lambda h:(-h['proba_podium_estimee'],h['numero']))
    base=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_ml_latest.json"
    old=load(base,{}) or {}
    if old.get('calcul_utc'):
        stamp=datetime.fromisoformat(old['calcul_utc']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        archive=base.parent/'versions'/f"{course['date']}_{course['code']}_ml_{stamp}.json"
        if not archive.exists():save(archive,old)
    save(base,{'date':course['date'],'course':course['code'],'calcul_utc':now.isoformat(),
               'depart':course['depart'],'modele':packed['modele'],'statut':'ML_ENTRAINE_NON_CALIBRE',
               'top3':ranking[:3],'classement_complet':ranking,
               'note':'Score non calibre; cotes exclues des variables.'})
    return 'ML_CALCULE'


def predict(cache,course,manifest=None,now=None):
    """Compatibilite anciens appelants : relire exclusivement le profil PMU."""
    doc=load(Path(cache)/'partants_actuels'/f"{course['date']}_{course['code']}.json",{}) or {}
    raw={'participants':[{'numPmu':int(n),'nom':h.get('nom',''),'age':h.get('age_ans'),
        'gainsCarriere':h.get('gains_euros'),'sexe':h.get('sexe'),
        'ferrure':h.get('ferrure'),'musique':h.get('musique_pmu'),
        'statut':h.get('statut_np')} for n,h in doc.get('chevaux',{}).items()]}
    return predict_pmu(cache,course,raw,now)


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
