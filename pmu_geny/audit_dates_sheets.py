"""Inventaire en lecture seule des valeurs et formats du registre de production."""
import json
from collections import Counter
from datetime import datetime

from dashboard.trot_analytics.dates import instant_iso
from .lectures_sheets import get_lecture
from .moteur_sheets import SynchroniseurSheets
from .sync_google_sheets import SHEET_TABS, colname

TABS = (*SHEET_TABS, 'Data Quality & KPI', 'TCD', 'Historique qualité')


def categorie(cell):
    value = cell.get('userEnteredValue', {})
    if 'formulaValue' in value:
        return 'formule'
    kind = cell.get('effectiveFormat', {}).get('numberFormat', {})
    if 'numberValue' in value:
        if kind.get('type') in ('DATE', 'DATE_TIME', 'TIME'):
            return f"natif:{kind['type']}:{kind.get('pattern', '')}"
        return 'nombre'
    raw = value.get('stringValue')
    if not raw:
        return 'vide' if not value else 'autre'
    if instant_iso(raw):
        return 'ISO instant'
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%Y %H:%M',
                '%d/%m/%Y %H:%M:%S', '%H:%M', '%H:%M:%S'):
        try:
            datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return f'texte:{fmt}'
    if raw.startswith('https://') and any(instant_iso(word) for word in raw.split()):
        return 'URL et instant'
    return 'texte'


def pages(engine, tab, props):
    grid = props['gridProperties']
    page_size = min(2000, max(1, 80000 // grid['columnCount']))
    for start in range(1, grid['rowCount'] + 1, page_size):
        end = min(start + page_size - 1, grid['rowCount'])
        result = engine.check(get_lecture(engine.session, engine.base, params={
            'ranges': f"'{tab}'!A{start}:{colname(grid['columnCount'])}{end}",
            'fields': 'sheets(properties(sheetId),data(startRow,startColumn,rowData(values('
                      'userEnteredValue,effectiveValue,effectiveFormat(numberFormat),'
                      'userEnteredFormat(numberFormat)))))',
        }, timeout=60))
        sheets = result['sheets']
        if len(sheets) != 1 or sheets[0]['properties']['sheetId'] != props['sheetId']:
            raise ValueError(f'Réponse Sheets inattendue pour {tab}')
        for block in sheets[0].get('data', []):
            if block.get('startRow', 0) != start - 1 or block.get('startColumn', 0):
                raise ValueError(f'Plage Sheets inattendue pour {tab}')
            for index, row in enumerate(block.get('rowData', []), start):
                yield index, row.get('values', [])


def inventorier(engine):
    tables = engine.metadata()
    report = {}
    for tab in TABS:
        props = tables[tab]
        headers = []
        counts = {}
        for row, cells in pages(engine, tab, props):
            if row == 1:
                headers = [cell.get('effectiveValue', {}).get('stringValue', '') for cell in cells]
                continue
            for index, cell in enumerate(cells):
                category = categorie(cell)
                if category != 'vide':
                    counts.setdefault(index, Counter())[category] += 1
        report[tab] = {
            'grille': props['gridProperties'],
            'colonnes': [
                {'colonne': colname(index + 1), 'en_tete': headers[index] if index < len(headers) else '',
                 'formats': dict(counter)}
                for index, counter in sorted(counts.items())
            ],
        }
    return report


if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path

    engine = SynchroniseurSheets('.', os.environ['GOOGLE_SHEETS_ID'])
    try:
        report = inventorier(engine)
        Path(sys.argv[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        for tab, data in report.items():
            for column in data['colonnes']:
                formats = {key: count for key, count in column['formats'].items()
                           if key not in ('texte', 'nombre')}
                if formats:
                    print(json.dumps([tab, column['colonne'], column['en_tete'], formats],
                                     ensure_ascii=False), flush=True)
    finally:
        engine.fermer()
