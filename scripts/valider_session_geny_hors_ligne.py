from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
from playwright.sync_api import sync_playwright
from pmu_geny.historique_individuel import resolve
from pmu_geny.extraction_historique_par_cheval import extraire_cheval

course='https://www.geny.com/course/1698061/partants-pronostics'
horse='https://www.geny.com/cheval/123456-test'
race='<html><body><button>Refuser</button><table><tr><td>1</td><td></td><td><a href="'+horse+'">Test</a></td><td>Partant</td></tr></table></body></html>'
career='<html><body><h1>Test</h1><div>CARRIÈRE</div><div>sur 2 courses</div>'+''.join('<div>'+c+'</div>' for c in ['06/11/2026','Vincennes','Attelé','2 700','D','21 000 €','1','e'])+'</body></html>'
with TemporaryDirectory() as tmp, sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 ctx=browser.new_context(locale='fr-FR',timezone_id='Europe/Paris');requests=[]
 def route(r):
  requests.append(r.request.url)
  if r.request.url==course:
   r.fulfill(status=200,body=race,content_type='text/html; charset=utf-8',headers={'Set-Cookie':'continuite=oui; Path=/; Secure'})
  elif r.request.url==horse:
   assert 'continuite=oui' in r.request.headers.get('cookie',''), 'session perdue'
   r.fulfill(status=200,body=career,content_type='text/html; charset=utf-8')
  else:r.abort()
 ctx.route('**/*',route)
 page=ctx.new_page()
 with patch('pmu_geny.historique_individuel.dismiss_consent',return_value='REFUSE'):
  geny=resolve({'nom':'Test','numero':'1','course_url':course},Path(tmp),page)
 page.wait_for_load_state('domcontentloaded')
 result=extraire_cheval(geny['url_geny'],geny['id'],Path(tmp),page=page,page_chargee=False,http_status=None)
 assert [url for url in requests if url in (course,horse)]==[course,horse],requests
 assert result['nombre_extrait']==1 and not result['complet'],result
 print('VALIDATION_NAVIGATEUR',json.dumps({'navigations':len(requests),'fiche_cheval_chargee_une_fois':True,'cookie_session_conserve':True,'performances_valides':result['nombre_extrait'],'carriere_complete':result['complet']},ensure_ascii=False))
 browser.close()
