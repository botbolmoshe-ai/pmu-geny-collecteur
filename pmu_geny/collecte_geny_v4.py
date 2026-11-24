"""Collecteur Geny de diagnostic, sans ecriture Google Sheets.

Usage : python collecte_geny_corrige.py
Il refuse automatiquement le consentement optionnel lorsque le bouton est visible.
Il verifie la concordance entre le nombre de courses annonce et les lignes extraites.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DEFAULT_URL = "https://www.geny.com/cheval/2775817-kelle-belle-jasma/course/1683699"
DATE_RE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(20\d{2}|\d{2})(?!\d)")
COUNT_RE = re.compile(r"\bsur\s+(\d{1,4})\s+courses\b", re.I)
RANK_RE = re.compile(r"(?<!\w)(Dpg|Dai|Di|Disq|Nc|NP|(?:\d{1,2})\s*(?:er|e|eme|ème|ᵉ))(?!\w)", re.I)
DIST_RE = re.compile(r"(?<!\d)(\d{4})\s*(?:m|\b)")


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ").replace("\u202f", " ")).strip()


def dismiss_consent(page) -> str:
    """Cliquer seulement sur le refus explicite du bandeau, jamais sur l'acceptation.

    Les CMP peuvent apparaitre apres le chargement ou dans une iframe.
    """
    for _ in range(12):
        for frame in page.frames:
            selectors = [
                frame.get_by_role("button", name=re.compile(r"^\s*Refuser\s*$", re.I)),
                frame.get_by_role("button", name=re.compile(r"Tout refuser|Refuser tout|Continuer sans accepter", re.I)),
                frame.get_by_text("Refuser", exact=True),
            ]
            for candidate in selectors:
                try:
                    button = candidate.first
                    if button.is_visible(timeout=450):
                        button.click(timeout=2500)
                        page.wait_for_timeout(500)
                        print("Consentement : bouton 'Refuser' active.")
                        return "REFUSE"
                except Exception:
                    continue
        page.wait_for_timeout(600)
    print("Consentement : aucun bouton 'Refuser' visible (absent ou deja traite).")
    return "NON_VISIBLE"


def separer_qualifications(candidat: str) -> tuple[str, bool]:
    """Retirer une qualification (hors course) et sa date des donnees de course.

    Geny peut placer une qualification juste apres une course dans le meme
    conteneur DOM. On conserve la course et on elimine uniquement la suite.
    Si le conteneur ne decrit qu'une qualification, on l'exclut entierement.
    """
    texte = normalize(candidat)
    if not re.search(r"\bqualification\b", texte, re.I):
        return texte, False
    # Reperer la date de qualification precedant le libelle. Le format peut
    # etre 03/06/2026, 03/06 2026 ou 03/06 | 2026.
    qual = re.search(r"\bqualification\b", texte, re.I)
    prefixe = texte[:qual.start()]
    dates = list(re.finditer(r"(?<!\d)\d{2}/\d{2}(?:\s*(?:\|\s*)\s*(?:20)?\d{2})?(?!\d)", prefixe))
    if len(dates) >= 2:
        return texte[:dates[-1].start()].rstrip(' |'), True
    # Une seule date : soit une qualification seule, soit une course suivie
    # d'une qualification dont la date est absente. Dans le doute, NE PAS
    # valider une performance sur ce bloc ambigu.
    return '', True


def lire_classement(cellules: list[str]) -> str:
    """Lire uniquement le classement de fin de ligne, jamais une cote ou allocation.

    Geny peut rendre les rangs en un bloc (« 12e »), en deux (« 12 | e »),
    ou afficher un statut (« Dai », « Di »). Le chrono est facultatif.
    """
    cells = [normalize(str(c)) for c in cellules if normalize(str(c))]
    # Le lecteur vidéo peut ajouter « 00:00 | / | 00:00 » après le rang.
    # Retirer uniquement ce suffixe reconnu, sans chercher un rang parmi les cotes.
    if (len(cells)>=3 and cells[-2]=='/' and
            re.fullmatch(r'\d{1,2}:\d{2}',cells[-3]) and
            re.fullmatch(r'\d{1,2}:\d{2}',cells[-1])):
        cells=cells[:-3]
    if not cells:
        return ""
    # Une extraction DOM ajoute parfois des cellules vides ou des espaces.
    dernier = cells[-1]
    # Codes de resultats explicitement affiches par Geny : ne jamais les
    # transformer en rang numerique. R conserve sa valeur source sans
    # interpretation semantique non verifiee.
    non_classes = {"dpg", "dai", "di", "disq", "nc", "np", "arr", "dist", "d", "r", "tb"}
    if dernier.casefold() in non_classes:
        return dernier
    m = re.fullmatch(r"(\d{1,2})\s*(?:er|e|eme|ème|ᵉ)", dernier, re.I)
    if m:
        return m.group(1)
    if len(cells) >= 2 and re.fullmatch(r"(?:er|e|eme|ème|ᵉ)", dernier, re.I):
        if re.fullmatch(r"\d{1,2}", cells[-2]):
            return cells[-2]
    # Certaines structures placent une colonne sans valeur après « Rang ».
    # Ne pas chercher dans toutes les cellules : cela confondrait courses et rang.
    return ""


def parse_career(body: str, dom_rows: list[str]) -> dict:
    """Extrait les dates de courses de carriere en privilegiant les lignes DOM.

    Extraction volontairement conservatrice : une date sans ligne de course exploitable
    ne valide pas l'historique. Les champs incertains restent vides.
    """
    match = re.search(r"(?im)^\s*CARRIÈRE\s*$", body)
    if not match:
        raise ValueError("Rubrique CARRIÈRE introuvable")
    body_after = body[match.end():]
    end = re.search(r"(?im)^\s*(?:COMPRENDRE LES DONNÉES|AUTRES CHEVAUX|PRONOSTICS)\s*$", body_after)
    if end:
        body_after = body_after[:end.start()]
    intro = body_after[:2000]
    counts = [int(x) for x in COUNT_RE.findall(intro)]
    expected = max(counts) if counts else None

    # 1. Lignes de tableau réelles dans le DOM : date et autres cellules sur une seule ligne.
    candidates = [normalize(x) for x in dom_rows if DATE_RE.search(x)]
    # 2. Secours : regrouper les lignes autour des dates dans le texte visible.
    if not candidates:
        lines = [normalize(x) for x in body_after.splitlines() if normalize(x)]
        starts = [i for i, x in enumerate(lines) if DATE_RE.search(x)]
        for j, i in enumerate(starts):
            # Ne pas tronquer arbitrairement à 18 cellules : une qualification
            # datée sur deux lignes peut suivre le rang. Son libellé doit rester
            # visible pour que separer_qualifications retire le bloc entier.
            end_index=starts[j+1] if j+1 < len(starts) else len(lines)
            candidates.append(" | ".join(lines[i:end_index]))

    from .structure_geny import structurer

    records=[]
    qualifications_ignorees = 0
    for brut in candidates:
        txt, contient_qualification = separer_qualifications(brut)
        if contient_qualification:
            qualifications_ignorees += 1
        if not txt:
            continue
        m=DATE_RE.search(txt)
        if not m: continue
        day, month, year=m.groups()
        year = year if len(year)==4 else "20"+year
        date=f"{year}-{month}-{day}"
        # Les lignes DOM de Geny se présentent en cellules séparées.
        # Exemple: date | hippodrome | discipline | 2 650 | ... | 1'16''6 | cote | 10 | e
        parts=[normalize(t) for t in txt.split("|")]
        track="";discipline="";distance="";rank="";chrono=""
        if len(parts)>=7 and DATE_RE.fullmatch(parts[0]):
            track=parts[1]
            discipline=parts[2]
            candidate_distance=re.sub(r"\s+", "", parts[3])
            if candidate_distance.isdigit() and 1000 <= int(candidate_distance) <= 5000:
                distance=candidate_distance
            chrono=next((x for x in parts[4:] if re.fullmatch(r"\d['’]\d{2}(?:['’]{2}\d+)?", x)), "")
            rank=lire_classement(parts[4:])
        else:
            # En cas de structure inconnue, conserver la ligne brute, sans inventer de champs.
            remain=txt[m.end():]
            disc_match=re.search(r"\b(Attel[eé]|Mont[eé])\b", remain, re.I)
            track=normalize(remain[:disc_match.start()]).strip(" -|·•") if disc_match else ""
            discipline=disc_match.group(1) if disc_match else ""
        records.append({
            "date":date,"hippodrome":track,"discipline":discipline,
            "distance_m":distance,"classement":rank,"chrono":chrono,
            "texte_source":txt,
            **structurer(txt),
        })
    # Une date repetee peut correspondre a deux courses differentes (Naples,
    # Frank Gio, 03/05/2026). Rejeter les lignes source identiques, pas les dates.
    dates=[x["date"] for x in records]
    dates_uniques=len(set(dates)) == len(dates)
    signatures=[" ".join(x["texte_source"].casefold().split()) for x in records]
    lignes_uniques=len(set(signatures)) == len(signatures)
    count_ok=(expected is not None and len(records)==expected and lignes_uniques)
    # Le contrôle final exige également les attributs clés : pas de faux 'COMPLET'.
    detailed_ok=all(x["hippodrome"] and x["discipline"] and x["distance_m"] and x["classement"] for x in records)
    return {
        "nombre_annonce_geny":expected,
        "nombre_extrait":len(records),
        "blocs_qualification_exclus": qualifications_ignorees,
        "dates_uniques":dates_uniques,
        "lignes_uniques":lignes_uniques,
        "nombre_concordant":count_ok,
        "champs_detail_valides":detailed_ok,
        "complet":count_ok and detailed_ok,
        "manquants":None if expected is None else max(0,expected-len(records)),
        "performances":records,
    }


def limitation_geny(status: int | None, title: str, visible_text: str) -> bool:
    """Le site peut renvoyer une page 429 avec un statut HTTP 200."""
    if status == 429:
        return True
    title = (title or '').casefold()
    body = (visible_text or '').casefold()
    return ('trop de requêtes' in title or 'trop de requetes' in title
            or bool(re.search(r'\b429\b', body[:1500]) and
                    ('trop de requêtes' in body[:1500] or 'trop de requetes' in body[:1500])))



def diagnostic_acces(status: int | None, title: str, text: str, html: str) -> str:
    """Classer la page existante sans lancer aucune nouvelle requete HTTP.

    RECORDS n'est jamais une condition ; l'accessibilite de CARRIERE est
    evaluee uniquement sur une vraie page cheval, hors erreur de limitation.
    """
    if (limitation_geny(status, title, text) or
        re.search(r"error_status\s*:\s*['\"]429['\"]", html or "") or
        re.search(r"<title>\s*Trop de requ[eê]tes", html or "", re.I)):
        return 'ACCES_LIMITE_429'
    # Geny peut servir une page de refus avec HTTP 200 côté navigation.
    # Vérifier uniquement les marqueurs explicites de la page d'erreur,
    # sans déduire un 403 de la simple absence de CARRIERE.
    if (status == 403 or
        re.search(r"error_status\s*:\s*['\"]403['\"]", html or "") or
        re.search(r"<title>\s*Acc[eè]s refus[eé]\s*-\s*Geny\s*</title>", html or "", re.I) or
        (re.search(r"(?m)^\s*403\s*$", (text or '')[:1200]) and
         re.search(r"acc[eè]s refus[eé]", (text or '')[:1200], re.I))):
        return 'ACCES_REFUSE_403'
    if status is not None and status >= 400:
        return f'HTTP_{status}'
    if re.search(r"(?im)^\s*CARRIÈRE\s*$", text or ""):
        return 'CARRIERE_ACCESSIBLE'
    return 'CARRIERE_NON_DETECTEE'


def enregistrer_acces(outdir: Path, verdict: str, url: str, status: int | None,
                      title: str, cookie_status: str = 'NON_TESTE') -> None:
    record = {
        'statut_acces': verdict, 'carriere_accessible': verdict == 'CARRIERE_ACCESSIBLE',
        'historique_extrait': False, 'historique_complet': False,
        'source_url': url, 'http': status, 'titre_page': title,
        'consentement': cookie_status,
        'extrait_utc': datetime.now(timezone.utc).isoformat(),
    }
    (outdir / 'controle_acces.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')


def sauvegarder_diagnostics(page, outdir: Path, text: str) -> None:
    (outdir / 'diagnostic_texte_geny.txt').write_text(text, encoding='utf-8')
    (outdir / 'diagnostic_geny.html').write_text(page.content(), encoding='utf-8')
    page.screenshot(path=str(outdir / 'diagnostic_capture.png'), full_page=True)

def sauver_refus_ou_limitation(outdir: Path, url: str, status: int | None, titre: str, verdict: str) -> None:
    (outdir / 'etat_collecte.json').write_text(json.dumps({
        'statut': verdict, 'source_url': url,
        'http': status, 'titre_page': titre,
        'extrait_utc': datetime.now(timezone.utc).isoformat(),
        'action': 'ARRET_IMMEDIAT_SANS_REESSAI'
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def collecter_page(page, url: str, outdir: Path, *, page_chargee=False, http_status=None) -> int:
    """Lire dans la session courante ; aucune reconnexion ni navigation de secours."""
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    text=""; dom_rows=[];cookie_status="NON_TESTE"
    # Ne jamais réutiliser par accident un ancien succès après un échec.
    for old in ('historique_geny.json', 'historique_geny.csv', 'etat_collecte.json', 'controle_acces.json'):
        (outdir / old).unlink(missing_ok=True)
    try:
        print("Ouverture :",url)
        if not page_chargee:
            response=page.goto(url,wait_until="domcontentloaded",timeout=45000)
            http_status = response.status if response else None
        print("HTTP :", http_status if http_status is not None else "inconnu")
        title = page.title()
        initial_text = page.locator("body").inner_text(timeout=12000)
        initial_html = page.content()
        verdict = diagnostic_acces(http_status, title, initial_text, initial_html)
        print('Controle initial (sans requete supplementaire) :', verdict, flush=True)
        enregistrer_acces(outdir, verdict, url, http_status, title)
        if verdict in ('ACCES_LIMITE_429', 'ACCES_REFUSE_403'):
            sauver_refus_ou_limitation(outdir, url, http_status, title, verdict)
            sauvegarder_diagnostics(page, outdir, initial_text)
            print(f'{verdict} : arret immediat, sans nouvel essai.', flush=True)
            return 3
        if verdict.startswith('HTTP_'):
            sauvegarder_diagnostics(page, outdir, initial_text)
            print('ERREUR_HTTP :', verdict, flush=True)
            return 2
        if verdict != 'CARRIERE_ACCESSIBLE':
            # L'unique chargement peut afficher un bandeau de consentement.
            # Verifier l'accessibilite a nouveau apres le refus, mais sans
            # declencher une deuxieme navigation vers Geny.
            cookie_status = dismiss_consent(page)
            try:
                page.get_by_text('CARRIÈRE', exact=True).first.wait_for(timeout=7000)
            except PlaywrightTimeoutError:
                pass
            current_text = page.locator('body').inner_text(timeout=12000)
            verdict = diagnostic_acces(http_status, page.title(), current_text, page.content())
            print('Controle apres consentement :', verdict, flush=True)
            enregistrer_acces(outdir, verdict, url, http_status, page.title(), cookie_status)
            if verdict in ('ACCES_LIMITE_429', 'ACCES_REFUSE_403'):
                sauver_refus_ou_limitation(outdir, url, http_status, page.title(), verdict)
                sauvegarder_diagnostics(page, outdir, current_text)
                return 3
            if verdict != 'CARRIERE_ACCESSIBLE':
                sauvegarder_diagnostics(page, outdir, current_text)
                print('CARRIERE_NON_DETECTEE : page conservee pour diagnostic.', flush=True)
                return 2
        else:
            print('CARRIERE_ACCESSIBLE : pas de rubrique RECORDS requise.', flush=True)
        # Continuer progressivement jusqu'a disparition des changements de taille,
        # puis remonter pour garder toute la page accessible.
        last_height=-1; stable=0
        for _ in range(35):
            page.mouse.wheel(0,1400)
            page.wait_for_timeout(400)
            height=page.evaluate("document.body.scrollHeight")
            stable=stable+1 if height==last_height else 0
            last_height=height
            if stable>=5: break
        page.wait_for_timeout(800)
        text=page.locator("body").inner_text(timeout=20000)
        controle_final = diagnostic_acces(http_status, page.title(), text, page.content())
        if controle_final in ('ACCES_LIMITE_429', 'ACCES_REFUSE_403'):
            sauver_refus_ou_limitation(outdir, url, http_status, page.title(), controle_final)
            enregistrer_acces(outdir, controle_final, url, http_status, page.title(), cookie_status)
            sauvegarder_diagnostics(page, outdir, text)
            print(f'{controle_final} : arret immediat.', flush=True)
            return 3
        if controle_final != 'CARRIERE_ACCESSIBLE':
            enregistrer_acces(outdir, controle_final, url, http_status, page.title(), cookie_status)
            sauvegarder_diagnostics(page, outdir, text)
            print('CARRIERE_NON_DETECTEE apres chargement.', flush=True)
            return 2
        # Capture des lignes structurées si Geny utilise un vrai tableau.
        # Playwright Locator.all_inner_texts() n'accepte pas de parametre timeout.
        # Les lignes DOM peuvent ne pas exister si Geny utilise des div CSS.
        dom_rows=page.locator("table tbody tr, [role='row']").all_inner_texts()
        final_html=page.content()
        (outdir/"diagnostic_texte_geny.txt").write_text(text,encoding="utf-8")
        (outdir/"diagnostic_geny.html").write_text(final_html,encoding="utf-8")
        page.screenshot(path=str(outdir/"diagnostic_capture.png"),full_page=True)
    except Exception as e:
        print("ERREUR NAVIGATION :",e)
        try: page.screenshot(path=str(outdir/"diagnostic_capture.png"),full_page=True)
        except Exception: pass
        return 2
    try:
        result=parse_career(text,dom_rows)
    except ValueError as e:
        print("ECHEC EXTRACTION :",e)
        return 2
    result.update({"source_url":url,"extrait_utc":datetime.now(timezone.utc).isoformat(),"consentement":cookie_status})
    from .ferrures_geny import enrichir
    from .carriere_geny import confirmer_inedit
    ident=re.search(r'/cheval/(\d+)',url)
    if ident:
        confirmer_inedit(result,final_html,ident[1])
        enrichir(result,final_html,ident[1],url,result['extrait_utc'])
    result["statut"]="COMPLET" if result["complet"] else "PARTIEL_A_CONTROLER"
    (outdir/"historique_geny.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    cols=["date","hippodrome","discipline","distance_m","classement","chrono","texte_source","ferrure"]
    with (outdir/"historique_geny.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=cols,delimiter=";");writer.writeheader()
        writer.writerows({k:r.get(k,'') for k in cols} for r in result["performances"])
    access_path = outdir / 'controle_acces.json'
    if access_path.exists():
        info = json.loads(access_path.read_text(encoding='utf-8'))
        info['historique_extrait'] = bool(result['nombre_extrait'])
        info['historique_complet'] = bool(result['complet'])
        access_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print("\nConsentement :",cookie_status)
    print("Geny annonce :",result["nombre_annonce_geny"])
    print("Lignes extraites :",result["nombre_extrait"])
    print("Blocs contenant une qualification exclus/nettoyes :", result["blocs_qualification_exclus"])
    print("Lignes manquantes :",result["manquants"])
    print("Statut :",result["statut"])
    print("Fichiers de diagnostic :",outdir.resolve())
    if not result["complet"]:print("Important : champs detail encore a valider ; aucune ecriture Sheets.")
    return 0 if result["complet"] else 1


def main() -> int:
    p=argparse.ArgumentParser(description="Test Geny : consentement + extraction de carrière")
    p.add_argument("--url",default=DEFAULT_URL)
    p.add_argument("--sortie",default="resultats")
    p.add_argument("--headless",action="store_true")
    args=p.parse_args()
    if not args.url.startswith("https://www.geny.com/cheval/"):
        p.error("URL cheval Geny attendue")
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=args.headless)
        try:
            context=browser.new_context(locale="fr-FR",timezone_id="Europe/Paris",viewport={"width":1366,"height":900})
            return collecter_page(context.new_page(), args.url, Path(args.sortie))
        finally:
            browser.close()

if __name__=="__main__":
    sys.exit(main())
