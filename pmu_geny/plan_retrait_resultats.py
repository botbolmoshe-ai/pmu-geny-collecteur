"""Préparer le retrait des colonnes par jalon dans Résultats & Analyse, en lecture seule."""
from collections import Counter
from pathlib import Path
import argparse
import json

from .dates_registre import libelle_paris
from .sync_google_sheets import (
    DISPLAY_NAMES, ETAT_JALON_COLUMNS, SCORE_JALON_COLUMNS, canonical_headers, colname,
)

TAB = 'Résultats & Analyse'


def colonnes_jalons():
    fields = (*SCORE_JALON_COLUMNS, *ETAT_JALON_COLUMNS)
    projections = {libelle_paris(field, DISPLAY_NAMES.get(field, field)) for field in ETAT_JALON_COLUMNS}
    return set(fields) | projections


def planifier(headers):
    """Retourner les indices physiques sans modifier la feuille ni son schéma."""
    keys = canonical_headers(headers)
    duplicates = sorted(key for key, n in Counter(keys).items() if key and n > 1)
    if duplicates:
        raise ValueError(f'En-têtes ambigus dans {TAB} : {duplicates}')
    if 'course_key' not in keys:
        raise ValueError(f'Colonne clé absente dans {TAB}')
    selected = colonnes_jalons()
    retired = [(i, label) for i, (label, key) in enumerate(zip(headers, keys)) if key in selected]
    return {'onglet': TAB, 'retraits': [
        {'index': index, 'colonne': colname(index + 1), 'libelle': label} for index, label in retired
    ], 'en_tetes_attendus': [label for label, key in zip(headers, keys) if key not in selected]}


def verifier_projection(before, after, plan):
    """Contrôler la conservation des clés, valeurs et formules hors des colonnes retirées."""
    if len(before) != len(after) or not after or after[0] != plan['en_tetes_attendus']:
        raise ValueError('Dimensions ou en-têtes différents du plan de retrait')
    retired = {entry['index'] for entry in plan['retraits']}
    for index, (old, new) in enumerate(zip(before[1:], after[1:]), start=2):
        expected = [value for col, value in enumerate(old) if col not in retired]
        while expected and expected[-1] in ('', None):
            expected.pop()
        observed = list(new)
        while observed and observed[-1] in ('', None):
            observed.pop()
        if expected != observed:
            raise ValueError(f'Valeurs restantes différentes à la ligne {index}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('entetes', type=Path, help='JSON contenant les en-têtes tels que lus dans Sheets')
    args = parser.parse_args()
    print(json.dumps(planifier(json.loads(args.entetes.read_text())), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
