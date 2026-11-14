"""Rattrapage à inventaire figé, sans fenêtre de courses ni moteur de collecte parallèle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from . import historiques_incrementaux as inc
from .liaison_chevaux_v22 import nom_normalise

QUEUE=Path('rattrapage_historiques/etat.json')
INVENTAIRE=QUEUE.parent/'inventaire_sheets.json'


def url_cheval(url,ident):
    parsed=urlparse(str(url or ''))
    match=re.match(r'/cheval/(\d+)(?:\D|$)',parsed.path)
    return parsed.scheme=='https' and parsed.hostname in ('geny.com','www.geny.com') and bool(match and match[1]==ident)


def url_course(url):
    parsed=urlparse(str(url or ''))
    return parsed.scheme=='https' and parsed.hostname in ('geny.com','www.geny.com') and bool(re.match(r'/course/\d+',parsed.path))


def inventaire_local(cache,sheets):
    """Toutes les dates, NP inclus ; un nom ambigu n'est pas un identifiant."""
    cache=Path(cache);records=[]
    journal=inc.lire(cache/'etat_persistant.json',{'chevaux':{}})['chevaux']
    for ident,meta in journal.items():
        doc=inc.lire(cache/'historiques'/str(ident)/'historique_geny.json')
        records.append({'id':str(ident),'nom':meta.get('nom',''),'url_geny':doc.get('source_url',''),
                        'origine':'JOURNAL'})
    for file in sorted((cache/'historiques').glob('*/historique_geny.json')):
        doc=inc.lire(file);ident=file.parent.name
        records.append({'id':ident,'nom':journal.get(ident,{}).get('nom') or doc.get('nom',''),
                        'url_geny':doc.get('source_url',''),'origine':'CAPTURE'})
    for file in sorted((cache/'manifestes').glob('*.json')):
        for course in inc.lire(file).get('courses',[]):
            for h in course.get('partants',[]):
                records.append({**h,'id':str(h.get('id','')),
                    'course_url':course.get('source_course_geny',''),'origine':'MANIFESTE:'+file.stem})
    from .sync_google_sheets import read_csv
    for name in ('partants.csv','performances.csv'):
        for file in sorted((cache/'exports').glob('GENY-*/'+name)):
            for h in read_csv(file):
                records.append({'id':str(h.get('cheval_id','')),'nom':h.get('nom',''),
                    'numero':h.get('numero',''),'origine':'EXPORT:'+file.parent.name})
    for key,h in inc.lire(cache/inc.QUEUE,{'chevaux':{}})['chevaux'].items():
        records.append({**h,'url_geny':h.get('geny',{}).get('url_geny',''),
                        'origine':'FILE_PRODUCTION:'+key})
    correspondence=inc.lire(cache/'orchestration/correspondances_geny.json')
    for file in sorted((cache/'partants_actuels').glob('????-??-??_R*C*.json')):
        day,code=file.stem.split('_',1)
        course=inc.lire(cache/'orchestration'/f'{day}.json').get('courses',{}).get(code,{})
        cid=correspondence.get(file.stem,'')
        if not cid:
            cid=course.get('identifiant_geny','')
            mapping=course.get('rapprochement_geny',{})
            if not cid and mapping.get('statut')=='CORRESPONDANCE_CONFIRMEE':
                cid='GENY-'+str(mapping.get('geny_id',''))
        if not cid:
            # Réutiliser l'index déjà observé, y compris pour les anciennes courses.
            from .rapprochement_v20_6 import rapprocher
            index=inc.lire(cache/'sources_geny'/f'index_{day}.json')
            rc=re.fullmatch(r'R(\d+)C(\d+)',code)
            if index.get('statut')=='OK' and rc:
                decision=rapprocher({**course,'date':day,'num_reunion':int(rc[1]),
                                     'num_course':int(rc[2])},index.get('courses',[]))
                if decision.get('statut')=='CORRESPONDANCE_CONFIRMEE':
                    cid='GENY-'+str(decision['geny_id'])
        course_url='https://www.geny.com/course/'+cid[5:]+'/partants-pronostics' if re.fullmatch(r'GENY-\d+',str(cid)) else ''
        for number,h in inc.lire(file).get('chevaux',{}).items():
            records.append({'nom':h.get('nom',''),'numero':str(number),'engagement':file.stem,
                            'course_url':course_url,'origine':'PMU:'+file.stem})
    records.extend(sheets.get('chevaux',[]))
    by_id={};unknown=[]
    def merge(target,record):
        name=record.get('nom','')
        if name and target.get('nom') and nom_normalise(name)!=nom_normalise(target['nom']):
            target['conflit_identite']=True
        if name and not target.get('nom'):target['nom']=name
        target.setdefault('origines',[])
        origin=record.get('origine','')
        if origin and origin not in target['origines']:target['origines'].append(origin)
        ident=target.get('id','')
        url=record.get('url_geny') or record.get('geny',{}).get('url_geny','')
        if ident and url_cheval(url,ident):
            target['geny']={'id':ident,'nom':target.get('nom',''),
                            'url_geny':url.replace('https://geny.com/','https://www.geny.com/')}
        if url_course(record.get('course_url')) and record.get('numero'):
            target.update(course_url=record['course_url'],numero=str(record['numero']))
        if record.get('engagement'):target['engagement']=record['engagement']
        if record.get('prochain_essai_utc'):target['prochain_essai_utc']=record['prochain_essai_utc']
    for record in records:
        ident=str(record.get('id',''))
        if re.fullmatch(r'\d{4,15}',ident):
            merge(by_id.setdefault(ident,{'id':ident,'nom':''}),record)
        elif record.get('nom'):unknown.append(record)
    names={}
    for ident,h in by_id.items():
        if h.get('nom') and not h.get('conflit_identite'):
            names.setdefault(nom_normalise(h['nom']),set()).add(ident)
    targets=dict(by_id)
    for record in unknown:
        ids=names.get(nom_normalise(record['nom']),set())
        if len(ids)==1:
            merge(targets[next(iter(ids))],record)
        else:
            # Les contextes non identifiés ne sont pas fusionnés sur le seul nom.
            signature='|'.join((nom_normalise(record['nom']),str(record.get('engagement','')),str(record.get('numero',''))))
            key='contexte:'+hashlib.sha256(signature.encode()).hexdigest()[:24]
            merge(targets.setdefault(key,{'nom':record['nom']}),record)
    return targets


def preparer(cache,now):
    cache=Path(cache)
    sheets=inc.lire(cache/INVENTAIRE)
    if not sheets.get('capture_utc') or not isinstance(sheets.get('chevaux'),list):
        raise ValueError('INVENTAIRE_SHEETS_REQUIS')
    state=inc.lire(cache/QUEUE)
    if state and (state.get('version')!=1 or not isinstance(state.get('chevaux'),dict)):
        raise ValueError('FILE_RATTRAPAGE_INCOMPATIBLE')
    if not state:
        targets=inventaire_local(cache,sheets)
        if not targets:raise ValueError('INVENTAIRE_VIDE')
        state={'version':1,'mode':'RATTRAPAGE_GLOBAL','inventaire_utc':now.isoformat(),
            'inventaire_id':hashlib.sha256((now.isoformat()+'\n'+'\n'.join(sorted(targets))).encode()).hexdigest()[:24],
            'chevaux':targets,'sync_kpi':'A_REPRENDRE',
            'lignes_historique_initiales':sheets.get('lignes_historique')}
    local=inventaire_local(cache,sheets)
    # Le dénominateur est figé. La production peut néanmoins avoir complété une cible.
    journal=inc.lire(cache/'etat_persistant.json',{'chevaux':{}})['chevaux']
    names={}
    for ident,h in journal.items():names.setdefault(nom_normalise(h.get('nom')),set()).add(str(ident))
    covered=set(sheets.get('ids_couverts',[]))
    for key,h in state['chevaux'].items():
        h.setdefault('sync','SANS_MODIFICATION')
        if h.get('rattrapage_complet_au_utc'):continue
        if not h.get('id'):
            ids=names.get(nom_normalise(h.get('nom')),set())
            if len(ids)==1:h['id']=next(iter(ids))
        fresh=local.get(h.get('id')) or local.get(key) or {}
        if nom_normalise(fresh.get('nom'))==nom_normalise(h.get('nom')):
            for field in ('geny','course_url','numero','conflit_identite'):
                if fresh.get(field):h[field]=fresh[field]
        ident=h.get('id','');doc=inc.capture_valide(cache,ident) if ident else None
        stamp=inc.instant(doc.get('extrait_utc')) if doc else None
        if h.get('conflit_identite') or not h.get('nom'):
            h.update(collecte='IDENTITE_A_VERIFIER',motif_actualisation='IDENTITE_A_VERIFIER')
            continue
        if doc and url_cheval(doc.get('source_url'),ident):
            h['geny']={'id':ident,'nom':h['nom'],
                       'url_geny':doc['source_url'].replace('https://geny.com/','https://www.geny.com/')}
        if (stamp and stamp<=now and h.get('geny') and url_cheval(doc.get('source_url'),ident)
                and str(doc.get('identifiant_cheval',ident))==ident):
            h.update(collecte='COMPLET',nombre_performances=len(doc['performances']),
                     historique_complet_au_utc=stamp.isoformat(),motif_actualisation='')
            if ident in covered or not doc['performances']:
                h.update(sync='OK',rattrapage_complet_au_utc=stamp.isoformat(),
                         preuve_sync='INVENTAIRE_SHEETS_CONTROLE',complete_depuis_sauvegarde=True)
            else:h['sync']='A_FAIRE'
        else:
            h.update(collecte='A_REPRENDRE',motif_actualisation='HISTORIQUE_ABSENT_PARTIEL_OU_NON_DATE')
            if not h.get('geny') and not (url_course(h.get('course_url')) and h.get('numero')):
                h['collecte']='LIEN_GENY_A_RESOUDRE'
    bilan(state)
    return state


def prochaine_tache(state,now,attempts):
    # Une publication en échec est reprise sans nouvelle consultation Geny.
    for key,h in state['chevaux'].items():
        if h.get('sync')=='A_FAIRE' and attempts.get(('SYNC',key),0)<1:
            retry=inc.instant(h.get('prochaine_sync_utc'))
            if not retry or retry<=now:return key,'SYNC'
    cooldown=inc.instant(state.get('prochain_acces_geny_utc'))
    if cooldown and cooldown>now:return None,'COOLDOWN'
    candidates=[]
    for key,h in state['chevaux'].items():
        if h.get('rattrapage_complet_au_utc') or not h.get('motif_actualisation'):continue
        if h.get('collecte') in ('LIEN_GENY_A_RESOUDRE','IDENTITE_A_VERIFIER'):continue
        retry=inc.instant(h.get('prochain_essai_utc'))
        if attempts.get(('COLLECTE',key),0) or retry and retry>now:continue
        candidates.append(((not bool(h.get('geny')),h.get('engagement',''),key),key))
    return (min(candidates)[1],'COLLECTE') if candidates else (None,'TERMINE_PASSAGE')


def valider_sync(state,horse):
    stamp=horse.get('historique_complet_au_utc')
    if not inc.instant(stamp):raise ValueError('CAPTURE_NON_DATEE')
    horse.update(rattrapage_complet_au_utc=stamp,motif_actualisation='')
    horse['ajouts_confirmes']=horse.get('ajouts_confirmes',0)+horse.get('sync_details',{}).get('Historique chevaux',{}).get('lignes_ajoutees',0)
    # Les contextes répétés d'une identité désormais vérifiée partagent la preuve.
    for other in state['chevaux'].values():
        if other is horse or other.get('conflit_identite'):continue
        if other.get('id')==horse['id'] and nom_normalise(other.get('nom'))==nom_normalise(horse['nom']):
            other.update(rattrapage_complet_au_utc=stamp,sync='OK',motif_actualisation='',
                         historique_complet_au_utc=stamp,preuve_sync='MEME_IDENTIFIANT_VERIFIE')


def bilan(state):
    horses=list(state['chevaux'].values())
    complete=sum(bool(h.get('rattrapage_complet_au_utc')) and h.get('sync')=='OK' for h in horses)
    previous=state.get('bilan',{})
    state['bilan']={'cibles_inventoriees':len(horses),'cibles_completees':complete,
        'cibles_restantes':len(horses)-complete,
        'identifiants_geny_distincts':len({h['id'] for h in horses if h.get('id')}),
        'identites_non_resolues':sum(not h.get('id') for h in horses),
        'liens_a_resoudre':sum(h.get('collecte')=='LIEN_GENY_A_RESOUDRE' for h in horses),
        'identites_a_verifier':sum(h.get('collecte')=='IDENTITE_A_VERIFIER' for h in horses),
        'synchronisations_en_attente':sum(h.get('sync')=='A_FAIRE' for h in horses),
        'ajouts_confirmes':sum(h.get('ajouts_confirmes',0) for h in horses),
        'tentatives_collecte':previous.get('tentatives_collecte',0)}
    state['statut']='TERMINE' if complete==len(horses) and state.get('sync_kpi')=='OK' else 'PARTIEL_REPRENABLE'
    if state['statut']=='TERMINE' and not state.get('termine_utc'):
        state['termine_utc']=datetime.now(inc.UTC).isoformat()
    return state['bilan']


def priorite_production():
    """Céder entre deux chevaux si un workflow de production attend le verrou."""
    if os.getenv('GITHUB_ACTIONS')!='true':return None
    repo=os.environ.get('GITHUB_REPOSITORY','')
    token=os.environ.get('GH_TOKEN','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or not token:
        return 'PRIORITE_PRODUCTION_NON_VERIFIABLE'
    import requests
    try:
        response=requests.get(f'https://api.github.com/repos/{repo}/actions/runs',
            params={'status':'pending','per_page':100},
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},timeout=15)
        response.raise_for_status()
        paths={'.github/workflows/pmu-v16.yml','.github/workflows/historiques-incrementaux.yml'}
        if any(run.get('path') in paths for run in response.json()['workflow_runs']):
            return 'PRIORITE_PRODUCTION_EN_ATTENTE'
    except Exception:
        return 'PRIORITE_PRODUCTION_NON_VERIFIABLE'
    return None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',default='cache_pmu')
    parser.add_argument('--max-minutes',type=int,default=10)
    parser.add_argument('--max-chevaux',type=int,default=1000)
    parser.add_argument('--publier',action='store_true')
    args=parser.parse_args()
    if not 1<=args.max_minutes<=15 or args.max_chevaux<1:parser.error('Bornes positives, duree maximale 15 minutes')
    cache=Path(args.cache)
    if args.publier:
        if not all(os.environ.get(k) for k in ('GOOGLE_SHEETS_ID','GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON')):
            raise SystemExit('Secrets Sheets absents : aucune collecte lancee')
        from .moteur_sheets import SynchroniseurSheets
        engine=SynchroniseurSheets(cache,os.environ['GOOGLE_SHEETS_ID'])
        try:inc.ecrire(cache/INVENTAIRE,engine.inventaire_rattrapage())
        finally:engine.fermer()
        state=inc.run(cache,max_minutes=args.max_minutes,max_chevaux=args.max_chevaux,
                      publier=True,mode='rattrapage',stop_requested=priorite_production)
    else:
        state=preparer(cache,datetime.now(inc.UTC))
    print('BILAN_RATTRAPAGE '+json.dumps({'statut':state['statut'],'inventaire_id':state['inventaire_id'],
                                       'motif_fin_passage':state.get('motif_fin_passage','BUDGET_OU_FILE_EPUISE'),
                                       **state['bilan']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
