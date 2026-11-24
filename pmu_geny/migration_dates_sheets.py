"""Migration ciblée des champs de consultation du classeur existant."""
import argparse
from collections import Counter
from datetime import timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

from dashboard.trot_analytics.dates import (
    DATE_PATTERN, DATETIME_PATTERN, TIME_PATTERN, date_kind, lire_instant_consultation, vers_nombre,
)
from .audit_dates_sheets import TABS, pages
from .dates_registre import SOURCES, libelle_paris, nombre_kpi, projection
from .lectures_sheets import get_lecture
from .moteur_sheets import SynchroniseurSheets, verrou_local
from .sync_google_sheets import DISPLAY_NAMES, SHEET_HEADER_LABELS, canonical_headers

PATTERNS = {'DATE': DATE_PATTERN, 'DATE_TIME': DATETIME_PATTERN, 'TIME': TIME_PATTERN}


def range_cell(sheet, row, col):
    return {'sheetId': sheet, 'startRowIndex': row - 1, 'endRowIndex': row,
            'startColumnIndex': col, 'endColumnIndex': col + 1}


def format_cell(sheet, row, col, kind, note=None):
    cell = {'userEnteredFormat': {'numberFormat': {'type': kind, 'pattern': PATTERNS[kind]}}}
    fields = 'userEnteredFormat.numberFormat'
    if note:
        cell['note'] = note
        fields += ',note'
    return {'repeatCell': {'range': range_cell(sheet, row, col), 'cell': cell, 'fields': fields}}


def entered(cell):
    return cell.get('userEnteredValue', {})


def raw(cell):
    value = entered(cell)
    return value.get('numberValue', value.get('stringValue', ''))


def hide_column(sheet, col):
    return {'updateDimensionProperties': {
        'range': {'sheetId': sheet, 'dimension': 'COLUMNS', 'startIndex': col, 'endIndex': col + 1},
        'properties': {'hiddenByUser': True}, 'fields': 'hiddenByUser',
    }}


def current_format(cell):
    return cell.get('effectiveFormat', {}).get('numberFormat', {})


def same_value(actual, expected):
    if type(expected) in (float, int) and type(actual) in (float, int):
        return math.isclose(actual, expected, abs_tol=1e-10, rel_tol=0)
    return type(actual) is type(expected) and actual == expected


def write_column(sheet, col, changes):
    requests = []
    for row, value in sorted(changes.items()):
        key = 'numberValue' if type(value) in (int, float) else 'stringValue'
        cell = {'userEnteredValue': {key: value}} if value != '' else {}
        if requests and row == requests[-1]['updateCells']['range']['endRowIndex'] + 1:
            block = requests[-1]['updateCells']
            block['range']['endRowIndex'] = row
            block['rows'].append({'values': [cell]})
        else:
            requests.append({'updateCells': {
                'range': range_cell(sheet, row, col), 'rows': [{'values': [cell]}],
                'fields': 'userEnteredValue',
            }})
    return requests


def planifier(tab, props, rows):
    sheet = props['sheetId']
    header = rows.get(1, [])
    names = [raw(cell) for cell in header]
    while names and not names[-1]:
        names.pop()
    headers = canonical_headers(names)
    updates = {}
    requests = []
    ignored = Counter()
    hidden = []
    width = props['gridProperties']['columnCount']
    targets = {}
    new_columns = set()
    mixed = {'Data Quality & KPI': (1, 2), 'Historique qualité': (4, 5)}.get(tab)
    # Le TCD peut comporter des formules et des colonnes sans en-tête.
    # Seules les cellules déjà reconnues comme dates/heures y sont formatées.
    if tab in TABS[:3] or tab == 'Historique qualité':
        labels = {**DISPLAY_NAMES, **SHEET_HEADER_LABELS.get(tab, {})}
        for col, field in enumerate(headers):
            if not field or (date_kind(field) != 'DATE_TIME' and field not in SOURCES):
                continue
            # Une formule existante et ses dépendances restent visibles.
            if any('formulaValue' in entered(cells[col]) for n, cells in rows.items()
                   if n > 1 and col < len(cells)):
                ignored[f'formule:{field}'] += 1
                continue
            label = libelle_paris(field, labels.get(field, names[col]))
            if label not in names:
                names.append(label)
                target = len(names) - 1
                new_columns.add(target)
                updates.setdefault(target, {})[1] = label
            target = names.index(label)
            targets[col] = (field, target)
            hidden.append(col)
            if field not in SOURCES:
                requests.append({'repeatCell': {
                    'range': {'sheetId': sheet, 'startRowIndex': 1,
                              'startColumnIndex': target, 'endColumnIndex': target + 1},
                    'cell': {'userEnteredFormat': {
                        'numberFormat': {'type': 'DATE_TIME', 'pattern': DATETIME_PATTERN}}},
                    'fields': 'userEnteredFormat.numberFormat',
                }})
            if field == 'ipr_calcul_utc':
                requests.append({'repeatCell': {
                    'range': {'sheetId': sheet, 'startColumnIndex': target, 'endColumnIndex': target + 1},
                    'cell': {'userEnteredFormat': {'textFormat': {'italic': True}}},
                    'fields': 'userEnteredFormat.textFormat.italic',
                }})
    for row, cells in rows.items():
        if row == 1:
            continue
        for col, cell in enumerate(cells):
            field = headers[col] if col < len(headers) else ''
            value = raw(cell)
            if col in targets:
                source, target = targets[col]
                expected = projection(source, value)
                if source not in SOURCES and expected != '' and type(expected) not in (int, float):
                    ignored[f'valeur:{source}'] += 1
                if source in SOURCES and isinstance(value, str) and value.startswith(('https://', 'http://')):
                    from .audit_dates_sheets import categorie
                    if categorie(cell) == 'URL et instant' and expected == value:
                        ignored[f'provenance:{source}'] += 1
                existing = cells[target] if target < len(cells) else {}
                if 'formulaValue' in entered(existing):
                    raise ValueError(f'Formule inattendue dans la projection {tab}/{row}/{target}')
                if not same_value(raw(existing), expected):
                    updates.setdefault(target, {})[row] = expected
            elif mixed and col == mixed[1] and mixed[0] < len(cells):
                expected = nombre_kpi(value, raw(cells[mixed[0]]), legacy=True)
                if type(expected) in (int, float) and not same_value(value, expected):
                    updates.setdefault(col, {})[row] = expected
                    note = '\n'.join(filter(None, (
                        cell.get('note'),
                        f'Affichage Europe/Paris. Valeur source UTC avant migration : {value}',
                    )))
                    requests.append(format_cell(sheet, row, col, 'DATE_TIME', note=note))
                elif lire_instant_consultation(value, timezone.utc) and type(value) is str:
                    ignored[f'KPI:{raw(cells[mixed[0]])}'] += 1
            elif date_kind(field) == 'DATE':
                expected = vers_nombre(field, value)
                if type(expected) in (int, float) and not same_value(value, expected):
                    updates.setdefault(col, {})[row] = expected
                    requests.append(format_cell(sheet, row, col, 'DATE'))
            if col not in targets and 'numberValue' in cell.get('effectiveValue', {}):
                fmt = current_format(cell)
                kind = fmt.get('type')
                if (kind in PATTERNS and (date_kind(field) == kind or tab == 'TCD')
                        and fmt.get('pattern', '').lower() != PATTERNS[kind]):
                    requests.append(format_cell(sheet, row, col, kind))
    if len(names) > width:
        requests.insert(0, {'appendDimension': {
            'sheetId': sheet, 'dimension': 'COLUMNS', 'length': len(names) - width,
        }})
    for col, changes in updates.items():
        if col in new_columns:
            if any(len(cells) > col and (entered(cells[col]) or cells[col].get('effectiveValue'))
                   for cells in rows.values()):
                raise ValueError(f'Une colonne sans en-tête contient déjà des données : {tab}/{col}')
            dense = {row: changes.get(row, '') for row in range(1, max(changes) + 1)}
            requests.extend(write_column(sheet, col, dense))
        else:
            requests.extend(write_column(sheet, col, changes))
    requests.extend(hide_column(sheet, col) for col in hidden)
    return requests, updates, ignored


def snapshot(engine):
    tables = engine.metadata()
    return {tab: (tables[tab], dict(pages(engine, tab, tables[tab]))) for tab in TABS}


def empreinte(snapshot_data):
    values = {
        tab: [props['gridProperties'], {
            row: [{"value": entered(cell), "format": cell.get("userEnteredFormat", {}),
                   "note": cell.get("note", "")}
                  for cell in cells]
            for row, cells in rows.items()
        }]
        for tab, (props, rows) in snapshot_data.items()
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verifier(before, after, updates):
    for tab, (_, rows) in before.items():
        observed = after[tab][1]
        changes = updates[tab]
        for index in rows.keys() | observed.keys():
            old = rows.get(index, [])
            new = observed.get(index, [])
            for col in range(max(len(old), len(new))):
                left = entered(old[col]) if col < len(old) else {}
                right = entered(new[col]) if col < len(new) else {}
                if index in changes.get(col, {}):
                    expected = changes[col][index]
                    if not same_value(raw(new[col]) if col < len(new) else '', expected):
                        raise ValueError(f'Relecture différente pour {tab}/{index}/{col}')
                    if type(expected) in (int, float):
                        fmt = current_format(new[col])
                        if (fmt.get('type') not in PATTERNS
                                or fmt.get('pattern', '').lower() != PATTERNS[fmt['type']]):
                            raise ValueError(f'Format natif absent dans {tab}/{index}/{col}')
                elif left != right:
                    raise ValueError(f'Valeur hors migration modifiée dans {tab}/{index}/{col}')


def migrer(engine, archive, *, appliquer=False):
    with verrou_local(engine.spreadsheet):
        doc = engine.check(get_lecture(engine.session, engine.base, params={
            'fields': 'properties(locale,timeZone)',
        }, timeout=30))
        if doc.get('properties') != {'locale': 'fr_FR', 'timeZone': 'Europe/Paris'}:
            raise ValueError('Locale ou fuseau du registre inattendu')
        before = snapshot(engine)
        plans = {tab: planifier(tab, props, rows) for tab, (props, rows) in before.items()}
        summary = {tab: {'requêtes': len(plan[0]), 'cellules': sum(map(len, plan[1].values())),
                         'à examiner': dict(plan[2])} for tab, plan in plans.items()}
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        unknown_count = sum(sum(plan[2].values()) for plan in plans.values())
        print(f'REGISTRE_DATES_A_EXAMINER={unknown_count}', flush=True)
        if unknown_count:
            raise ValueError('Des dates de consultation restent à examiner')
        if not appliquer:
            with gzip.open(archive, 'xt', encoding='utf-8') as out:
                json.dump({'empreinte': empreinte(before), 'onglets': before}, out,
                          ensure_ascii=False, separators=(',', ':'))
            return
        requests = [request for plan in plans.values() for request in plan[0]]
        with gzip.open(archive, 'rt', encoding='utf-8') as saved:
            if json.load(saved)['empreinte'] != empreinte(before):
                raise ValueError('Le registre a évolué depuis la sauvegarde')
        engine.check(engine.session.post(engine.base + ':batchUpdate',
                                         json={'requests': requests}, timeout=120))
        after = snapshot(engine)
        verifier(before, after, {tab: plan[1] for tab, plan in plans.items()})
        for tab, (props, rows) in after.items():
            _, changes, unknown = planifier(tab, props, rows)
            if changes or unknown:
                raise ValueError(f'Migration non idempotente après relecture de {tab}')
        print('MIGRATION_DATES_SHEETS_VERIFIEE=6', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--appliquer', action='store_true')
    parser.add_argument('--sauvegarde', type=Path, required=True)
    args = parser.parse_args()
    engine = SynchroniseurSheets('.', os.environ['GOOGLE_SHEETS_ID'])
    try:
        migrer(engine, args.sauvegarde, appliquer=args.appliquer)
    finally:
        engine.fermer()


if __name__ == '__main__':
    main()
