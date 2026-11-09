"""Pilote d'une course à venir : choisir l'URL Partants/Pronos du programme Geny.
Ne jamais reconstruire une URL canonique de course; journaliser chaque tentative.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit
from playwright.sync_api import sync_playwright
from .collecte_geny_v4 import dismiss_consent

PROGRAMME = 'https://www.geny.com/programme/2026-11-10/orga/PMU'
COURSE_NAME = 'prix-des-tulipes'  # Vincennes R2C1, 14 partants au programme Geny
HORSE_RE = re.compile(r'/cheval/(\d+)-([^/?#]+)(?:/course/(\d+))?', re.I)
COURSE_RE = re.compile(r'/course/(\d+)-([^/?#]+)', re.I)

def links(page):
    return page.locator('a[href]').evaluate_all('els => els.map(a => ({href:a.href, text:(a.innerText||a.getAttribute("title")||"").trim()}))')

def unique_urls_for_race(anchors, keyword):
    by_id = {}
    for a in anchors:
        u = a.get('href') or ''
        m = COURSE_RE.search(urlparse(u).path)
        if not m or keyword.casefold() not in (m.group(2)+' '+a.get('text','')).casefold():
            continue
        by_id.setdefault(m.group(1), []).append(u)
    return {ident: list(dict.fromkeys(urls)) for ident, urls in by_id.items()}

def candidate_urls(urls):
    """Essayer d'abord l'URL exacte (potentiellement /partants-pronos), puis la rubrique explicite."""
    chosen=[]
    for u in sorted(urls, key=lambda x: ('partants' not in x.lower(), 'pronos' not in x.lower())):
        parsed=urlsplit(u)
        root=re.search(r'(/course/\d+-[^/]+)', parsed.path)
        if not root: continue
        base=urlunsplit((parsed.scheme,parsed.netloc,root.group(1),'',''))
        for item in (u,base+'/partants-pronos'):
            if item not in chosen: chosen.append(item)
    return chosen

def get_horses(anchors, race_id):
    exact={}; other={}
    for a in anchors:
        url=a.get('href') or ''
        m=HORSE_RE.search(urlparse(url).path)
        if not m: continue
        horse_id, slug, linked_race=m.groups()
        horse={'id':horse_id,'nom':(a.get('text') or '').strip() or slug.replace('-',' ').title(),'url_geny':url}
        if linked_race == race_id: exact[horse_id]=horse
        else: other[horse_id]=horse
    return list(exact.values()),list(other.values())

def produire_manifest(race_url, programme, attendu, output, diagnostic, keyword):
    diagnostic.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        ctx=browser.new_context(locale='fr-FR',timezone_id='Europe/Paris',viewport={'width':1366,'height':900})
        page=ctx.new_page()
        try:
            if race_url:
                m=COURSE_RE.search(urlparse(race_url).path)
                if urlparse(race_url).hostname not in ('www.geny.com','geny.com') or not m:
                    raise ValueError('URL de course invalide')
                race_id=m.group(1)
                urls=[race_url]
            else:
                resp=page.goto(programme,wait_until='domcontentloaded',timeout=45000)
                print('Programme Geny HTTP:',resp.status if resp else '?',flush=True)
                dismiss_consent(page)
                anchors=links(page)
                (diagnostic/'liens_programme.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2),encoding='utf-8')
                found=unique_urls_for_race(anchors,keyword)
                print('Identifiants courses candidates:',list(found),flush=True)
                if len(found)!=1:
                    raise RuntimeError(f'Sélection ambiguë : {len(found)} courses pour {keyword}. Diagnostic liens_programme.json')
                race_id,urls=next(iter(found.items()))
            attempts=[]
            for u in candidate_urls(urls):
                resp=page.goto(u,wait_until='domcontentloaded',timeout=45000)
                status=resp.status if resp else None
                dismiss_consent(page)
                page.wait_for_timeout(1000)
                anchors=links(page)
                exact,other=get_horses(anchors,race_id)
                attempts.append({'url':u,'http':status,'chevaux_lies':len(exact),'autres_liens':len(other)})
                (diagnostic/f'liens_tentative_{len(attempts)}.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2),encoding='utf-8')
                page.screenshot(path=str(diagnostic/f'fiche_tentative_{len(attempts)}.png'),full_page=True)
                print(f'Tentative {len(attempts)} : HTTP {status} ; chevaux {len(exact)}/{attendu} ; URL {u}',flush=True)
                if status == 200 and len(exact)==attendu:
                    data={'courses':[{'course_id':f'GENY-{race_id}','source_course_geny':u,'nombre_partants_attendu':attendu,'partants':exact}]}
                    output.parent.mkdir(parents=True,exist_ok=True)
                    output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                    (diagnostic/'tentatives.json').write_text(json.dumps(attempts,ensure_ascii=False,indent=2),encoding='utf-8')
                    return data
            (diagnostic/'tentatives.json').write_text(json.dumps(attempts,ensure_ascii=False,indent=2),encoding='utf-8')
            raise RuntimeError(f'Impossible de vérifier {attendu} partants rattachés à la course Geny {race_id}. Voir les diagnostics. Aucune extraction lancée.')
        finally:
            ctx.close();browser.close()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--course-url',default='')
    ap.add_argument('--programme',default=PROGRAMME)
    ap.add_argument('--mot-cle',default=COURSE_NAME)
    ap.add_argument('--attendu',type=int,default=14)
    ap.add_argument('--manifest',default='resultats/partants_decouverts.json')
    ap.add_argument('--diagnostic',default='resultats/decouverte')
    args=ap.parse_args()
    if args.attendu<1: ap.error('--attendu >= 1')
    manifest=produire_manifest(args.course_url,args.programme,args.attendu,Path(args.manifest),Path(args.diagnostic),args.mot_cle)
    print('MANIFEST VALIDE',len(manifest['courses'][0]['partants']),'partants',flush=True)

if __name__=='__main__':main()
