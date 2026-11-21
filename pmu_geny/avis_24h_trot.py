"""Veille éditoriale publique en marge de la publication PMU."""
import argparse
from datetime import datetime, timedelta, timezone
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup

from .echeances_production import PARIS, instant, lire, sauver

BASE = 'https://province-courses.fr/24H/'
HOSTS = {'province-courses.fr', 'www.province-courses.fr'}
WEEKDAYS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')
DATE_RUBRIQUE = re.compile(r'(Actualité|En bref|Demain à Vincennes|Aujourd.hui à Vincennes|'
                          r'Présentation de course|Le Mag)\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})', re.I)


class Redirections(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not source_autorisee(newurl):
            raise ValueError('Redirection hors de la source')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def source_autorisee(url):
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and parsed.hostname in HOSTS
            and parsed.path in ('/24H/articles.php', '/24H/article_PDF.php'))


def lire_page(url):
    if not source_autorisee(url):
        raise ValueError('URL 24H au Trot non autorisée')
    with build_opener(Redirections()).open(Request(url, headers={
            'User-Agent': 'PMU-Trot-Research/1.0'}), timeout=6) as response:
        content = response.read(2_000_001)
    if len(content) > 2_000_000:
        raise ValueError('Page 24H au Trot trop longue')
    return content


def normaliser(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(
        char for char in value if not unicodedata.combining(char))))


def contient(text, terme):
    match = normaliser(terme)
    return bool(match and f' {match} ' in f' {normaliser(text)} ')


def liens_index(html):
    result = {}
    for link in BeautifulSoup(html, 'html.parser').find_all('a', href=True):
        url = urljoin(BASE, link['href'])
        heading = link.get_text(' ', strip=True)
        if heading and source_autorisee(url) and re.fullmatch(
                r'id=\d+', urlparse(url).query) and urlparse(url).path.endswith('/article_PDF.php'):
            result.setdefault(url, heading)
    return result


def article(html, titre_index, course, cheval, observed):
    soup = BeautifulSoup(html, 'html.parser')
    heading = next((node for node in soup.select('h1,h2,h3,h4')
                    if normaliser(node.get_text(' ', strip=True)) == normaliser(titre_index)), None)
    if heading is None or not contient(titre_index, cheval):
        return None
    # L'en-tête de l'article porte sa rubrique et sa date. Le premier
    # paragraphe doit nommer ensemble le cheval, la course et l'hippodrome.
    dating = None
    for previous in heading.find_all_previous('small', limit=4):
        dating = DATE_RUBRIQUE.search(previous.parent.get_text(' ', strip=True))
        if dating:
            break
    lead = heading.find_next('p')
    if not dating or lead is None or not lead.get_text(strip=True):
        return None
    published = datetime.strptime(dating[2], '%d.%m.%Y').date()
    target = datetime.fromisoformat(course['date']).date()
    local_day = observed.astimezone(PARIS).date()
    if not 0 <= (target - published).days <= 3 or published > local_day:
        return None
    first_paragraph = lead.get_text(' ', strip=True)
    # Lier le cheval et le prix dans la même phrase, sans attribuer
    # un engagement cité ailleurs dans l'article au cheval du titre.
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÉÈÀ])|\b(?:quand|tandis que|alors que)\b',
                         first_paragraph, flags=re.IGNORECASE)
    if not any(all(contient(sentence, term) for term in (cheval, course['nom'], 'Vincennes'))
               for sentence in sentences):
        return None
    distance = (target - published).days
    if distance == 0:
        markers = ("aujourd'hui", 'ce ' + WEEKDAYS[target.weekday()])
    elif distance == 1:
        markers = ('demain', WEEKDAYS[target.weekday()])
    else:
        markers = (WEEKDAYS[target.weekday()],)
    if not any(contient(first_paragraph, term) or contient(dating[1], term) for term in markers):
        return None
    return {'titre': titre_index[:220], 'publication_date': published.isoformat(),
            'lecture_utc': observed.isoformat(), 'nature': 'ARTICLE_EDITORIAL'}


def collecter(cache, *, fetch=lire_page, clock=lambda: datetime.now(timezone.utc)):
    cache = Path(cache)
    now = clock()
    day = now.astimezone(PARIS).date()
    candidates = []
    for date in (day, day + timedelta(days=1)):
        programme = lire(cache/'sources_pmu'/f'programme_{date}.json')
        for course in programme.get('courses_jalons', programme.get('programme', [])):
            departure = instant(course.get('depart'))
            if not departure or departure <= now or not contient(course.get('hippodrome', ''), 'Vincennes'):
                continue
            key = f"{date}_{course['code']}"
            profile = lire(cache/'partants_actuels'/f'{key}.json')
            for number, horse in profile.get('chevaux', {}).items():
                if horse.get('nom') and horse.get('statut_np') == 'PARTANT':
                    candidates.append((course, key, number, horse['nom'], departure))
    if not candidates:
        return 0
    directory = cache/'avis_editoriaux'
    index = directory/f'index_24h_{day:%Y-%m}.json'
    last = lire(index)
    checked = instant(last.get('controle_utc'))
    if checked and timedelta(0) <= now - checked < timedelta(hours=1):
        return 0
    # Le contrôle est enregistré même si le site refuse ou ne répond pas.
    sauver(index, {'controle_utc': now.isoformat()})
    try:
        urls = liens_index(fetch(f'{BASE}articles.php?date={day:%Y-%m}'))
    except (OSError, ValueError) as exc:
        sauver(index, {'controle_utc': now.isoformat(), 'statut': type(exc).__name__})
        return 0
    selected = [(url, heading, candidate) for url, heading in urls.items()
                for candidate in candidates if contient(heading, candidate[3])]
    pages = {}
    count = 0
    for url, heading, (course, key, number, name, departure) in selected:
        if (url not in pages and len(pages) >= 5) or clock() >= departure:
            continue
        path = directory/f'{key}.json'
        doc = lire(path)
        if any(r['url'] == url for r in doc.get(number, [])):
            continue
        try:
            if url not in pages:
                pages[url] = (fetch(url), clock())
            html, observed = pages[url]
            result = article(html, heading, course, name, observed) if observed < departure else None
        except (OSError, ValueError):
            break
        if result:
            doc.setdefault(number, []).append({**result, 'nom': name, 'url': url})
            sauver(path, doc)
            count += 1
    sauver(index, {'controle_utc': now.isoformat(), 'statut': 'LU', 'articles_retenus': count})
    return count


def champs_sheet(doc, number, name, departure, now):
    valid = [r for r in doc.get(str(number), []) if normaliser(r['nom']) == normaliser(name)
             and source_autorisee(r['url']) and (observed := instant(r['lecture_utc']))
             and departure and observed < departure and observed <= now]
    if not valid:
        return {}
    row = valid[-1]
    return {'avis_24h_trot': row['titre'],
            'source_24h_trot': f"{row['url']} · publié le {row['publication_date']} · lu {row['lecture_utc']}"}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='cache_pmu')
    args = parser.parse_args()
    print(f'AVIS_24H_TROT articles_retenus={collecter(args.cache)}', flush=True)
