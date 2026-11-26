"""Extraction isolée issue du pilote c08feed, sans état global ni écriture Sheets."""
import argparse
import json
import os
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

from .extraction_historique_par_cheval import extraire_cheval
from .controle_historique import classifier
from .liaison_chevaux_v22 import nom_geny_concordant, nom_normalise, separer_pays_pmu
from .decouverte_partants import get_rows
from .collecte_geny_v4 import diagnostic_acces, dismiss_consent


RECHERCHE_NON_AUTORISEE = 'RECHERCHE_GENY_NON_AUTORISEE'


def recherche_autorisee():
    # /recherche est exclu par robots.txt. Réserver l'accès nominatif aux
    # exécutions bénéficiant d'une autorisation explicite du fournisseur.
    return os.environ.get('GENY_RECHERCHE_AUTORISEE') == 'true'


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
    if not recherche_autorisee():
        raise ValueError(RECHERCHE_NON_AUTORISEE)
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
    candidates = candidats_recherche(html, name)
    if country:
        sans_nationalite = any(not fiche.get('nationalite_geny') for fiche in candidates.values())
        candidates = {ident: {**fiche, 'nom_pmu': horse['nom']} for ident, fiche in candidates.items()
                      if nom_geny_concordant(horse['nom'], fiche)}
        if not candidates and sans_nationalite:
            raise ValueError('RECHERCHE_GENY_NOM_AMBIGU')
    year = horse.get('annee_naissance_pmu')
    current = datetime.now(ZoneInfo('Europe/Paris')).year
    if len(candidates) == 1 and horse.get('rapprochement_geny') != 'NOM_AMBIGU':
        fiche = next(iter(candidates.values()))
        if not year or fiche['age_geny'] is None or current - fiche['age_geny'] == year:
            return {**fiche, 'preuve': 'RECHERCHE_GENY_NOM_EXACT',
                    'annee_naissance_pmu': year}
        raise ValueError('RECHERCHE_GENY_NOM_AMBIGU')
    if len(candidates) > 1 and year and all(h['age_geny'] is not None for h in candidates.values()):
        same_year = [h for h in candidates.values() if current - h['age_geny'] == year]
        if len(same_year) == 1:
            return {**same_year[0], 'preuve': 'RECHERCHE_GENY_NOM_EXACT',
                    'homonymes': list(candidates.values()), 'annee_naissance_pmu': year}
    raise ValueError('RECHERCHE_GENY_NOM_AMBIGU' if candidates else 'RECHERCHE_GENY_SANS_NOM_EXACT')


def recherche_bloquee_avant_navigation(horse):
    return (not recherche_autorisee() and not (horse.get('geny') or horse.get('lien_candidat'))
            and (not horse.get('course_url') or not horse.get('numero') or horse.get('course_geny_deja_lue')))


def resolve(horse, out, page=None, *, arreter=None):
    if page is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                ctx=browser.new_context(locale='fr-FR',timezone_id='Europe/Paris')
                return resolve(horse,out,ctx.new_page())
            finally:
                browser.close()
    if horse.get('lien_candidat'):
        return ouvrir_source(horse, out, page)
    if horse.get('course_url') and horse.get('numero') and not horse.get('course_geny_deja_lue'):
        try:
            return ouvrir_source(horse, out, page)
        except LookupError:
            if horse.get('id') or arreter and arreter():
                raise
    if not horse.get('id') and horse.get('nom'):
        return rechercher({**horse, 'course_url': ''}, page)
    raise ValueError('IDENTITE_GENY_SANS_PREUVE')


def ouvrir_source(horse, out, page):
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
    stamp = datetime.now(timezone.utc).isoformat()
    html = page.content()
    proof = extraire([], html, horse.get('engagement'), url, stamp)
    found = proof.get('chevaux', {}).get(str(horse['numero']))
    if not found:
        dismiss_consent(page)
        proof = extraire(get_rows(page), page.content(), horse.get('engagement'), url, stamp)
        found = proof.get('chevaux', {}).get(str(horse['numero']))
    if not found:
        (out/'diagnostic_resolution.html').write_text(page.content(), encoding='utf-8')
        raise LookupError('FICHE_EXACTE_NON_IDENTIFIEE')
    if not nom_geny_concordant(horse['nom'], found):
        raise ValueError('NOM_FICHE_GENY_NON_CONCORDANT')
    if nom_normalise(found['nom']) != nom_normalise(horse['nom']):
        found['nom_pmu'] = horse['nom']
    (out/'liens_course.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
    return {**found, 'preuve': 'COURSE_GENY_VERIFIEE'}


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


def ignorer_ressource(route):
    # Le texte, les données, les scripts et les styles restent disponibles.
    if route.request.resource_type in ('image', 'media', 'font'):
        route.abort()
    else:
        route.fallback()


def observer_http_geny(context, out=None, *, filtrage=False):
    from .cadence_geny import reprise_serveur
    from .echeances_production import instant, sauver

    mesure = {'requetes': 0, 'reponses_refusees': {'403': 0, '429': 0}, 'par_ressource': {},
              'details': []}
    en_cours = {}
    occurrences = {}
    def persister_mesure():
        if out is not None:
            sauver(out / 'http_geny.json', mesure)

    def geny(url):
        domaine = urlparse(url).hostname or ''
        return domaine == 'geny.com' or domaine.endswith('.geny.com')

    def requete(request):
        if geny(request.url):
            # Playwright émet aussi request pour les ressources interceptées.
            resource = getattr(request, 'resource_type', 'inconnu')
            if resource in ('image', 'media', 'font') and filtrage:
                return
            mesure['requetes'] += 1
            mesure['par_ressource'][resource] = mesure['par_ressource'].get(resource, 0) + 1
            url = request.url
            method = getattr(request, 'method', 'GET')
            key = (url, method)
            occurrences[key] = occurrences.get(key, 0) + 1
            entry = {'url': url, 'type': resource, 'methode': method,
                     'occurrence': occurrences[key], 'origine': 'navigateur',
                     'etape': 'recherche' if '/recherche' in url else 'course' if '/course/' in url
                     and '/cheval/' not in url else 'carriere' if '/cheval/' in url else 'ressource'}
            en_cours[id(request)] = (time.monotonic(), entry)
            mesure['details'].append(entry)
            if mesure['requetes'] % 20 == 0:
                persister_mesure()

    def reponse(response):
        if not geny(response.url):
            return
        timing = en_cours.pop(id(getattr(response, 'request', None)), None)
        if timing:
            start, entry = timing
            entry.update(statut=response.status, duree_ms=round((time.monotonic() - start) * 1000),
                         service_worker=bool(getattr(response, 'from_service_worker', False)))
        if response.status in (403, 429):
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
    context.on('close', lambda *_: persister_mesure())
    persister_mesure()
    return mesure


def observer_cache_chromium(context, page, mesure):
    """Distinguer les événements du navigateur des requêtes sorties sur le réseau."""
    session = context.new_cdp_session(page)
    memory_cache = set()
    hits = mesure.setdefault('cache_http_par_ressource', {})

    def reponse(event):
        identifiant = event['requestId']
        response = event['response']
        if identifiant not in memory_cache and not response.get('fromDiskCache'):
            return
        memory_cache.discard(identifiant)
        target = urlparse(response['url']).hostname or ''
        if target == 'geny.com' or target.endswith('.geny.com'):
            resource = event['type'].lower()
            hits[resource] = hits.get(resource, 0) + 1
            for entry in reversed(mesure['details']):
                if entry['url'] == response['url'] and not entry.get('cache_http'):
                    entry['cache_http'] = True
                    break

    session.on('Network.requestServedFromCache', lambda event: memory_cache.add(event['requestId']))
    session.on('Network.responseReceived', reponse)
    session.send('Network.enable')


def collecter(horse, out, *, profil=None):
    out.mkdir(parents=True, exist_ok=True)
    report = {'complet': False, 'debut_utc': datetime.now(timezone.utc).isoformat()}
    try:
        if recherche_bloquee_avant_navigation(horse):
            raise ValueError(RECHERCHE_NON_AUTORISEE)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            config = {'locale': 'fr-FR', 'timezone_id': 'Europe/Paris',
                      'viewport': {'width': 1366, 'height': 900}}
            browser = None
            if profil:
                # Sans interception Playwright, Chromium conserve son cache HTTP.
                ctx = p.chromium.launch_persistent_context(profil,
                    args=['--blink-settings=imagesEnabled=false'], **config)
            else:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(**config)
                ctx.route('**/*', ignorer_ressource)
            try:
                mesure_http = observer_http_geny(ctx, out, filtrage=not profil)
                statuses={}
                def navigation(response):
                    if response.request.is_navigation_request():statuses[response.url]=response.status
                ctx.on('response',navigation)
                page = ctx.pages[0] if profil and ctx.pages else ctx.new_page()
                if profil:
                    observer_cache_chromium(ctx, page, mesure_http)
                def interrompre():
                    return bool(mesure_http.get('refus'))

                geny=horse.get('geny') or resolve(horse,out,page,arreter=interrompre)
                report['geny']=geny
                if mesure_http.get('refus'):
                    from .cadence_geny import REFUS
                    raise RuntimeError(next(statut for statut, code in REFUS.items() if code == mesure_http['refus']))
                # Le lien résolu survit même à une interruption de l'extraction.
                resolution = out/'resolution_geny.tmp'
                resolution.write_text(json.dumps({'geny':geny,
                    'preuve':geny.get('preuve'), 'nom_attendu':horse['nom'],'engagement':horse.get('engagement'),
                    'numero':str(horse.get('numero','')),
                    'id_pmu':horse.get('id_pmu'), 'annee_naissance_pmu':horse.get('annee_naissance_pmu'),
                    'resolution_utc':datetime.now(timezone.utc).isoformat()},ensure_ascii=False),encoding='utf-8')
                resolution.replace(out/'resolution_geny.json')
                from .liens_geny_course import url_fiche_canonique
                url_fiche = url_fiche_canonique(geny['url_geny'])
                loaded = page.url == url_fiche
                result=extraire_cheval(url_fiche,geny['id'],out,
                    page=page,page_chargee=loaded,
                    http_status=statuses.get(url_fiche),
                    arreter=interrompre)
            finally:
                if browser:
                    browser.close()
                else:
                    # Le profil garde le cache mais redémarre sur une page vide.
                    # Chromium ne doit jamais rouvrir les fiches du cheval précédent.
                    try:
                        for tab in ctx.pages:
                            tab.goto('about:blank', timeout=3000)
                    finally:
                        ctx.close()
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
                        'RECHERCHE_GENY_INDISPONIBLE', 'FICHE_EXACTE_NON_IDENTIFIEE',
                        'NOM_FICHE_GENY_NON_CONCORDANT', RECHERCHE_NON_AUTORISEE}
        status = reason if reason in reason_codes else 'ERREUR'
        report.update(statut=status, erreur=f'{type(exc).__name__}: {exc}')
    report['fin_utc'] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tache', required=True)
    parser.add_argument('--sortie', required=True)
    parser.add_argument('--profil')
    args = parser.parse_args()
    out = Path(args.sortie)
    report = collecter(json.loads(Path(args.tache).read_text()), out, profil=args.profil)
    (out/'resultat.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
