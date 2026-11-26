"""Découverte Geny depuis les preuves contenues dans la page des partants.

Pilote défensif : valide la course, le nombre de partants, l'unicité des numéros,
les URLs /cheval/{ID} et n'écrit le manifeste que si tout est vérifié.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit
from playwright.sync_api import sync_playwright
from .collecte_geny_v4 import dismiss_consent, diagnostic_acces

PROGRAMME = 'https://www.geny.com/programme/2026-11-10/orga/PMU'
COURSE_NAME = 'prix-des-tulipes'
COURSE_RE = re.compile(r'/course/(\d+)(?:-([^/?#]+))?', re.I)


def write_json(file: Path, obj):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def links(page):
    return page.locator('a[href]').evaluate_all('els => els.map(a => ({href:a.href, text:(a.innerText||a.getAttribute("title")||"").trim()}))')


def race_candidates(anchors, keyword):
    found = {}
    for a in anchors:
        href = a.get('href') or ''
        m = COURSE_RE.search(urlparse(href).path)
        if m and keyword.casefold() in ((m.group(2) or '') + ' ' + a.get('text', '')).casefold():
            found.setdefault(m.group(1), []).append(href)
    return {k: list(dict.fromkeys(v)) for k, v in found.items()}


def candidate_urls(urls):
    out = []
    for url in sorted(urls, key=lambda x: ('partants' not in x.lower(), x)):
        parsed = urlsplit(url)
        root = re.search(r'(/course/\d+(?:-[^/]+)?)', parsed.path)
        if not root:
            continue
        base = urlunsplit((parsed.scheme, parsed.netloc, root.group(1), '', ''))
        for candidate in (url, base + '/partants-pronostics', base + '/partants-pronos'):
            if candidate not in out:
                out.append(candidate)
    return out


def get_rows(page):
    """Lit les tr HTML sans supposer que le nom est un href.

    Les lignes sont reconnues par : premier texte = numéro, au moins 4 cellules,
    troisième cellule = nom; vérifications de l'absence de doublon ensuite.
    """
    return page.locator('tr').evaluate_all('''rows => rows.map((tr, index) => {
        const cells = Array.from(tr.querySelectorAll(':scope > td'));
        const tidy = s => (s || '').replace(/\\s+/g, ' ').trim();
        return {index, cells: cells.map(c=>tidy(c.innerText)),
                html: tr.outerHTML.slice(0, 1800)};
    }).filter(r => r.cells.length >= 4 && /^\\d{1,2}$/.test(r.cells[0])
               && r.cells[2] && /[A-Za-zÀ-ÿ]/.test(r.cells[2]))''')


def participants_from_rows(rows):
    found = []
    for row in rows:
        number = int(row['cells'][0])
        if number < 1 or number > 30:
            continue
        name = row['cells'][2].strip()
        # Un intitulé comportant plusieurs lignes est suspect : éviter les tables parasites.
        if not name or len(name) > 90:
            continue
        found.append({'numero': number, 'nom': name, 'row_index': row['index']})
    return found


def extract_partants(page, race_id, attendu, diagnostic):
    from .liens_geny_course import extraire
    from .liaison_chevaux_v22 import nom_geny_concordant

    rows = get_rows(page)
    write_json(diagnostic / 'lignes_tableau.json', rows)
    partants = participants_from_rows(rows)
    if sorted(horse['numero'] for horse in partants) != list(range(1, attendu + 1)):
        raise RuntimeError(f'Tableau des partants ambigu : {len(partants)} lignes, attendu {attendu}')
    proof = extraire(rows, page.content(), None, page.url, datetime.now(timezone.utc).isoformat())
    if proof.get('course_geny_id') != race_id:
        raise RuntimeError('Course finale Geny non concordante')
    result = []
    for horse in partants:
        number = horse['numero']
        link = proof.get('chevaux', {}).get(str(number))
        if not link or not nom_geny_concordant(horse['nom'], link):
            raise RuntimeError(f'Fiche cheval non identifiée pour n°{number} {horse["nom"]}')
        result.append({'id': link['id'], 'numero': number, 'nom': horse['nom'], 'url_geny': link['url_geny']})
    if len({p['id'] for p in result}) != attendu:
        raise RuntimeError('Identifiants de chevaux en doublon : extraction refusee')
    return result


def produire_manifest(race_url, programme, attendu, output, diagnostic, keyword, etat_path=None):
    from .historique_individuel import ignorer_ressource

    diagnostic.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale='fr-FR', timezone_id='Europe/Paris', viewport={'width':1366,'height':900})
        ctx.route('**/*', ignorer_ressource)
        page = ctx.new_page()
        try:
            if race_url:
                parsed = urlparse(race_url)
                m = COURSE_RE.search(parsed.path)
                if parsed.hostname not in ('www.geny.com', 'geny.com') or not m:
                    raise ValueError('URL de course invalide')
                race_id, urls = m.group(1), [race_url]
            else:
                response = page.goto(programme, wait_until='domcontentloaded', timeout=45000)
                print('Programme Geny HTTP:', response.status if response else '?', flush=True)
                dismiss_consent(page)
                anchors = links(page)
                write_json(diagnostic/'liens_programme.json', anchors)
                candidates = race_candidates(anchors, keyword)
                print('Identifiants courses candidates:', list(candidates), flush=True)
                if len(candidates) != 1:
                    raise RuntimeError(f'Selection ambiguë : {len(candidates)} courses pour {keyword}')
                race_id, urls = next(iter(candidates.items()))
            attempts=[]
            for attempt_number, url in enumerate(candidate_urls(urls), 1):
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                status = response.status if response else None
                # Lire la page actuelle AVANT d'agir sur la CMP ou de chercher
                # des partants. Evite les autres tentatives si refus 403/429.
                verdict = diagnostic_acces(status, page.title(), page.locator("body").inner_text(), page.content())
                if verdict in ("ACCES_LIMITE_429", "ACCES_REFUSE_403"):
                    write_json(diagnostic / "blocage_decouverte.json", {"url": url, "verdict": verdict, "http": status})
                    if etat_path:
                        state = {}
                        if etat_path.exists():
                            try:
                                state = json.loads(etat_path.read_text(encoding='utf-8'))
                            except (ValueError, OSError):
                                state = {}
                        if not isinstance(state, dict):
                            state = {}
                        state.setdefault('version', 1)
                        state.setdefault('chevaux', {})
                        state['dernier_blocage_geny'] = {'utc': datetime.now(timezone.utc).isoformat(), 'code': '403' if verdict.endswith('403') else '429'}
                        write_json(etat_path, state)
                    raise RuntimeError(f"Geny refuse la decouverte : {verdict}; aucune nouvelle requete de decouverte")
                dismiss_consent(page)
                page.wait_for_timeout(1200)
                anchors = links(page)
                write_json(diagnostic/f'liens_tentative_{attempt_number}.json', anchors)
                page.screenshot(path=str(diagnostic/f'fiche_tentative_{attempt_number}.png'), full_page=True)
                rows = get_rows(page)
                attempts.append({'url': url, 'http': status, 'lignes_partants_candidates': len(rows)})
                write_json(diagnostic/'tentatives.json', attempts)
                print(f'Tentative {attempt_number}: HTTP {status}, lignes candidates {len(rows)}/{attendu}', flush=True)
                if status != 200 or len(rows) != attendu:
                    continue
                horses = extract_partants(page, race_id, attendu, diagnostic)
                output_data = {'courses': [{'course_id': f'GENY-{race_id}', 'source_course_geny': url,
                                            'nombre_partants_attendu': attendu, 'partants': horses}]}
                write_json(output, output_data)
                print(f'MANIFEST VALIDE : {len(horses)}/{attendu} chevaux', flush=True)
                return output_data
            raise RuntimeError(f'Impossible de confirmer {attendu} partants. Voir diagnostics.')
        finally:
            ctx.close()
            browser.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--course-url', default='')
    ap.add_argument('--programme', default=PROGRAMME)
    ap.add_argument('--mot-cle', default=COURSE_NAME)
    ap.add_argument('--attendu', type=int, default=14)
    ap.add_argument('--manifest', default='resultats/partants_decouverts.json')
    ap.add_argument('--diagnostic', default='resultats/decouverte')
    ap.add_argument('--etat', default='cache_pmu/etat_persistant.json')
    args=ap.parse_args()
    if args.attendu < 1:
        ap.error('--attendu >= 1')
    produire_manifest(args.course_url,args.programme,args.attendu,Path(args.manifest),Path(args.diagnostic),args.mot_cle,Path(args.etat))

if __name__=='__main__':
    main()
