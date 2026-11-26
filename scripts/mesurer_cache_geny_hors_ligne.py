import argparse
from collections import Counter
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit
import json
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from pmu_geny.collecte_geny_v4 import parse_career
from pmu_geny.ferrures_geny import enrichir
from pmu_geny.historique_individuel import observer_cache_chromium, observer_http_geny

parser = argparse.ArgumentParser(description="Mesurer le cache Chromium sur 30 captures de pmu-data, hors réseau externe.")
parser.add_argument('--source', required=True, type=Path)
parser.add_argument('--chromium', help="Exécutable Chromium local, sinon celui de Playwright")
args_cli = parser.parse_args()
ref = args_cli.source
documents = {}
for html in sorted((ref/'diagnostics').rglob('diagnostic_geny.html')):
    ident = html.parent.name
    raw = html.read_text()
    text = html.with_name('diagnostic_texte_geny.txt').read_text()
    try:
        parsed = parse_career(text, [])
    except ValueError:
        continue
    if not parsed['complet'] or not parsed['nombre_extrait'] or not ident.isdigit():
        continue
    enrichir(parsed, raw, ident, f'https://www.geny.com/cheval/{ident}', '2026-11-26T03:06:00+00:00')
    soup = BeautifulSoup(raw, 'html.parser')
    resources = {urlsplit(tag['src']).path for tag in soup.find_all('script', src=True)
                 if urlsplit(tag['src']).path.startswith('/_next/static/')}
    documents['/cheval/'+ident] = ((
        '<!doctype html><meta charset=utf-8><pre>' + escape(text) + '</pre>' +
        ''.join(f'<script src="{escape(route)}" defer></script>' for route in sorted(resources)) +
        '<img src="/512.png">'
    ).encode(), parsed, ident, raw)
    if len(documents) == 30:
        break
assert len(documents) == 30
counts = Counter()
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in documents:
            kind, body = 'document', documents[path][0]
        elif path.startswith('/_next/static/'):
            kind, body = 'script', b'/* immutable fixture */'
        else:
            kind, body = 'image' if path.endswith('.png') else 'other', b''
        counts[kind] += 1
        self.send_response(200)
        self.send_header('Content-Type', {'document': 'text/html', 'script': 'text/javascript'}.get(kind, 'image/png'))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'public, max-age=31536000, immutable' if kind == 'script' else 'no-store')
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
Thread(target=server.serve_forever, daemon=True).start()
root = f'http://www.geny.com:{server.server_port}'
args = ['--no-proxy-server', '--host-resolver-rules=MAP www.geny.com 127.0.0.1, MAP * ~NOTFOUND']
summary = {}
with sync_playwright() as playwright, TemporaryDirectory() as profile:
    for label in ('avant', 'apres'):
        counts.clear()
        start = time.monotonic()
        hits = Counter()
        ns = 0
        distinct = []
        for url, (_, evidence, ident, raw) in documents.items():
            if label == 'avant':
                browser = playwright.chromium.launch(executable_path=args_cli.chromium, args=args)
                context = browser.new_context()
                page = context.new_page()
            else:
                context = playwright.chromium.launch_persistent_context(profile,
                    executable_path=args_cli.chromium, args=args + ['--blink-settings=imagesEnabled=false'])
                page = context.pages[0]
            measure = observer_http_geny(context)
            observer_cache_chromium(context, page, measure)
            page.goto(root+url, wait_until='load')
            rows = parse_career(page.locator('body').inner_text(), [])
            enrichir(rows, raw, ident, 'https://www.geny.com/cheval/'+ident, '2026-11-26T03:06:00+00:00')
            assert evidence == rows, (url, label)
            ns += rows['nombre_extrait']
            distinct.append(ident)
            hits.update(measure['cache_http_par_ressource'])
            if label == 'apres':
                page.goto('about:blank')
            context.close()
            if label == 'avant':
                browser.close()
        summary[label] = {'duree_secondes': round(time.monotonic()-start, 2),
                          'appels_effectifs': dict(counts), 'cache_hits': dict(hits),
                          'carrieres': len(distinct), 'performances': ns}
print(json.dumps(summary, indent=2))
server.shutdown()
