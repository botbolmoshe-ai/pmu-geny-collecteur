"""Découverte Geny : tableau des partants sans liens href, ouverture des fiches au clic.

Pilote défensif : valide la course, le nombre de partants, l'unicité des numéros,
les URLs /cheval/{ID} et n'écrit le manifeste que si tout est vérifié.
"""
from __future__ import annotations
import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit
from playwright.sync_api import sync_playwright
from .collecte_geny_v4 import dismiss_consent, diagnostic_acces

PROGRAMME = 'https://www.geny.com/programme/2026-11-10/orga/PMU'
COURSE_NAME = 'prix-des-tulipes'
COURSE_RE = re.compile(r'/course/(\d+)(?:-([^/?#]+))?', re.I)
HORSE_RE = re.compile(r'/cheval/(\d+)(?:-([^/?#]+))?', re.I)


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

    Conserve l'index DOM de chaque ligne pour cliquer sur la même ligne ensuite.
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


def try_direct_url(page, row_index):
    return page.locator('tr').nth(row_index).evaluate('''tr => {
      const node = tr.querySelectorAll(':scope > td')[2];
      const a = node && node.closest('a[href]') || node && node.querySelector('a[href]');
      return a ? a.href : null;
    }''')


def click_get_horse_url(page, context, row_index, name, diagnostic, number):
    """Clique uniquement dans la cellule du nom et suit popup OU navigation locale.

    En cas d'ambiguïté, journalise et ne devine aucun identifiant.
    """
    before = page.url
    before_pages = set(context.pages)
    target = page.locator('tr').nth(row_index).locator('td').nth(2)
    try:
        # Le clic porte sur le nom plutôt que sur le bouton de pari voisin.
        matching = target.get_by_text(name, exact=True)
        if matching.count() == 1:
            matching.click(timeout=6500)
        else:
            target.click(timeout=6500)
    except Exception as exc:
        return None, 'clic impossible : ' + str(exc)[:240]
    new_pages = []
    for _ in range(15):
        page.wait_for_timeout(250)
        new_pages = [p for p in context.pages if p not in before_pages]
        if new_pages or page.url != before:
            break
    if new_pages:
        popup = new_pages[-1]
        try:
            popup.wait_for_load_state('domcontentloaded', timeout=12000)
        except Exception:
            pass
        url = popup.url
        write_json(diagnostic / f'clic_{number:02d}.json', {'nom': name, 'mode': 'nouvel_onglet', 'url': url})
        try:
            popup.close()
        except Exception:
            pass
        return url, 'nouvel_onglet'
    if page.url != before:
        url = page.url
        write_json(diagnostic / f'clic_{number:02d}.json', {'nom': name, 'mode': 'meme_onglet', 'url': url})
        try:
            page.go_back(wait_until='domcontentloaded', timeout=20000)
            page.wait_for_timeout(650)
        except Exception:
            pass
        return url, 'meme_onglet'
    write_json(diagnostic / f'clic_{number:02d}.json', {'nom': name, 'mode': 'aucune_navigation', 'url': page.url})
    return None, 'aucune_navigation'


def extract_partants(page, context, race_id, attendu, diagnostic):
    rows = get_rows(page)
    write_json(diagnostic / 'lignes_tableau.json', rows)
    partants = participants_from_rows(rows)
    # Exclure tableaux parasites si leurs numéros entrent en collision.
    numbers = [x['numero'] for x in partants]
    if len(partants) != attendu or len(numbers) != len(set(numbers)):
        raise RuntimeError(f'Tableau des partants ambigu : {len(partants)} lignes, {len(set(numbers))} numeros distincts, attendu {attendu}. Voir lignes_tableau.json')
    if sorted(numbers) != list(range(1, attendu + 1)):
        raise RuntimeError(f'Numeros partants incoherents : {numbers}')
    result = []
    for idx, horse in enumerate(partants, start=1):
        name, row_index = horse['nom'], horse['row_index']
        # Les lignes du DOM peuvent changer après retour arrière : les retrouver par numéro.
        now = participants_from_rows(get_rows(page))
        matching = [x for x in now if x['numero'] == horse['numero'] and x['nom'] == name]
        if len(matching) != 1:
            raise RuntimeError(f'Ligne introuvable apres navigation : {horse["numero"]} {name}')
        row_index = matching[0]['row_index']
        url = try_direct_url(page, row_index)
        how = 'lien_direct'
        if not url or not HORSE_RE.search(urlparse(url).path):
            url, how = click_get_horse_url(page, context, row_index, name, diagnostic, horse['numero'])
        m = HORSE_RE.search(urlparse(url or '').path)
        if not m:
            raise RuntimeError(f'Fiche cheval non identifiee pour n°{horse["numero"]} {name} ({how}, url={url!r}). Voir clic_{horse["numero"]:02d}.json')
        horse_id = m.group(1)
        if urlparse(url).hostname not in ('geny.com', 'www.geny.com'):
            raise RuntimeError(f'Domaine inattendu pour le cheval {name} : {url}')
        result.append({'id': horse_id, 'numero': horse['numero'], 'nom': name, 'url_geny': url})
        print(f'Partant {idx}/{attendu} : n°{horse["numero"]} {name} -> {horse_id} ({how})', flush=True)
        page.wait_for_timeout(350)
    if len({p['id'] for p in result}) != attendu:
        raise RuntimeError('Identifiants de chevaux en doublon : extraction refusee')
    return result


def produire_manifest(race_url, programme, attendu, output, diagnostic, keyword, etat_path=None):
    diagnostic.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale='fr-FR', timezone_id='Europe/Paris', viewport={'width':1366,'height':900})
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
                horses = extract_partants(page, ctx, race_id, attendu, diagnostic)
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
