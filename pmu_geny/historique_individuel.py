"""Extraction isolée issue du pilote c08feed, sans état global ni écriture Sheets."""
import argparse
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

from .extraction_historique_par_cheval import extraire_cheval
from .controle_historique import classifier
from .liaison_chevaux_v22 import nom_normalise
from .decouverte_partants import get_rows, participants_from_rows, try_direct_url
from .collecte_geny_v4 import diagnostic_acces, dismiss_consent


def cliquer_nom(cell, nom):
    target = cell.get_by_text(nom, exact=True)
    if target.count() != 1:
        raise ValueError('NOM_CLIQUABLE_AMBIGU')
    target.click(timeout=8000)


def resolve(horse, out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(locale='fr-FR', timezone_id='Europe/Paris')
            page = ctx.new_page()
            candidate=horse.get('lien_candidat')
            if candidate:
                ident=str(horse.get('id',''))
                if not re.fullmatch(r'\d{4,15}',ident) or candidate!='https://www.geny.com/cheval/'+ident:
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
                return verifier_candidat(horse,page.url,response.status if response else None,
                                        page.locator('body').inner_text(),out)
            expected = re.search(r'/course/(\d+)', url)
            actual = re.search(r'/course/(\d+)', page.url)
            if not response or response.status != 200 or not expected or not actual or expected[1] != actual[1]:
                raise ValueError('COURSE_GENY_NON_CONFIRMEE')
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
            if len(matched) != 1 or str(matched[0]['numero']) != str(horse['numero']):
                (out/'diagnostic_resolution.html').write_text(page.content(), encoding='utf-8')
                raise ValueError('FICHE_EXACTE_NON_IDENTIFIEE')
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
                raise ValueError('FICHE_EXACTE_NON_IDENTIFIEE')
            return {'id': match[1], 'nom': horse['nom'],
                    'url_geny': direct.replace('https://geny.com/', 'https://www.geny.com/')}
        finally:
            browser.close()


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


def collecter(horse, out):
    out.mkdir(parents=True, exist_ok=True)
    report = {'complet': False, 'debut_utc': datetime.now(timezone.utc).isoformat()}
    try:
        geny = horse.get('geny') or resolve(horse, out)
        # Un nouveau processus/navigateur isole les erreurs ; il ne contourne aucun refus.
        if not horse.get('geny'):
            time.sleep(30)
        result = extraire_cheval(geny['url_geny'], geny['id'], out)
        status, reasons = classifier(result)
        folder = out/geny['id']
        textfile = folder/'diagnostic_texte_geny.txt'
        text = textfile.read_text(encoding='utf-8') if textfile.exists() else ''
        identity = nom_normalise(horse['nom']) in nom_normalise(text[:6000])
        report.update(geny=geny, statut=status, motifs=reasons,
                      identite_verifiee=identity, complet=status == 'COMPLET' and identity,
                      dossier=str(folder))
    except Exception as exc:
        status = 'ACCES_LIMITE_429' if '429' in str(exc) else 'ACCES_REFUSE_403' if '403' in str(exc) else 'ERREUR'
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
