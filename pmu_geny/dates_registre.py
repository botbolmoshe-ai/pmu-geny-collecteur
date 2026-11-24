"""Projection des horodatages Sheets sans perte des instants utilisés par la production."""
from dashboard.trot_analytics.dates import (
    DISPLAY_PREFIX, date_kind, depuis_nombre, afficher_source, instant_iso,
    indicateur_horodate, nombre_paris,
)

SOURCES = {
    'source_pmu': 'Source PMU · URL et collecte',
    'source_24h_trot': '24H au Trot · Source et lecture',
}


def libelle_paris(field, label):
    if field in SOURCES:
        return DISPLAY_PREFIX + SOURCES[field]
    return DISPLAY_PREFIX + label.removesuffix(' UTC').removesuffix('_utc').removesuffix(' (Paris)')


def projection(field, value):
    if field in SOURCES:
        return afficher_source(value)
    if value in ('', None):
        return ''
    # Toute série numérique préexistante suit la convention propre à la colonne.
    # Le départ est déjà encodé en heure locale, même pendant l'heure répétée.
    if field == 'heure_depart_paris' and type(value) in (float, int):
        return value
    raw = depuis_nombre(field, value)
    return nombre_paris(raw, utc=field != 'heure_depart_paris')


def colonnes_projection(headers, labels):
    fields = {}
    for index, field in enumerate(headers):
        if date_kind(field) != 'DATE_TIME' and field not in SOURCES:
            continue
        try:
            target = headers.index(libelle_paris(field, labels[index]))
        except ValueError:
            continue
        fields[index] = target
    return fields


def enrichir_publication(tab, headers, updates, appends):
    from .sync_google_sheets import DISPLAY_NAMES, SHEET_HEADER_LABELS
    labels = {**DISPLAY_NAMES, **SHEET_HEADER_LABELS.get(tab, {})}
    columns = colonnes_projection(headers, [labels.get(field, field) for field in headers])
    projected = [(row, columns[col - 1] + 1, projection(headers[col - 1], value))
                 for row, col, value in updates if col - 1 in columns]
    for row in appends:
        for source, target in columns.items():
            row[target] = projection(headers[source], row[source])
    return updates + projected


def nombre_kpi(value, label, *, legacy=False):
    if instant_iso(value) or (legacy and indicateur_horodate(label)):
        return nombre_paris(value)
    return value
