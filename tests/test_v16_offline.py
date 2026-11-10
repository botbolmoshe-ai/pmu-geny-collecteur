import sys,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pmu_geny.traitement_course import traiter
from pmu_geny.collecte_geny_v4 import diagnostic_acces
assert diagnostic_acces(200,'Accès refusé - Geny','403\nAccès refusé',"dataLayer.push({ event: 'error_page', error_status: '403' });") == 'ACCES_REFUSE_403'
assert diagnostic_acces(200,'Trop de requêtes - Geny','429\nTrop de requêtes','') == 'ACCES_LIMITE_429'
manifest={'courses':[{'course_id':'GENY-1697377','nombre_partants_attendu':3,'partants':[{'id':str(1000+i),'nom':f'Cheval{i}','url_geny':f'https://www.geny.com/cheval/{1000+i}-test/course/1697377'} for i in range(3)]}]}
with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp); calls=[]
  def fake(url,ident,sortie):
    calls.append(ident)
    d=sortie/ident;d.mkdir(parents=True,exist_ok=True)
    res={'nombre_annonce_geny':1,'nombre_extrait':1,'performances':[{'date':'2026-10-11','hippodrome':'Vincennes','discipline':'Attelé','distance_m':'2700','classement':'6e'}],'statut':'COMPLET'}
    (d/'historique_geny.json').write_text(json.dumps(res))
    return res
  etat=root/'cache_pmu/etat_persistant.json'
  with patch('pmu_geny.traitement_course.extraire_cheval',side_effect=fake), patch('pmu_geny.traitement_course.time.sleep',lambda _:None):
    first=traiter(manifest,root/'sortie1',3,etat)
    second=traiter(manifest,root/'sortie2',3,etat)
  assert calls==['1000','1001','1002'],calls
  assert all(h['origine']=='CACHE_PERSISTANT' for h in second['courses'][0]['chevaux'])
  assert len(list((root/'cache_pmu/historiques').glob('*/historique_geny.json')))==3
  # 429 should cause no further calls and 24h gate next time
  state=json.loads(etat.read_text());state.pop('dernier_blocage_geny',None);state['chevaux'].pop('1002');(root/'cache_pmu/historiques/1002/historique_geny.json').unlink()
  etat.write_text(json.dumps(state))
  def limit(url,ident,sortie):
    calls.append(ident)
    return {'statut':'ACCES_LIMITE_429','nombre_extrait':0}
  with patch('pmu_geny.traitement_course.extraire_cheval',side_effect=limit), patch('pmu_geny.traitement_course.time.sleep',lambda _:None):
    blocked=traiter(manifest,root/'sortie3',3,etat)
    assert blocked['collecte_geny']=='SUSPENDUE_429'
    count=len(calls)
    later=traiter(manifest,root/'sortie4',3,etat)
    assert len(calls)==count
    assert later['collecte_geny']=='DIFFEREE_COOLDOWN'
print('Tests V16 : 403,429,3 complet, reprise 0 requete, blocage, cooldown OK')
