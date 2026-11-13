"""Sous-processus neuf : resoudre puis extraire UN cheval de la file."""
import argparse,json,re,sys,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pmu_geny.extraction_historique_par_cheval import extraire_cheval
from pmu_geny.controle_historique import classifier
from pmu_geny.liaison_chevaux_v22 import nom_normalise
from pmu_geny.decouverte_partants import get_rows,participants_from_rows,try_direct_url
from pmu_geny.collecte_geny_v4 import diagnostic_acces,dismiss_consent

def cliquer_nom(cell,nom):
    # Le nom est le controle interactif ; le centre du td peut etre une zone vide.
    target=cell.get_by_text(nom,exact=True)
    if target.count()!=1:raise ValueError('NOM_CLIQUABLE_AMBIGU')
    target.click(timeout=8000)

def attendre_partant(page,horse,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        rows=participants_from_rows(get_rows(page))
        matched=[r for r in rows if nom_normalise(r['nom'])==nom_normalise(horse['nom']) and r['numero']==horse['numero']]
        if matched:return matched
        page.wait_for_timeout(500)
    return []

def resolve(horse,out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            ctx=browser.new_context(locale='fr-FR',timezone_id='Europe/Paris');page=ctx.new_page()
            for url in horse['course_urls']:
                response=page.goto(url,wait_until='domcontentloaded',timeout=45000)
                verdict=diagnostic_acces(response.status if response else None,page.title(),page.locator('body').inner_text(),page.content())
                if verdict in ('ACCES_LIMITE_429','ACCES_REFUSE_403'):raise RuntimeError(verdict)
                if response and response.status!=200:continue
                expected=re.search(r'/course/(\d+)',url)
                actual=re.search(r'/course/(\d+)',page.url)
                if not expected or not actual or expected[1]!=actual[1]:continue
                dismiss_consent(page)
                matched=attendre_partant(page,horse)
                if len(matched)!=1:continue
                index=matched[0]['row_index'];direct=try_direct_url(page,index)
                if not direct:
                    before=page.url;pages=set(ctx.pages)
                    cliquer_nom(page.locator('tr').nth(index).locator('td').nth(2),matched[0]['nom'])
                    for _ in range(30):
                        new=[x for x in ctx.pages if x not in pages]
                        if new or page.url!=before:
                            direct=new[-1].url if new else page.url
                            if '/cheval/' in direct:break
                        page.wait_for_timeout(250)
                m=re.search(r'/cheval/(\d+)',direct or '')
                if m and urlparse(direct).hostname in ('geny.com','www.geny.com'):
                    return {'id':m[1],'nom':horse['nom'],'url_geny':direct.replace('https://geny.com/','https://www.geny.com/')}
            (out/'diagnostic_resolution.html').write_text(page.content(),encoding='utf-8')
            (out/'diagnostic_resolution_lignes.json').write_text(json.dumps(get_rows(page),ensure_ascii=False,indent=2))
            raise ValueError('FICHE_EXACTE_NON_IDENTIFIEE')
        finally:browser.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cle',required=True);args=parser.parse_args()
    state=json.loads((ROOT/'collecte_unitaire/etat.json').read_text());horse=state['chevaux'][args.cle]
    out=ROOT/'resultats/boucle'/args.cle/str(horse['tentatives']);out.mkdir(parents=True,exist_ok=True)
    report={'nom':horse['nom'],'debut_utc':datetime.now(timezone.utc).isoformat(),'complet':False}
    try:
        geny=horse.get('geny') or resolve(horse,out)
        if not horse.get('geny'):time.sleep(30)
        result=extraire_cheval(geny['url_geny'],geny['id'],out)
        status,reasons=classifier(result);folder=out/geny['id']
        text=(folder/'diagnostic_texte_geny.txt').read_text(encoding='utf-8') if (folder/'diagnostic_texte_geny.txt').exists() else ''
        identity=nom_normalise(horse['nom']) in nom_normalise(text[:6000])
        report.update(geny=geny,statut=status,motifs=reasons,identite_verifiee=identity,
                      complet=status=='COMPLET' and identity,nombre_extrait=result.get('nombre_extrait',0),dossier=str(folder))
        if (folder/'controle_acces.json').exists():report['acces']=json.loads((folder/'controle_acces.json').read_text())
    except Exception as exc:
        report.update(statut='ACCES_LIMITE_429' if '429' in str(exc) else 'ACCES_REFUSE_403' if '403' in str(exc) else 'ERREUR',erreur=f'{type(exc).__name__}: {exc}')
    report['fin_utc']=datetime.now(timezone.utc).isoformat()
    path=ROOT/'collecte_unitaire/dernier_resultat.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('RESULTAT_UN_CHEVAL '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
