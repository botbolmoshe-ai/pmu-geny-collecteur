"""Découverte prudente des 14 partants d'une course Geny.

Ne fabrique jamais d'identifiants de chevaux. En cas de doute : diagnostic + arrêt.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright
from .collecte_geny_v4 import dismiss_consent

PROGRAMME = 'https://www.geny.com/programme/2026-11-09/orga/PMU'
COURSE_NAME = 'caliceo'
HORSE_RE = re.compile(r'/cheval/(\d+)-([^/?#]+)(?:/course/(\d+))?', re.I)
COURSE_RE = re.compile(r'/course/(\d+)-([^/?#]+)', re.I)


def course_candidates(anchors: list[dict], keyword: str) -> list[dict]:
    out=[]
    for a in anchors:
        url=a.get('href') or ''
        m=COURSE_RE.search(url)
        if m and keyword in (m.group(2)+' '+a.get('text','')).lower():
            out.append({'url': url, 'id':m.group(1)})
    return list({x['url']:x for x in out}.values())


def horse_candidates(anchors: list[dict], race_id: str) -> tuple[list[dict],list[dict]]:
    """La sécurité prime : ne retenir que les liens rattachés à la course sélectionnée."""
    exact={}; other={}
    for a in anchors:
        link=a.get('href') or ''
        m=HORSE_RE.search(link)
        if not m: continue
        ident, slug, embedded_race_id=m.groups()
        name=(a.get('text') or '').strip() or slug.replace('-',' ').title()
        row={'id': ident, 'nom':name, 'url_geny':link}
        if embedded_race_id == race_id:
            exact[ident]=row
        else:
            other[ident]=row
    return list(exact.values()),list(other.values())


def links(page):
    return page.locator('a[href]').evaluate_all('els => els.map(a => ({href:a.href, text:(a.innerText||a.getAttribute("title")||"").trim()}))')


def produire_manifest(race_url: str, programme: str, attendu: int, output: Path, diagnostic: Path) -> dict:
    diagnostic.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(locale='fr-FR', timezone_id='Europe/Paris',viewport={'width':1366,'height':900})
        page=context.new_page()
        try:
            if not race_url:
                page.goto(programme,wait_until='domcontentloaded',timeout=45000)
                dismiss_consent(page)
                page.wait_for_timeout(1200)
                candidates=course_candidates(links(page),COURSE_NAME)
                (diagnostic/'liens_courses.json').write_text(json.dumps(links(page),ensure_ascii=False,indent=2),encoding='utf-8')
                if len(candidates)!=1:
                    raise RuntimeError(f'Découverte course ambiguë : {len(candidates)} lien(s) Caliceo, voir liens_courses.json. Fournir course_url explicitement.')
                race_url=candidates[0]['url']
            parsed=urlparse(race_url)
            m=COURSE_RE.search(parsed.path)
            if parsed.hostname not in {'geny.com','www.geny.com'} or not m:
                raise ValueError('URL de course Geny invalide')
            course_id=m.group(1)
            response=page.goto(race_url,wait_until='domcontentloaded',timeout=45000)
            print('Course Geny:',race_url,'HTTP:',response.status if response else '?',flush=True)
            dismiss_consent(page)
            page.wait_for_timeout(1800)
            for _ in range(5):
                page.mouse.wheel(0,1200)
                page.wait_for_timeout(250)
            anchors=links(page)
            (diagnostic/'liens_fiche_course.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2),encoding='utf-8')
            page.screenshot(path=str(diagnostic/'fiche_course.png'),full_page=True)
            exact, other=horse_candidates(anchors,course_id)
            print(f'Liens chevaux rattachés à la course : {len(exact)}, autres liens : {len(other)}, attendu : {attendu}',flush=True)
            if len(exact)!=attendu:
                raise RuntimeError(f'Partants non vérifiés ({len(exact)}/{attendu}). Arrêt avant collecte. Examiner fiche_course.png et liens_fiche_course.json.')
            data={'courses':[{'course_id':'2026-11-09-BORDEAUX-R1C4','source_course_geny':race_url,'nombre_partants_attendu':attendu,'partants':exact}]}
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            return data
        finally:
            context.close();browser.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--course-url',default='')
    ap.add_argument('--programme',default=PROGRAMME)
    ap.add_argument('--attendu',type=int,default=14)
    ap.add_argument('--manifest',default='resultats/partants_decouverts.json')
    ap.add_argument('--diagnostic',default='resultats/decouverte')
    args=ap.parse_args()
    manifest=produire_manifest(args.course_url,args.programme,args.attendu,Path(args.manifest),Path(args.diagnostic))
    print('Manifest prêt :',args.manifest,'(',len(manifest['courses'][0]['partants']),'partants )',flush=True)

if __name__=='__main__':main()
