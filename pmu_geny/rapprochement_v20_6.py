"""Rapprochement PMU–Geny priorisant la clef date + hippodrome + R/C.

Index journalier, repli sur le nom, refus en cas d'ambiguïté.
Le chargement Geny est séparé de la décision métier pour permettre les tests hors réseau.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

GENY_PROGRAMME = 'https://www.geny.com/programme/{date}/orga/PMU'
COURSE_LINK = re.compile(r'^/course/(\d+)-(.+)$', re.I)
STOP = {'prix', 'de', 'des', 'du', 'la', 'le', 'les', 'd', 'l', 'et', 'grand', 'course', 'gp'}


def norm(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def tokens(value):
    return set(norm(value).split()) - STOP


def nom_course_url(url):
    """Extraire la partie «prix...» du slug quand elle existe."""
    slug = norm(urlparse(url).path)
    m = re.search(r'\b(?:prix|grand prix)\b', slug)
    return slug[m.start():] if m else slug


def _numero(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 < value < 100:
        return value
    if isinstance(value, str) and re.fullmatch(r'\d{1,2}', value.strip()):
        n = int(value)
        return n if n > 0 else None
    return None


def _meme_hippodrome(course, candidate):
    from .selection_metier_v20_4 import normaliser_hippodrome
    location = normaliser_hippodrome(course.get('hippodrome', ''))
    slug = candidate.get('slug', '')
    return bool(tokens(location) and tokens(location).issubset(tokens(slug)))


def _meme_date(course, candidate):
    return (not course.get('date')) or course['date'] == candidate.get('date')


def index_from_anchors(anchors, date):
    """Dédupliquer les liens du programme sans charger les pages individuelles."""
    seen = {}
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        url = str(anchor.get('href') or '')
        parsed = urlparse(url)
        if parsed.hostname not in ('www.geny.com', 'geny.com'):
            continue
        match = COURSE_LINK.match(parsed.path)
        if not match:
            continue
        slug = re.sub(r'/(?:partants-pronostics|partants-pronos|arrivee|resultats)(?:/.*)?$', '', match.group(2), flags=re.I)
        if date not in slug:
            continue
        cid = match.group(1)
        canonical = f'https://www.geny.com/course/{cid}-{slug}'
        old = seen.get(cid)
        # Le lien du programme peut avoir le texte «Partants/Pronos» ; le slug reste utile.
        # Les numéros R/C doivent être observés dans le DOM et jamais déduits
        # de l'ordre des liens ni de l'identifiant opaque Geny.
        r = _numero(anchor.get('r'))
        c = _numero(anchor.get('c'))
        item = {'geny_id': cid, 'url': canonical, 'slug': norm(slug),
                'texte': str(anchor.get('text') or ''), 'date': date,
                'r': r, 'c': c, 'code_rc_verifie': r is not None and c is not None}
        if old is None:
            seen[cid] = item
        elif item['code_rc_verifie'] and not old['code_rc_verifie']:
            seen[cid] = item
        elif item['code_rc_verifie'] and old['code_rc_verifie'] and (item['r'],item['c']) != (old['r'],old['c']):
            # Deux positions contradictoires pour la même fiche : supprimer le code.
            old.update({'r':None,'c':None,'code_rc_verifie':False,'code_rc_conflit':True})
        elif len(item['texte']) > len(old['texte']) and not old.get('code_rc_conflit'):
            # Le libellé le plus explicite, sans perdre une preuve R/C antérieure.
            item['r'], item['c'], item['code_rc_verifie'] = old['r'], old['c'], old['code_rc_verifie']
            seen[cid] = item
    return list(seen.values())


def similarity(course, candidate):
    """Renvoie score et preuves; écarte une contradiction hippodrome évidente."""
    from .selection_metier_v20_4 import normaliser_hippodrome
    location = normaliser_hippodrome(course.get('hippodrome', ''))
    slug = candidate.get('slug', '')
    loc_tokens = tokens(location)
    slug_tokens = tokens(slug)
    # Refus si la date ou l'hippodrome diffère.
    if not _meme_date(course,candidate) or not loc_tokens or not loc_tokens.issubset(slug_tokens):
        return 0.0, {'hippodrome': False}
    raw_name = norm(course.get('nom', ''))
    title = nom_course_url(candidate['url'])
    a, b = tokens(raw_name), tokens(title)
    if not a or not b:
        return 0.0, {'hippodrome': True, 'nom': False}
    # Le titre Geny peut avoir des compléments (sponsor, groupe), d'où ce score souple.
    overlap = len(a & b) / max(len(a), len(b))
    fuzzy = SequenceMatcher(None, raw_name, title).ratio()
    title_score = max(overlap, fuzzy)
    # Un nom court doit partager son terme distinctif; le fuzzy seul peut
    # confondre « Prix de Beauvais » et « Prix de Paris ».
    if (len(a) <= 2 and not a.issubset(b)) or title_score < .58:
        return 0.0, {'hippodrome': True, 'similarite_nom': round(title_score, 3)}
    score = .42 + .58 * title_score
    return score, {'hippodrome': True, 'similarite_nom': round(title_score, 3)}


def _nom_fortement_identique(course, candidate):
    """Preuve de nom très forte, indépendante de la numérotation R/C.

    Un nom identique normalisé (ou les mêmes termes hors mots vides)
    est accepté ; la similarité floue seule ne prouve pas une renumérotation.
    """
    source = norm(course.get('nom', ''))
    target = nom_course_url(candidate.get('url', ''))
    a, b = tokens(source), tokens(target)
    if not a or not b:
        return False
    return source == target or (a == b and len(a) >= 2)


def rapprocher(course, candidats, seuil=.83, ecart=.12):
    """Associer date + hippodrome + nom ; R/C n'est qu'une preuve additionnelle.

    Les éditeurs peuvent renuméroter les réunions. Si un code R/C diffère,
    seuls un nom très fortement identique et une unicité par hippodrome/date
    permettent le rapprochement ; une divergence est explicitement auditée.
    """
    r = _numero(course.get('num_reunion'))
    c = _numero(course.get('num_course'))
    eligible = [cand for cand in candidats if _meme_date(course, cand) and _meme_hippodrome(course, cand)]
    direct = [cand for cand in eligible if r is not None and c is not None
              and cand.get('code_rc_verifie') and cand.get('r') == r and cand.get('c') == c]
    if len(direct) > 1:
        return {'statut': 'CORRESPONDANCE_AMBIGUE', 'methode': 'DATE_HIPPODROME_RC',
                'candidats': len(direct)}
    conflit_direct = None
    if len(direct) == 1:
        cand = direct[0]
        score, preuve_nom = similarity(course, cand)
        if score > 0 or not course.get('nom'):
            return {'statut': 'CORRESPONDANCE_CONFIRMEE', 'geny_id': cand['geny_id'],
                    'url': cand['url'], 'score': 1.0,
                    'methode': 'DATE_HIPPODROME_RC',
                    'preuves': {'date': True, 'hippodrome': True, 'r': r, 'c': c, 'nom': preuve_nom}}
        conflit_direct = cand

    # D'abord tester TOUS les noms très solides, y compris les candidats
    # dotés d'un R/C différent. La différence de code n'est pas un rejet.
    forts = [cand for cand in eligible if _nom_fortement_identique(course, cand)]
    if len(forts) > 1:
        return {'statut': 'CORRESPONDANCE_AMBIGUE', 'methode': 'NOM_FORT',
                'candidats': len(forts)}
    if len(forts) == 1:
        cand = forts[0]
        contradictoire = bool(cand.get('code_rc_verifie') and r is not None and c is not None
                               and (cand.get('r'), cand.get('c')) != (r, c))
        return {'statut': 'CORRESPONDANCE_CONFIRMEE', 'geny_id': cand['geny_id'],
                'url': cand['url'], 'score': 1.0,
                'methode': 'NOM_FORT_RC_DIFFERENT' if contradictoire else 'NOM_FORT',
                'preuves': {'date': True, 'hippodrome': True, 'nom_identique': True,
                            'code_rc_different': contradictoire,
                            'pmu_rc': [r, c], 'geny_rc': [cand.get('r'), cand.get('c')]}}

    # Les noms approximatifs restent autorisés uniquement pour les candidats
    # non documentés R/C, avec seuil et marge de non-ambiguïté stricts.
    inconnus = [cand for cand in eligible if not cand.get('code_rc_verifie')]
    matches = []
    for cand in inconnus:
        score, preuves = similarity(course, cand)
        if score:
            matches.append((score, cand, preuves))
    matches.sort(key=lambda x: x[0], reverse=True)
    if not matches or matches[0][0] < seuil:
        if conflit_direct is not None:
            return {'statut': 'CONFLIT_CODE_ET_NOM', 'candidats': len(eligible),
                    'geny_id_candidat': conflit_direct['geny_id']}
        return {'statut': 'AUCUNE_CORRESPONDANCE_FIABLE', 'candidats': len(matches),
                'meilleur_score': round(matches[0][0], 3) if matches else 0,
                'codes_differents': len(eligible) - len(inconnus)}
    top = matches[0]
    if len(matches) > 1 and top[0] - matches[1][0] < ecart:
        return {'statut': 'CORRESPONDANCE_AMBIGUE', 'methode': 'NOM_SECOURS',
                'candidats': len(matches), 'meilleur_score': round(top[0], 3),
                'second_score': round(matches[1][0], 3)}
    return {'statut': 'CORRESPONDANCE_CONFIRMEE', 'geny_id': top[1]['geny_id'],
            'url': top[1]['url'], 'score': round(top[0], 3),
            'methode': 'NOM_SECOURS', 'preuves': top[2]}


def liens_programme_avec_contexte(page):
    """Extraire les codes R/C seulement quand le DOM montre un contexte univoque.

    Ne pas utiliser la position dans la liste des ancres comme numéro de course.
    Les mises en page non reconnues restent au rapprochement par nom.
    """
    return page.locator('a[href]').evaluate_all(r"""els => els.map(a => {
      const href=a.href, text=(a.innerText||a.title||'').trim();
      const out={href,text};
      if(!/\/course\/\d+-/.test(href)) return out;
      const num=(s,letter)=>{
        const pat=new RegExp('(?:^|\\s)'+letter+'\\s*(\\d{1,2})(?=\\s|$)','gi');
        const matches=[...s.matchAll(pat)].map(m=>Number(m[1]));
        return matches.length && matches.every(n=>n===matches[0]) ? matches[0] : null;
      };
      // Restreindre les ancêtres à de petits blocs descriptifs : un conteneur
      // de réunion entière contient plusieurs Cn et ne prouve aucun numéro.
      let node=a;
      for(let k=0;k<5 && node;k++,node=node.parentElement){
        const s=(node.innerText||'').trim();
        if(s.length>650) break;
        const c=num(s,'C'), r=num(s,'R');
        if(c && r){out.r=r;out.c=c;out.contexte='bloc_local';break;}
      }
      return out;
    })""")

def index_programme(cache, date, etat_path, ttl_heures=6):
    """Interroger le programme une fois par TTL, pas une fois par course.

    Sur 403/429 explicite, consigner le blocage pour le cooldown partagé.
    """
    from .auto_v18 import load, save
    from .cadence_geny import reprise_serveur
    from .collecte_geny_v4 import diagnostic_acces, dismiss_consent
    target = Path(cache) / 'sources_geny' / f'index_{date}.json'
    existing = load(target, {}) or {}
    fetched = existing.get('consultation_utc')
    if fetched:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(fetched)
            if age < timedelta(hours=ttl_heures) and existing.get('statut') == 'OK' and existing.get('schema_index') == 2:
                return existing
        except ValueError:
            pass
    from playwright.sync_api import sync_playwright
    url = GENY_PROGRAMME.format(date=date)
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(locale='fr-FR', timezone_id='Europe/Paris')
            page = ctx.new_page()
            resp = page.goto(url, wait_until='domcontentloaded', timeout=45000)
            http_status = resp.status if resp else None
            verdict = diagnostic_acces(http_status, page.title(), page.locator('body').inner_text(), page.content())
            if verdict in ('ACCES_LIMITE_429','ACCES_REFUSE_403'):
                state = load(etat_path,{}) or {}
                now = datetime.now(timezone.utc)
                incident = {'utc': now.isoformat(), 'code': '403' if '403' in verdict else '429'}
                if resp and (reprise := reprise_serveur(resp.header_value('retry-after'), now)):
                    incident['reprise_au_plus_tot_utc'] = reprise.isoformat()
                state['dernier_blocage_geny'] = incident
                save(etat_path, state)
                return {'statut':'GENY_BLOQUE','motif':verdict, 'courses':[]}
            if http_status != 200:
                return {'statut':f'HTTP_{http_status}','courses':[]}
            dismiss_consent(page)
            entries=index_from_anchors(liens_programme_avec_contexte(page),date)
            out={'schema_index':2, 'codes_rc_documentes':sum(e.get('code_rc_verifie',False) for e in entries),
                 'statut':'OK' if entries else 'INDEX_VIDE', 'consultation_utc':datetime.now(timezone.utc).isoformat(),
                 'source':url, 'courses':entries}
            save(target,out)
            return out
        finally:
            browser.close()
