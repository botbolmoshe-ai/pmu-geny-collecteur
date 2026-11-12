"""Rejeu hors reseau : archives avant depart + scenarios de quota avec extracteur simule."""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import types
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bs4 import BeautifulSoup
from pmu_geny import auto_v18
from pmu_geny.top3_independants_v22 import _form_score
from pmu_geny.sync_google_sheets import source_rows, limiter_cours_registre
from pmu_geny.sources_experts_v23 import same_race
from pmu_geny.liaison_chevaux_v22 import nom_normalise

BASELINE='2c854d56c515cc7d1c1e091e70522e55806d323e'

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def legacy(path,ref=BASELINE):
    m=types.ModuleType('pmu_geny._simulation_ancienne')
    m.__package__='pmu_geny'
    exec(subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT,text=True),m.__dict__)
    return m

def rejouer_musique(cache):
    old=legacy('pmu_geny/top3_independants_v22.py')
    programme={c['code']:c for c in load(cache/'sources_pmu/programme_2026-11-12.json')['programme']}
    rows=[]
    for p in sorted((cache/'avis_experts/pages_v23').glob('*.json')):
        d=load(p);match=re.fullmatch(r'https://www.equidia.fr/courses/2026-11-12/(R\d+)/(C\d+)',d.get('url',''))
        if not match or not d.get('html'):continue
        code=''.join(match.groups());course=programme.get(code)
        if not course or datetime.fromisoformat(d['capture_utc'])>=datetime.fromisoformat(course['depart']):continue
        tag=BeautifulSoup(d['html'],'html.parser').find('script',id='serverApp-state')
        state=json.loads(tag.get_text());race=state.get('v2/courses/2026-11-12/'+match[1]+'/'+match[2],{})
        reunion=race.get('reunion') or {}
        if not same_race(course,reunion.get('date_reunion'),reunion.get('lib_reunion'),race.get('liblong_prix_course','')):continue
        # Identites verifiees sur le registre ; aucun rang d'arrivee ou cote extrait de la page.
        pmu=load(cache/'partants_actuels'/('2026-11-12_'+code+'.json'))['chevaux']
        eligible=0;rankings=[[],[]]
        for h in race.get('partants',[]):
            n=int(h['num_partant']);name=h.get('cheval',{}).get('nom_cheval','')
            if nom_normalise(name)!=nom_normalise(pmu.get(str(n),{}).get('nom')):raise ValueError('Identite non confirmee')
            if h.get('statut_part')=='NP':continue
            eligible+=1
            value=h.get('musique') or h.get('cheval',{}).get('musique')
            for ranking,score_fn in zip(rankings,[old._form_score,_form_score]):
                score=score_fn({'musique':value})
                if score is not None:ranking.append((score,n))
        arrival=load(cache/'arrivees'/('2026-11-12_'+code+'.json'))
        podium={int(h['numero']) for h in arrival['arrivee'] if h['rang'] in (1,2,3)}
        row={'course':code,'discipline':course['discipline'],'capture_utc':d['capture_utc'],
             'source_url':d['url'],'sha256_archive':hashlib.sha256(p.read_bytes()).hexdigest(),'eligibles':eligible}
        for label,rank in zip(['avant','apres'],rankings):
            selected=[n for s,n in sorted(rank,key=lambda x:(-x[0],x[1]))[:3]]
            row['classes_'+label]=len(rank);row['top3_'+label]=selected
            row['hits_'+label]=len(set(selected)&podium) if len(selected)==3 else None
        rows.append(row)
    return sorted(rows,key=lambda x:x['course'])

def scenario_quota(cache, optimised, kind):
    module=auto_v18 if optimised else legacy('pmu_geny/auto_v18.py')
    template=next(load(p) for p in sorted((cache/'historiques').glob('*/historique_geny.json')) if load(p).get('statut')=='COMPLET')
    now=datetime(2026,11,12,10,tzinfo=timezone.utc);calls=[]
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        courses=[];parts={};mapping={};journal={}
        for c,size in [(1,3),(2,6)]:
            code=f'R1C{c}';cid=f'GENY-SIMULATION-{c}'
            horses=[{'numero':n,'id':str(990000+c*100+n),'nom':f'SIMULATION_{c}_{n}',
                     'url_geny':f'https://www.geny.com/cheval/{990000+c*100+n}-simulation'} for n in range(1,size+1)]
            write(root/'manifestes'/f'{cid}.json',{'courses':[{'course_id':cid,'nombre_partants_attendu':size,'partants':horses}]})
            courses.append({'date':'2026-11-12','code':code,'depart':(now+timedelta(minutes=65+c*5)).isoformat(),
                            'nombre_declares':size,'hippodrome':'Vincennes','nom':'SCENARIO_SIMULE'})
            mapping['2026-11-12_'+code]=cid
            parts[code]={'participants':[{'numPmu':h['numero'],'nom':h['nom'],'nonPartant':False} for h in horses]}
            if c==1 and kind=='premiere_course_en_cache':
                for h in horses:
                    write(root/'historiques'/h['id']/'historique_geny.json',template)
                    journal[h['id']]={'statut':'COMPLET','nom':h['nom'],'nombre_extrait':template['nombre_extrait']}
        write(root/'etat_persistant.json',{'version':1,'chevaux':journal})
        write(root/'orchestration/correspondances_geny.json',mapping)
        def get_json(url):
            m=re.search(r'/(R\d+)/(C\d+)/participants',url)
            return parts[''.join(m.groups())] if m else {}
        def extract(url,ident,dest):
            calls.append(ident)
            if kind=='refus_429':return {'statut':'ACCES_LIMITE_429','nombre_extrait':0}
            write(dest/ident/'historique_geny.json',template)
            return template
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch('socket.socket.connect',side_effect=AssertionError('Acces reseau interdit en simulation')))
            stack.enter_context(patch.object(module,'get_json',side_effect=get_json))
            stack.enter_context(patch.object(module,'programme_diagnostic',return_value=(courses,{'courses_retenues':2})))
            stack.enter_context(patch('pmu_geny.traitement_course.extraire_cheval',side_effect=extract))
            stack.enter_context(patch('pmu_geny.traitement_course.time.sleep',return_value=None))
            for name in ['pmu_geny.contexte_meteo_v20.collecter_meteo','pmu_geny.partants_actuels_v21.enregistrer',
                         'pmu_geny.sources_experts_v23.collecter','pmu_geny.top3_independants_v22.calculer',
                         'pmu_geny.cotes_v19.collecter','pmu_geny.ml_v19.snapshot_pmu','pmu_geny.ml_v19.snapshot',
                         'pmu_geny.ml_v19.predict','pmu_geny.pronostics_v18.preparer_top3',
                         'pmu_geny.pronostics_v18.actualiser_top3_np','pmu_geny.ml_v19.export_comparatif',
                         'pmu_geny.audit_predictif_v20_1.analyser_course']:
                stack.enter_context(patch(name,return_value='SIMULATION_TECHNIQUE'))
            stack.enter_context(patch.object(module,'exporter',return_value=None))
            with contextlib.redirect_stdout(io.StringIO()):
                result=module.run(root,'2026-11-12',[],6,max_discoveries=0,now=now)
        return {'tentatives_simulees':len(calls),'quota_annonce_consomme':result['fiches_geny_budget_consommees'],
                'nouveaux_historiques_simules':0 if kind=='refus_429' else len(calls),
                'courses_servies':len({ident[0:-2] for ident in calls}),
                'arret_429_respecte':len(calls)<=1 if kind=='refus_429' else None}

def etat_couverture(cache):
    data=limiter_cours_registre(source_rows(cache))['Courses & Prévisions']
    fields=['driver_jockey','entraineur','age_ans','sexe','gains_euros','ferrure','top3_direct_rang','top3_cotes_valeur','ml_rang','arrivee_rang']
    counts={f:sum(r.get(f) is not None and str(r.get(f)).strip()!='' for r in data.values()) for f in fields}
    rows=[]
    for key,row in sorted(data.items()):
        np=row.get('non_partant')=='NON_PARTANT';rank=row.get('top3_direct_rang')
        race_key=f"{row['date_course']}_{row['rncn']}"
        arrival_path=cache/'arrivees'/f'{race_key}.json'
        rows.append({'course_key':row['course_key'],'numero':row['numero'],'cheval':row['cheval'],
                     'rang_direct':rank or ('NON_PARTANT' if np else 'NON_CALCULE'),
                     'selection_top3':'NON_PARTANT' if np else 'OUI' if rank and int(rank)<=3 else 'NON' if rank else 'NON_CALCULE',
                     'historique':row.get('historique_statut'),
                     'performances':row.get('historique_nb_courses_datees') or 0,
                     'cause_rang_absent':'' if rank else 'NON_PARTANT' if np else 'MUSIQUE_ABSENTE_INVALIDE_OU_ANCIEN_PARSEUR',
                     'cause_historique_absent':'PAS_DE_FICHIER_ASSOCIE' if row.get('historique_statut')=='HISTO_NON_COLLECTE' else '',
                     'cause_cote_absente':'' if row.get('top3_cotes_valeur') else 'AUCUNE_COTE_EXTRAITE',
                     'cause_ml_absent':'' if row.get('ml_rang') else row.get('ml_modele_statut','ML_NON_ENTRAINE'),
                     'cause_arrivee_absente':'' if row.get('arrivee_rang') else 'AUCUN_RANG_POSITIF_DANS_ARRIVEE' if arrival_path.exists() else 'ARRIVEE_PAS_ENCORE_ENREGISTREE',
                     'champs_absents':','.join(f for f in fields if row.get(f) is None or str(row.get(f)).strip()=='')})
    return {'participations':len(rows),'champs_renseignes':counts,
            'historiques_lies':sum(str(r.get('historique_statut','')).startswith('HISTO_OK') for r in data.values()),
            'non_partants':sum(r['selection_top3']=='NON_PARTANT' for r in rows),'lignes':rows}

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,default=ROOT/'reference_pmu');p.add_argument('--sortie',type=Path,default=ROOT/'resultats/simulation_v25');a=p.parse_args()
    if a.sortie.resolve().is_relative_to(a.cache.resolve()):raise ValueError('Les rapports doivent rester hors du cache de reference')
    before={str(p.relative_to(a.cache)):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.cache.rglob('*') if p.is_file()}
    music=rejouer_musique(a.cache)
    scenarios={k:{label:scenario_quota(a.cache,opt,k) for label,opt in [('avant',False),('optimise',True)]} for k in ['premiere_course_en_cache','premiere_course_a_completer','refus_429']}
    coverage=etat_couverture(a.cache)
    rows=coverage.pop('lignes')
    previous=legacy('pmu_geny/sync_google_sheets.py','c50b077e2a642e5bdbd627fc4601488d9de097ae')
    before_rows=limiter_cours_registre(previous.source_rows(a.cache))['Courses & Prévisions']
    coverage['arrivees_renseignees_avant']=sum(bool(r.get('arrivee_rang')) for r in before_rows.values())
    coverage['selections_renseignees_avant']=sum(bool(r.get('top3_direct_top3')) for r in before_rows.values())
    coverage['selections_renseignees_apres']=sum(bool(r.get('top3_direct_top3')) for r in limiter_cours_registre(source_rows(a.cache))['Courses & Prévisions'].values())
    summary={'date_utc':datetime.now(timezone.utc).isoformat(),'mode':'SIMULATION_HORS_RESEAU',
             'baseline_git':BASELINE,'regle':'Archives Equidia horodatees avant depart ; scenarios quota synthetiques distincts des donnees reelles.',
             'musique':{'courses':len(music),'eligibles':sum(x['eligibles'] for x in music),
                        **{f:sum(x[f] or 0 for x in music) for f in ['classes_avant','classes_apres','hits_avant','hits_apres']},'details':music},
             'scenarios_quota':scenarios,'couverture_reelle':coverage}
    after={str(p.relative_to(a.cache)):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.cache.rglob('*') if p.is_file()}
    assert before==after,'La reference a ete modifiee'
    summary['reference_inchangee']=True
    write(a.sortie/'simulation.json',summary)
    with (a.sortie/'donnees_manquantes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps({k:v if k!='musique' else {f:x for f,x in v.items() if f!='details'} for k,v in summary.items()},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
