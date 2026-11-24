"""Plan additif appliqué aux seules performances déjà présentes dans le registre."""
from collections import Counter

from dashboard.trot_analytics.usages import GENY_HISTORIQUE

from .structure_geny import est_url, structurer


def planifier(headers, rows, archives):
    fields = tuple(GENY_HISTORIQUE.libelles)
    if len(set(h for h in headers if h)) != len([h for h in headers if h]):
        raise ValueError('En-têtes historiques ambigus')
    if 'cle_performance' not in headers or 'source_url' not in headers:
        raise ValueError('Schéma historique incompatible')
    keys = Counter(str(row.get('cle_performance') or '').strip() for row in rows)
    columns = headers + [field for field in fields if field not in headers]
    positions = {field: columns.index(field) + 1 for field in fields}
    updates, conflicts = [], Counter()
    for index, row in enumerate(rows, start=2):
        key = str(row.get('cle_performance') or '').strip()
        if not key or keys[key] != 1:
            continue
        archive = archives.get(key, {})
        legacy = row.get('source_url')
        text = row.get('texte_source') or (legacy if legacy and not est_url(legacy) else None) or archive.get('texte_source')
        url = legacy if est_url(legacy) else archive.get('url_source_geny')
        if isinstance(text, str) and text.startswith('='):
            text = archive.get('texte_source')
        data = structurer(text)
        if isinstance(text, str) and text.strip() and not est_url(text):
            data['texte_source'] = text
        if est_url(url):
            data['url_source_geny'] = url
        for field, value in data.items():
            before = row.get(field)
            if before in (None, ''):
                updates.append((index, positions[field], value))
            elif str(before) != str(value):
                conflicts[field] += 1
    return columns, updates, dict(conflicts), sum(n - 1 for k, n in keys.items() if k)


def verifier(before, after, headers, fields, updates):
    if len(before) != len(after) or after[0] != fields:
        raise ValueError('Dimensions modifiées après migration')
    expected = {(row, col): value for row, col, value in updates}
    for index, (old, new) in enumerate(zip(before[1:], after[1:]), start=2):
        old = old + [''] * (len(headers) - len(old))
        new = new + [''] * (len(fields) - len(new))
        restored = old + [''] * (len(fields) - len(headers))
        for col, value in enumerate(new, start=1):
            if value != expected.get((index, col), restored[col - 1]):
                raise ValueError(f'Écart après migration ligne {index}, colonne {col}')
