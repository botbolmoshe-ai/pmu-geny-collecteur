"""Extraction isolée issue du pilote c08feed, sans état global ni écriture Sheets."""
import argparse
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

from .extraction_historique_par_cheval import extraire_cheval
from .controle_historique import classifier
from .liaison_chevaux_v22 import nom_geny_concordant, nom_normalise, separer_pays_pmu
from .decouverte_partants import get_rows, participants_from_rows, try_direct_url
from .collecte_geny_v4 import diagnostic_acces, dismiss_consent


def cliquer_nom(cell, nom):
    target = cell.get_by_text(nom, exact=True)
    if target.count() != 1:
        raise LookupError('NOM_CLIQUABLE_AMBIGU')
    target.click(timeout=8000)


def candidats_recherche(html, nom):
    from .ferrures_geny import flux_next

    flux = flux_next(html)
    decoder = json.JSONDecoder()
    candidates = {}
    established = False
    for match in re.finditer(r'\{\s*"dehydratedAt"\s*:', flux):
        try:
            query, _ = decoder.raw_decode(flux, match.start())
        except ValueError:
            continue
        key = query.get('queryKey')
        if not isinstance(key, list) or len(key) != 2 or key[0] != 'recherche':
            continue
        if nom_normalise(key[1]) != nom_normalise(nom):
            continue
        state = query.get('state', {})
        results = state.get('data')
        if state.get('status') != 'success' or not isinstance(results, list):
            continue
        established = True
        for item in results:
            title = str(item.get('titre') or '')
            link = re.fullmatch(r'cheval/(\d{4,15})', str(item.get('urlV2') or ''))
            if item.get('type') == 'CHEVAL' and title.startswith('Fiche cheval - ') and link:
                name = title.removeprefix('Fiche cheval - ').strip()
                if nom_normalise(name) == nom_normalise(nom):
                    summary = str(item.get('resume') or '')
                    age = re.search(r'\bâge\s*:\s*(\d+)\s+ans?\b', summary)
                    country = re.search(r'\bpays\s*:\s*([^,]+)', summary, re.I)
                    iso = {'SUEDE': 'SE', 'ITALIE': 'IT'}.get(nom_normalise(country[1])) if country else None
                    candidates[link[1]] = {'id': link[1], 'nom': name, 'age_geny': int(age[1]) if age else None,
                                           'nationalite_geny': iso,
                                           'url_geny': 'https://www.geny.com/cheval/'+link[1]}
    if not established:
        raise ValueError('RECHERCHE_GENY_NON_INTERPRETABLE')
    return candidates


def rechercher(horse, page):
    name, country = separer_pays_pmu(horse['nom'])
    url = 'https://www.geny.com/recherche?'+urlencode({'q': name})
    response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
    html = page.content()
    verdict = diagnostic_acces(response.status if response else None, page.title(),
                               page.locator('body').inner_text(), html)
    if verdict in ('ACCES_LIMITE_429', 'ACCES_REFUSE_403'):
        raise RuntimeError(verdict)
    target = urlparse(page.url)
    if (not response or response.status != 200 or target.scheme != 'https'
            or target.hostname not in ('geny.com', 'www.geny.com') or target.path.rstrip('/') != '/recherche'):
        raise ValueError('RECHERCHE_GENY_INDISPONIBLE')
    try:
        candidates = candidats_recherche(html, name)
    except ValueError as exc:
        if horse.get('course_url') and horse.get('numero') and str(exc) == 'RECHERCHE_GENY_NON_INTERPRETABLE':
            return None
        raise
    if country:
        candidates = {ident: {**fiche, 'nom_pmu': horse['nom']} for ident, fiche in candidates.items()
                      if nom_geny_concordant(horse['nom'], fiche)}
    if len(candidates) == 1 and horse.get('rapprochement_geny') != 'NOM_AMBIGU':
        return {**next(iter(candidates.values())), 'preuve': 'RECHERCHE_GENY_NOM_EXACT'}
    year = horse.get('annee_naissance_pmu')
    if len(candidates) > 1 and year and all(h['age_geny'] is not None for h in candidates.values()):
        current = datetime.now(ZoneInfo('Europe/Paris')).year
        same_year = [h for h in candidates.values() if current - h['age_geny'] == year]
        if len(same_year) == 1:
            return {**same_year[0], 'preuve': 'RECHERCHE_GENY_NOM_EXACT',
                    'homonymes': list(candidates.values()), 'annee_naissance_pmu': year}
    if not horse.get('course_url') or not horse.get('numero'):
        raise ValueError('RECHERCHE_GENY_NOM_AMBIGU' if candidates else 'RECHERCHE_GENY_SANS_NOM_EXACT')
    # Le contexte sert de preuve si la recherche exacte ne permet pas de conclure.
    if len(candidates) > 1:
        horse['homonymes_geny'] = list(candidates.values())
    return None


def resolve(horse, out, page=None):
    if page is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                ctx=browser.new_context(locale='fr-FR',timezone_id='Europe/Paris')
                return resolve(horse,out,ctx.new_page())
            finally:
                browser.close()
    candidate = horse.get('lien_candidat')
    search_first = horse.get('recherche_geny_par_nom') and not candidate
    if search_first:
        found = rechercher(horse, page)
        if found:
            return found
    try:
        return ouvrir_source(horse, out, page)
    except LookupError:
        if candidate or search_first or horse.get('id'):
            raise
        # La course a été consultée. Rechercher la fiche sans revenir sur la même page.
        return rechercher({**horse, 'course_url': ''}, page)


def ouvrir_source(horse, out, page):
    ctx = page.context
    candidate = horse.get('lien_candidat')
    if candidate:
        ident = str(horse.get('id', ''))
        if not re.fullmatch(r'\d{4,15}', ident) or candidate != 'https://www.geny.com/cheval/'+ident:
            raise ValueError('LIEN_CANDIDAT_NON_CONCORDANT')
    url = candidate or horse['course_url']
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('geny.com', 'www.geny.com'):
        raise ValueError('URL_COURSE_INVALIDE')
    response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
    verdict = diagnostic_acces(response.status if response else None, page.title(),
                               page.locator('body').inner_text(), page.content())
    if verdict in ('ACCES_LIMITE_429', 'ACCES_REFUSE_403'):
        raise RuntimeError(verdict)
    if candidate:
        actual_name = nom_fiche(page.content(), ident)
        if not actual_name or nom_normalise(actual_name) != nom_normalise(horse['nom']):
            raise ValueError('NOM_FICHE_GENY_NON_CONCORDANT')
        return verifier_candidat(horse,page.url,response.status if response else None,
                                actual_name,out) | {'preuve': 'FICHE_GENY_VERIFIEE'}
    expected = re.search(r'/course/(\d+)', url)
    actual = re.search(r'/course/(\d+)', page.url)
    if not response or response.status != 200 or not expected or not actual or expected[1] != actual[1]:
        raise LookupError('COURSE_GENY_NON_CONFIRMEE')
    from .liens_geny_course import extraire
    proof = extraire([], page.content(), horse.get('engagement'), url, datetime.now(timezone.utc).isoformat())
    found = proof.get('chevaux', {}).get(str(horse['numero']))
    if found and nom_geny_concordant(horse['nom'], found):
        if nom_normalise(found['nom']) != nom_normalise(horse['nom']):
            found['nom_pmu'] = horse['nom']
        (out/'liens_course.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
        return {**found, 'preuve': 'COURSE_GENY_VERIFIEE', 'homonymes': horse.get('homonymes_geny', [])}
    dismiss_consent(page)
    deadline = time.monotonic() + 20
    matched = []
    while time.monotonic() < deadline:
        matched = [r for r in participants_from_rows(get_rows(page))
                   if nom_normalise(r['nom']) == nom_normalise(horse['nom'])]
        if matched:
            break
        page.wait_for_timeout(500)
    # Le numéro confirme le contexte de course ; il n'identifie pas le cheval.
    if len(matched) > 1:
        matched = [row for row in matched if str(row['numero']) == str(horse['numero'])]
    if len(matched) != 1 or str(matched[0]['numero']) != str(horse['numero']):
        (out/'diagnostic_resolution.html').write_text(page.content(), encoding='utf-8')
        raise LookupError('FICHE_EXACTE_NON_IDENTIFIEE')
    from .liens_geny_course import extraire
    proof=extraire(get_rows(page),page.content(),horse.get('engagement'),url,
                  datetime.now(timezone.utc).isoformat())
    (out/'liens_course.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    index = matched[0]['row_index']
    direct = try_direct_url(page, index)
    if not direct:
        before, pages = page.url, set(ctx.pages)
        cliquer_nom(page.locator('tr').nth(index).locator('td').nth(2), matched[0]['nom'])
        for _ in range(30):
            new = [x for x in ctx.pages if x not in pages]
            if new or page.url != before:
                direct = new[-1].url if new else page.url
                if '/cheval/' in direct:
                    break
            page.wait_for_timeout(250)
    match = re.search(r'/cheval/(\d+)', direct or '')
    if not match or urlparse(direct).hostname not in ('geny.com', 'www.geny.com'):
        raise LookupError('FICHE_EXACTE_NON_IDENTIFIEE')
    return {'id': match[1], 'nom': matched[0]['nom'], 'preuve': 'COURSE_GENY_VERIFIEE',
            'url_geny': direct.replace('https://geny.com/', 'https://www.geny.com/'),
            'homonymes': horse.get('homonymes_geny', [])}


def nom_fiche(html, ident):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        if isinstance(data, dict) and str(data.get('identifier')) == str(ident):
            return data.get('name', '')
    return ''


def verifier_candidat(horse,url,status,text,out):
    """Un ID déjà recensé donne une URL candidate, jamais une identité acceptée."""
    ident=str(horse.get('id',''));parsed=urlparse(url)
    actual=re.match(r'/cheval/(\d+)(?:\D|$)',parsed.path)
    identity=bool(horse.get('nom') and nom_normalise(horse['nom']) in nom_normalise(text[:6000]))
    proof={'identifiant_attendu':ident,'url_finale':url,'http':status,'nom_verifie':identity,
           'verification_utc':datetime.now(timezone.utc).isoformat()}
    (out/'verification_lien_candidat.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    if (status!=200 or parsed.scheme!='https' or parsed.hostname not in ('geny.com','www.geny.com')
            or not actual or actual[1]!=ident or not identity):
        raise ValueError('LIEN_CANDIDAT_NON_VERIFIE_HTTP_'+str(status))
    return {'id':ident,'nom':horse['nom'],'url_geny':url.replace('https://geny.com/','https://www.geny.com/')}


def observer_http_geny(context, out=None):
    from .cadence_geny import reprise_serveur
    from .echeances_production import instant, sauver

    mesure = {'requetes': 0, 'reponses_refusees': {'403': 0, '429': 0}}
    def persister_mesure():
        if out is not None:
            sauver(out / 'http_geny.json', mesure)

    def geny(url):
        domaine = urlparse(url).hostname or ''
        return domaine == 'geny.com' or domaine.endswith('.geny.com')

    def requete(request):
        if geny(request.url):
            mesure['requetes'] += 1
            persister_mesure()

    def reponse(response):
        if geny(response.url) and response.status in (403, 429):
            code = str(response.status)
            mesure['reponses_refusees'][code] += 1
            mesure.setdefault('refus', code)
            now = datetime.now(timezone.utc)
            reprise = reprise_serveur(response.header_value('Retry-After'), now)
            precedente = instant(mesure.get('reprise_au_plus_tot_utc'))
            if reprise and (not precedente or reprise > precedente):
                mesure['reprise_au_plus_tot_utc'] = reprise.isoformat()
            persister_mesure()

    context.on('request', requete)
    context.on('response', reponse)
    return mesure


def collecter(horse, out):
    out.mkdir(parents=True, exist_ok=True)
    report = {'complet': False, 'debut_utc': datetime.now(timezone.utc).isoformat()}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                ctx=browser.new_context(locale='fr-FR',timezone_id='Europe/Paris', viewport={'width':1366,'height':900})
                mesure_http = observer_http_geny(ctx, out)
                statuses={}
                def navigation(response):
                    if response.request.is_navigation_request():statuses[response.url]=response.status
                ctx.on('response',navigation)
                page=ctx.new_page()
                geny=horse.get('geny') or resolve(horse,out,page)
                report['geny']=geny
                if mesure_http.get('refus'):
                    from .cadence_geny import REFUS
                    raise RuntimeError(next(statut for statut, code in REFUS.items() if code == mesure_http['refus']))
                # Le lien résolu survit même à une interruption de l'extraction.
                resolution = out/'resolution_geny.tmp'
                resolution.write_text(json.dumps({'geny':geny,
                    'preuve':geny.get('preuve'), 'nom_attendu':horse['nom'],'engagement':horse.get('engagement'),
                    'numero':str(horse.get('numero','')),
                    'resolution_utc':datetime.now(timezone.utc).isoformat()},ensure_ascii=False),encoding='utf-8')
                resolution.replace(out/'resolution_geny.json')
                loaded=next((candidate for candidate in ctx.pages if candidate.url==geny['url_geny']),None)
                if loaded:loaded.wait_for_load_state('domcontentloaded',timeout=15000)
                result=extraire_cheval(geny['url_geny'],geny['id'],out,
                    page=loaded or page,page_chargee=loaded is not None,
                    http_status=statuses.get(geny['url_geny']))
            finally:
                browser.close()
        status, reasons = classifier(result)
        folder = out/geny['id']
        textfile = folder/'diagnostic_texte_geny.txt'
        text = textfile.read_text(encoding='utf-8') if textfile.exists() else ''
        expected = geny['nom'] if nom_geny_concordant(horse['nom'], geny) else horse['nom']
        htmlfile = folder/'diagnostic_geny.html'
        name = nom_fiche(htmlfile.read_text(encoding='utf-8'), geny['id']) if htmlfile.exists() else ''
        identity = (nom_normalise(expected) == nom_normalise(name) if name
                    else bool(nom_normalise(expected) and nom_normalise(expected) in nom_normalise(text[:6000])))
        report.update(geny=geny, statut=status, motifs=reasons,
                      identite_verifiee=identity, complet=status == 'COMPLET' and identity,
                      dossier=str(folder))
    except Exception as exc:
        reason = str(exc)
        reason_codes = {'ACCES_LIMITE_429', 'ACCES_REFUSE_403', 'RECHERCHE_GENY_NON_INTERPRETABLE',
                        'RECHERCHE_GENY_SANS_NOM_EXACT', 'RECHERCHE_GENY_NOM_AMBIGU',
                        'RECHERCHE_GENY_INDISPONIBLE', 'FICHE_EXACTE_NON_IDENTIFIEE'}
        status = reason if reason in reason_codes else 'ERREUR'
        report.update(statut=status, erreur=f'{type(exc).__name__}: {exc}')
    report['fin_utc'] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tache', required=True)
    parser.add_argument('--sortie', required=True)
    args = parser.parse_args()
    out = Path(args.sortie)
    report = collecter(json.loads(Path(args.tache).read_text()), out)
    (out/'resultat.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
