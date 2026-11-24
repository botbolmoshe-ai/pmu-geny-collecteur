"""Lecture conservatrice des lignes Geny archivées, sans I/O."""
import re
from collections import Counter

VERSION = "1"
FIELDS = (
    'piste_geny', 'corde_geny', 'depart_geny', 'terrain_geny', 'categorie_geny',
    'groupe_geny', 'allocation_geny_eur', 'driver_geny', 'chrono_geny_sec_km',
    'cote_geny_historique', 'geny_parsing_version', 'geny_parsing_motifs',
)
PROVENANCE = ('texte_source', 'url_source_geny')


def est_url(value):
    return isinstance(value, str) and bool(re.fullmatch(r'https?://[^\s|]+', value.strip(), re.I))


def structurer(texte):
    if not isinstance(texte, str) or not texte.strip() or est_url(texte):
        return {}
    result = {'geny_parsing_version': VERSION}
    parts = [p.strip() for p in texte.split('|')]
    if re.search(r'\bqualifications?\b', texte, re.I):
        return {**result, 'geny_parsing_motifs': 'qualification'}
    if (len(parts) < 5 or not re.fullmatch(r'\d{2}/\d{2}/\d{2,4}', parts[0])
            or not re.fullmatch(r'attel[eé]|mont[eé]', parts[2], re.I)
            or not re.fullmatch(r'\d{4}', ''.join(parts[3].split()))):
        return {**result, 'geny_parsing_motifs': 'structure_inconnue'}
    body = parts[4:]
    motifs = []

    def unique(field, candidates):
        if len(candidates) == 1:
            result[field] = candidates[0]
        elif candidates:
            motifs.append('ambigu_' + field)

    money = [(i, int(''.join(p[:-1].split()))) for i, p in enumerate(body)
             if re.fullmatch(r'\d[\d\s]*\s*€', p)]
    limit = money[0][0] if len(money) == 1 else len(body)
    context = body[:limit]
    context_patterns = []
    unique('allocation_geny_eur', [value for _, value in money])
    for field, pattern in (
        ('piste_geny', r'GP|PP|GPP'), ('corde_geny', r'G|D'),
        ('depart_geny', r'Auto'), ('terrain_geny', r'Dur|Herbe'),
        ('categorie_geny', r'Crse\s+([A-H])'), ('groupe_geny', r'Gr\.\s+(III|II|I)'),
    ):
        context_patterns.append(pattern)
        matches = [re.fullmatch(pattern, p, re.I) for p in context]
        unique(field, [m.group(m.lastindex or 0) for m in matches if m])
    if len(money) == 1 and any(
            p not in ('', '-') and not any(re.fullmatch(pattern, p, re.I) for pattern in context_patterns)
            for p in context):
        motifs.append('contexte_inconnu')
    chrono = re.compile(r"(\d)['’]([0-5]\d)(?:['’]{2}(\d+))?")
    matches = [chrono.fullmatch(p) for p in body]
    unique('chrono_geny_sec_km', [
        60 * int(m[1]) + int(m[2]) + float('0.' + (m[3] or '0'))
        for m in matches if m
    ])
    if len(money) == 1:
        tail = [p for p in body[limit + 1:] if p and p != '-']
        if tail and re.fullmatch(r"[^\W\d_][\w .’'\-]*", tail[0]) and re.search(r'\.\s*[^\W\d_]', tail[0]):
            result['driver_geny'] = tail.pop(0)
        if tail and chrono.fullmatch(tail[0]):
            tail.pop(0)
        if len(tail) >= 3 and tail[-2] == '/' and all(
                re.fullmatch(r'\d{1,2}:\d{2}', value) for value in (tail[-3], tail[-1])):
            tail = tail[:-3]
        if tail and tail[-1].casefold() in {'er', 'e', 'eme', 'ème', 'ᵉ'} and len(tail) >= 2 and tail[-2].isdigit():
            tail = tail[:-2]
        elif tail and re.fullmatch(r'\d{1,2}\s*(?:er|e|eme|ème|ᵉ)|Dpg|Dai|Di|Disq|Nc|NP|Arr|Dist|D|R|Tb', tail[-1], re.I):
            tail.pop()
        else:
            tail = []
            motifs.append('classement_non_reconnu')
        if len(tail) == 1 and re.fullmatch(r'\d+(?:[.,]\d+)?', tail[0]):
            odds = float(tail[0].replace(',', '.'))
            if odds >= 1:
                result['cote_geny_historique'] = odds
        elif tail:
            motifs.append('fin_de_ligne_inconnue')
    result['geny_parsing_motifs'] = ', '.join(motifs) or 'OK'
    return result


def couverture(rows):
    counts = Counter()
    motifs = Counter()
    versions = Counter()
    for row in rows:
        counts.update(field for field in FIELDS + PROVENANCE if row.get(field) not in ('', None))
        motifs.update(str(row.get('geny_parsing_motifs') or 'non analysé').split(', '))
        versions[str(row.get('geny_parsing_version') or 'non analysé')] += 1
    return {'lignes': len(rows), 'champs': dict(counts), 'motifs': dict(motifs), 'versions': dict(versions)}
