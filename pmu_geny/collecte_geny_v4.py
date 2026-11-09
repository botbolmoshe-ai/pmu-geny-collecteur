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
RANK_RE = re.compile(r"(?<!\w)(Dai|Disq|Nc|NP|(?:\d{1,2})\s*(?:er|e|eme|ème|ᵉ))(?!\w)", re.I)
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
            candidates.append(" | ".join(lines[i: min(starts[j+1] if j+1 < len(starts) else i+18, i+18)]))

    records=[]
    for txt in candidates:
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
            if parts[-1].casefold() in {"e","er","eme","ème"} and len(parts)>1 and re.fullmatch(r"\d{1,2}", parts[-2]):
                rank=parts[-2]
            elif parts[-1].casefold() in {"dai","disq","nc","np","arr","dist"}:
                rank=parts[-1]
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
        })
    # Une date répétée en DOM indique doublon ou artefact, jamais conformité.
    dates=[x["date"] for x in records]
    unique=len(set(dates)) == len(dates)
    count_ok=(expected is not None and len(records)==expected and unique)
    # Le contrôle final exige également les attributs clés : pas de faux 'COMPLET'.
    detailed_ok=all(x["hippodrome"] and x["discipline"] and x["distance_m"] and x["classement"] for x in records)
    return {
        "nombre_annonce_geny":expected,
        "nombre_extrait":len(records),
        "dates_uniques":unique,
        "nombre_concordant":count_ok,
        "champs_detail_valides":detailed_ok,
        "complet":count_ok and detailed_ok,
        "manquants":None if expected is None else max(0,expected-len(records)),
        "performances":records,
    }


def main() -> int:
    p=argparse.ArgumentParser(description="Test Geny : consentement + extraction de carrière")
    p.add_argument("--url",default=DEFAULT_URL)
    p.add_argument("--sortie",default="resultats")
    p.add_argument("--headless",action="store_true")
    args=p.parse_args()
    if not args.url.startswith("https://www.geny.com/cheval/"):
        p.error("URL cheval Geny attendue")
    outdir=Path(args.sortie);outdir.mkdir(parents=True,exist_ok=True)
    text=""; dom_rows=[];cookie_status="NON_TESTE"
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=args.headless)
        context=browser.new_context(locale="fr-FR",timezone_id="Europe/Paris",viewport={"width":1366,"height":900})
        page=context.new_page()
        try:
            print("Ouverture :",args.url)
            response=page.goto(args.url,wait_until="domcontentloaded",timeout=45000)
            print("HTTP :",response.status if response else "inconnu")
            cookie_status=dismiss_consent(page)
            try: page.get_by_text("CARRIÈRE",exact=True).first.wait_for(timeout=20000)
            except PlaywrightTimeoutError: print("Rubrique CARRIÈRE non detectee dans le delai.")
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
            # Capture des lignes structurées si Geny utilise un vrai tableau.
            # Playwright Locator.all_inner_texts() n'accepte pas de parametre timeout.
            # Les lignes DOM peuvent ne pas exister si Geny utilise des div CSS.
            dom_rows=page.locator("table tbody tr, [role='row']").all_inner_texts()
            (outdir/"diagnostic_texte_geny.txt").write_text(text,encoding="utf-8")
            (outdir/"diagnostic_geny.html").write_text(page.content(),encoding="utf-8")
            page.screenshot(path=str(outdir/"diagnostic_capture.png"),full_page=True)
        except Exception as e:
            print("ERREUR NAVIGATION :",e)
            try: page.screenshot(path=str(outdir/"diagnostic_capture.png"),full_page=True)
            except Exception: pass
            return 2
        finally:
            context.close();browser.close()
    try:
        result=parse_career(text,dom_rows)
    except ValueError as e:
        print("ECHEC EXTRACTION :",e)
        return 2
    result.update({"source_url":args.url,"extrait_utc":datetime.now(timezone.utc).isoformat(),"consentement":cookie_status})
    result["statut"]="COMPLET" if result["complet"] else "PARTIEL_A_CONTROLER"
    (outdir/"historique_geny.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    cols=["date","hippodrome","discipline","distance_m","classement","chrono","texte_source"]
    with (outdir/"historique_geny.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=cols,delimiter=";");writer.writeheader()
        writer.writerows({k:r[k] for k in cols} for r in result["performances"])
    print("\nConsentement :",cookie_status)
    print("Geny annonce :",result["nombre_annonce_geny"])
    print("Lignes extraites :",result["nombre_extrait"])
    print("Lignes manquantes :",result["manquants"])
    print("Statut :",result["statut"])
    print("Fichiers de diagnostic :",outdir.resolve())
    if not result["complet"]:print("Important : champs detail encore a valider ; aucune ecriture Sheets.")
    return 0 if result["complet"] else 1

if __name__=="__main__":
    sys.exit(main())
