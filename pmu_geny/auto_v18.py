"""V18: orchestration horaire prudente sur sources PMU et Geny.

Le PMU fournit le programme et les statuts NP seulement si le schéma est reconnu.
Geny reste optionnel et soumis à sa politique de refus/cooldown. Aucune
prévision ni arrivée n'est inventée quand les données sont indisponibles.
"""
from __future__ import annotations
import argparse, json, os, re, sys, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from zoneinfo import ZoneInfo
from .export_v17 import exporter
from .traitement_course import traiter

PARIS=ZoneInfo('Europe/Paris')
BASE='https://online.turfinfo.api.pmu.fr/rest/client/1/programme/'

def save(path, doc):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def load(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError): return default

def get_json(url, timeout=16):
    if not url.startswith(BASE): raise ValueError('Endpoint PMU non autorisé')
    req=Request(url,headers={'Accept':'application/json','User-Agent':'PMU-research-v18/1.0'})
    with urlopen(req,timeout=timeout) as response:
        if response.status!=200: raise RuntimeError(f'PMU_HTTP_{response.status}')
        body=response.read(5_000_001)
        if len(body)>5_000_000: raise RuntimeError('Réponse trop volumineuse')
        result=json.loads(body)
        if not isinstance(result,(dict,list)): raise ValueError('Format JSON PMU incompatible')
        return result

def _list(doc, *names):
    if isinstance(doc,list):return doc
    for name in names:
        x=doc.get(name)
        if isinstance(x,list):return x
    return []

def _num(doc,*fields):
    for field in fields:
        value=doc.get(field)
        if value is not None:
            try: return int(value)
            except (ValueError,TypeError): pass
    return None

def _str(doc,*fields):
    for field in fields:
        v=doc.get(field)
        if isinstance(v,str) and v.strip():return v.strip()
    return ''

def programme(doc, date):
    reunions=_list(doc,'programme','reunions')
    if not reunions and isinstance(doc,dict):
        reunions=_list(doc.get('programme',{}),'reunions') if isinstance(doc.get('programme'),dict) else []
    if not reunions: raise ValueError('Programme PMU non reconnu : aucune réunion')
    output=[]
    for r in reunions:
        if not isinstance(r,dict):continue
        numero_reunion=_num(r,'numOfficiel','numeroReunion','numReunion')
        hip=r.get('hippodrome') or {}
        country=_str(hip,'pays','codePays') if isinstance(hip,dict) else ''
        # Seules les réunions françaises CERTAINES sont prises en charge.
        if country.upper() not in ('FRA','FR','FRANCE'): continue
        hp=_str(hip,'libelleLong','libelleCourt','nom') if isinstance(hip,dict) else str(hip)
        for c in _list(r,'courses'):
            if not isinstance(c,dict):continue
            no=_num(c,'numOrdre','numeroCourse','numCourse')
            if no is None or numero_reunion is None:continue
            depart=c.get('heureDepart') or c.get('heureDepartEstimee')
            if not isinstance(depart,(int,float)):continue
            instant=datetime.fromtimestamp(depart/1000 if depart>10**11 else depart, tz=timezone.utc).astimezone(PARIS)
            if instant.date().isoformat()!=date:continue
            nb=_num(c,'nombreDeclaresPartants','nombrePartants','nbPartants')
            if not nb or not 1<=nb<=30:continue
            output.append({'date':date,'code':f'R{numero_reunion}C{no}','hippodrome':hp,'nom':_str(c,'libelle','nomCourse'),
                           'depart':instant.isoformat(),'nombre_declares':nb,'num_reunion':numero_reunion,'num_course':no,
                           'distance_m':_num(c,'distance','distanceMetres','distanceCourse'),
                           'discipline':_str(c,'discipline','typeCourse')})
    return sorted(output,key=lambda x:x['depart'])

def normalize(s):
    s=unicodedata.normalize('NFD',s.casefold());s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]+','-',s).strip('-')

def np_participants(doc, manifest):
    """Ne confirme zéro NP que si la liste complète, ses numéros et ses drapeaux sont interprétables."""
    entries=_list(doc,'participants','partants')
    if not entries: raise ValueError('Liste PMU absente')
    horses=manifest['courses'][0]['partants']
    expected={int(h['numero']) for h in horses}
    mapping={}
    for item in entries:
        if not isinstance(item,dict):raise ValueError('Participant PMU invalide')
        n=_num(item,'numPmu','num','numero','numeroPmu')
        if n in mapping or n is None: raise ValueError('Numéros PMU ambigus')
        explicit=item.get('nonPartant',None)
        if isinstance(explicit,bool): np=explicit
        elif isinstance(explicit,str) and explicit.lower() in ('true','false'):np=explicit.lower()=='true'
        elif str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):np=True
        elif str(item.get('statut','')).upper() in ('PARTANT',):np=False
        else:raise ValueError('Indicateur NP absent ou inconnu sur un participant')
        mapping[n]=np
    if set(mapping)!=expected: raise ValueError(f'Liste PMU incomplète/incohérente: {len(mapping)}/{len(expected)}')
    return mapping

def update_np(cache, course, manifest, pmu_data):
    mapped=np_participants(pmu_data,manifest)
    cid=manifest['courses'][0]['course_id']; target=cache/'participations'/f'{cid}.json'
    previous=load(target,{}) or {}; old={x['numero']:x for x in previous.get('chevaux',[])}
    now=datetime.now(timezone.utc).isoformat(); rows=[]
    for p in manifest['courses'][0]['partants']:
        n=int(p['numero']); statut='NON_PARTANT' if mapped[n] else 'PARTANT'
        rows.append({'numero':n,'cheval_id':str(p['id']),'nom':p['nom'],'statut_participation':statut,
                     'source_np':'PMU_API','date_verification_np':now})
    doc={'course_id':cid,'source_reference':'PMU','source_url':f"{BASE}{course['date'].replace('-','')}",
         'date_controle_utc':now,'liste_complete_verifiee':True,'chevaux':rows,
         'historique_modifications':previous.get('historique_modifications',[])+[{'utc':now,'numero':r['numero'],'ancien':old.get(r['numero'],{}).get('statut_participation','NP_NON_VERIFIE'),
                                       'nouveau':r['statut_participation']} for r in rows if old.get(r['numero'],{}).get('statut_participation')!=r['statut_participation']]}
    save(target,doc);return doc

def run(cache:Path, date:str, selection:list[str], max_new:int, phase:str='auto', max_discoveries:int=2, now=None):
    now=now or datetime.now(PARIS)
    if now.tzinfo is None: raise ValueError("Heure de traitement sans fuseau")
    index=cache/'orchestration'/f'{date}.json'; state=load(index,{'date':date,'courses':{},'alertes':[]})
    # Conservateur : absence PMU ≠ absence de NP.
    try:
        pmu=get_json(BASE+datetime.fromisoformat(date).strftime('%d%m%Y'))
        courses=programme(pmu,date)
        save(cache/'sources_pmu'/f'programme_{date}.json',{'date_controle_utc':datetime.now(timezone.utc).isoformat(),'programme':courses})
        state['source_programme']='PMU_API';state['dernier_controle_pmu']=datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        state['alertes'].append(f'Programme PMU indisponible: {type(exc).__name__}: {exc}')
        courses=(load(cache/'sources_pmu'/f'programme_{date}.json',{}) or {}).get('programme',[])
    # Une course déjà partie n'entre JAMAIS en prédiction/collecte.
    # Les courses récentes peuvent seulement passer par la phase arrivées/audit.
    # Le lendemain est préparé dès 18 h (heure de Paris), sans trafic nocturne.
    from .planification_v20_2 import selectionner_courses
    selected=selectionner_courses(courses, now, date, selection, max_new>0,
                                state, max_courses=12)
    remaining_new=max_new
    remaining_discoveries=max_discoveries
    correspondences_path=cache/'orchestration'/'correspondances_geny.json'
    correspondences=load(correspondences_path,{}) or {}
    geny_state=load(cache/'etat_persistant.json',{}) or {}
    last=(geny_state.get('dernier_blocage_geny') or {}).get('utc')
    try: cooldown=bool(last and datetime.now(timezone.utc)<datetime.fromisoformat(last)+timedelta(hours=1))
    except (ValueError,TypeError): cooldown=False
    for c in selected:
        key=c['code']; entry=state['courses'].setdefault(key,{'identifiant_geny':None,'etat':'A_DECOUVRIR'})
        entry.update({'depart':c['depart'],'nom':c['nom'],'hippodrome':c['hippodrome'],'nombre_declares':c['nombre_declares']})
        departure=datetime.fromisoformat(c['depart'])
        est_partie=now>=departure
        # Aucune prévision rétroactive, même si PMU n'a pas encore communiqué le statut.
        if est_partie:
            entry['traitement']='RESULTATS_SEULEMENT'
            if (cache/'arrivees'/f"{date}_{key}.json").exists() and entry.get('audit_predictif') in ('AUDIT_ENREGISTRE','AUDIT_DEJA_ENREGISTRE'):
                entry['etat']='TERMINE_ARCHIVE'
                continue
        else:
            entry['traitement']='PREPARATION_AVANT_DEPART'
        # Météo sourcée indépendante de Geny et des statuts NP : même sans manifeste.
        if not est_partie:
            try:
                from .contexte_meteo_v20 import collecter_meteo
                entry['statut_meteo']=collecter_meteo(cache,c)
            except Exception as exc:
                entry['statut_meteo']='METEO_NON_VERIFIEE'
                entry['erreur_meteo']=f'{type(exc).__name__}: {exc}'
        # Pas de consultation Geny sur une course terminée.
        manifest=None; manifest_path=None
        for f in (cache/'manifestes').glob('GENY-*.json') if (cache/'manifestes').exists() else []:
            m=load(f,{})
            if not m or not m.get('courses'):continue
            block=m['courses'][0]
            match=correspondences.get(f'{date}_{key}')==block.get('course_id')
            if not match:
                # Retrocompatibilité V16/V17: même date et même intitulé exact dans l'URL Geny.
                u=block.get('source_course_geny','')
                match=bool(date in u and normalize(c['nom']) and normalize(c['nom']) in normalize(u))
                if match:
                    correspondences[f'{date}_{key}']=block['course_id']
                    save(correspondences_path,correspondences)
            if match:
                manifest,manifest_path=m,f;break
        # Correspondance explicite PMU RnCn -> Geny : jamais sur le seul numéro de course.
        if manifest is None and not cooldown and remaining_discoveries>0 and not est_partie:
            # Rechercher une course par son NOM dans le programme Geny du jour.
            # Le collecteur refuse une correspondance ambiguë.
            try:
                from .decouverte_partants import produire_manifest
                from .collecte_geny_v4 import diagnostic_acces
                keyword=normalize(c['nom'])
                if not keyword: raise ValueError('Nom de course PMU vide')
                # Limite de découvertes par exécution pour ne pas saturer Geny.
                remaining_discoveries-=1
                temp=cache/'orchestration'/'decouvertes'/f'{date}_{key}.json'
                data=produire_manifest('',f'https://www.geny.com/programme/{date}/orga/PMU',
                         c['nombre_declares'],temp,cache/'diagnostics'/'decouverte'/f'{date}_{key}',keyword,
                         cache/'etat_persistant.json')
                block=data['courses'][0]
                # Interdire la liaison si le nom ne figure pas dans l'URL Geny.
                url=block.get('source_course_geny','')
                if keyword not in normalize(url):
                    raise ValueError('Geny: correspondance nom non confirmée')
                manifest_path=cache/'manifestes'/f"{block['course_id']}.json"
                save(manifest_path,data)
                manifest=data
                correspondences[f'{date}_{key}']=block['course_id']
                save(correspondences_path,correspondences)
                entry['etat']='DECOUVERT'
            except Exception as exc:
                entry['erreur_decouverte']=f'{type(exc).__name__}: {exc}'
                geny_state=load(cache/'etat_persistant.json',{}) or {}
                if (geny_state.get('dernier_blocage_geny') or {}).get('utc'): cooldown=True
        if manifest is None:
            entry['etat']='GENY_NON_ASSOCIE'
            continue
        entry['identifiant_geny']=manifest['courses'][0]['course_id'];entry['etat']='MANIFESTE_PRESENT'
        if phase in ('auto','collecter') and not est_partie and remaining_new>0 and not cooldown:
            try:
                result=traiter(manifest,cache/'diagnostics',remaining_new,cache/'etat_persistant.json',cooldown_heures=1)
                # Le nombre réellement ouvert sera enregistré par le traitement.
                # 1 course par cycle en collecte lourde ; les autres conservent leur manifeste.
                remaining_new=0
                geny_state=load(cache/'etat_persistant.json',{}) or {}
                if (geny_state.get('dernier_blocage_geny') or {}).get('utc'): cooldown=True
            except Exception as exc:entry['erreur_collecte']=str(exc)
        raw=None
        # La veille, ne pas saturer PMU en consultant les participants de toutes
        # les courses: les controles NP recommencent le jour J.
        verifier_participants=est_partie or (departure-now)<=timedelta(hours=6)
        try:
            if not verifier_participants: raise LookupError('CONTROLE_NP_DIFFERE_JUSQU_A_H6')
            raw=get_json(BASE+datetime.fromisoformat(date).strftime('%d%m%Y')+f"/{key[:key.index('C')]}/{key[key.index('C'):]}/participants")
            # Une course passée ne reçoit plus de nouvelles vérifications NP.
            # Les données brutes servent uniquement à confirmer l'arrivée.
            if not est_partie:
                info=update_np(cache,c,manifest,raw)
                entry['np_confirmes']=sum(x['statut_participation']=='NON_PARTANT' for x in info['chevaux'])
                entry['np_verification_utc']=info['date_controle_utc']
        except Exception as exc:
            if isinstance(exc,LookupError): entry['statut_np']='CONTROLE_DIFFERE'
            else: entry['erreur_np']=f'{type(exc).__name__}: {exc}'
        if est_partie and raw is not None:
            try:
                from .resultats_v18 import enregistrer_resultats
                entry['statut_arrivee']=enregistrer_resultats(cache,c,raw)
            except (NameError,ValueError,TypeError) as exc:
                entry['statut_arrivee']='ARRIVEE_NON_VERIFIEE'
                entry['erreur_arrivee']=str(exc)
        # Cotes: derniers instantanes AVANT le depart seulement, jamais variables ML.
        if raw is not None and not est_partie:
            try:
                from .cotes_v19 import collecter
                entry['statut_cotes']=collecter(cache,c,raw)
            except Exception as exc:entry['erreur_cotes']=f'{type(exc).__name__}: {exc}'
        if not est_partie:
            try:
                from .pronostics_v18 import preparer_top3, actualiser_top3_np
                entry['statut_prevision']=preparer_top3(cache,c,manifest)
                entry['statut_maj_np']=actualiser_top3_np(cache,c,manifest)
            except Exception as exc:
                entry['statut_prevision']='ERREUR_MODELE_PROVISOIRE'
                entry['erreur_prevision']=str(exc)
            try:
                from .ml_v19 import snapshot, predict
                # Instantane H-1:15...H-1, pas de donnees post-course.
                delay=(departure-now).total_seconds()/60
                if 60<=delay<=75:
                    entry['statut_snapshot_ml']=snapshot(cache,c,manifest)
                entry['statut_ml']=predict(cache,c,manifest)
            except Exception as exc:entry['erreur_ml']=f'{type(exc).__name__}: {exc}'
        try:
            exporter(manifest,cache,cache/'exports')
            from .ml_v19 import export_comparatif
            entry['comparatif_csv']=str(export_comparatif(cache,c,manifest))
            from .audit_predictif_v20_1 import analyser_course, bilan_global
            entry['audit_predictif']=analyser_course(cache,c,manifest)
            if entry['audit_predictif']=='AUDIT_ENREGISTRE':
                entry['bilan_audits_csv']=bilan_global(cache)
        except Exception as exc:entry['erreur_export']=str(exc)
    if now.hour==20 and now.minute<15:
        try:
            from .ml_v19 import train
            state['entrainement_ml']=train(cache)
        except Exception as exc:state['alertes'].append(f'ENTRAINEMENT_ML: {type(exc).__name__}: {exc}')
    state['fiches_geny_budget_consommees']=max_new-remaining_new
    save(index,state)
    print(json.dumps({'date':date,'courses_pmu':len(courses),'courses_selectionnees':len(selected),
                      'manifestes_associes':sum(e.get('identifiant_geny') is not None for e in state['courses'].values()),
                      'alertes':state['alertes'][-3:]},ensure_ascii=False))
    return state

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',default='cache_pmu');p.add_argument('--date',default='')
    p.add_argument('--courses',default='',help='Ex R2C8,R1C4; vide = toutes');p.add_argument('--max-nouvelles-fiches',type=int,default=3)
    p.add_argument('--max-decouvertes',type=int,default=2)
    a=p.parse_args();date=a.date or datetime.now(PARIS).date().isoformat()
    if a.max_nouvelles_fiches<0 or a.max_nouvelles_fiches>30:p.error('Nombre de fiches invalide')
    run(Path(a.cache),date,[x.strip().upper() for x in a.courses.split(',') if x.strip()],a.max_nouvelles_fiches,max_discoveries=a.max_decouvertes)
if __name__=='__main__':main()
