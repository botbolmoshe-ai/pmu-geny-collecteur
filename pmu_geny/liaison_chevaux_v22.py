"""Lien stable entre partant PMU (course, numéro) et cheval Geny.

Le nom exact normalise est la cle logique d'identite, le numero de course sert
uniquement au rattachement du partant actuel. L'identifiant Geny stable peut
confirmer la correspondance et departager des homonymes.
"""
from __future__ import annotations
import re
import unicodedata
from pathlib import Path
from .ml_v19 import load

def nom_normalise(value):
    value=unicodedata.normalize('NFKD',str(value or '').upper())
    return ''.join(ch for ch in value if ch.isalnum() and not unicodedata.combining(ch))

def separer_pays_pmu(nom):
    countries = {'SWE': 'SE', 'ITY': 'IT', 'ITA': 'IT'}
    suffix = re.fullmatch(r'(.+?)\s*\((SWE|ITY|ITA)\)\s*', str(nom or ''), flags=re.I)
    return (suffix[1], countries[suffix[2].upper()]) if suffix else (nom, '')


def nom_geny_concordant(nom_pmu, fiche):
    """Les suffixes de pays PMU sont confirmés par la nationalité Geny."""
    expected = nom_normalise(nom_pmu)
    actual = nom_normalise(fiche.get('nom'))
    if not expected or not actual:
        return False
    if expected == actual:
        return True
    base, country = separer_pays_pmu(nom_pmu)
    return bool(country and country == fiche.get('nationalite_geny') and nom_normalise(base) == actual)


def etablir(cache, course, participants=None, *, index=None):
    from collections import Counter
    from .identites_chevaux import IndexGeny
    from .historiques_incrementaux import course_geny_connue

    cache = Path(cache)
    index = IndexGeny(cache) if index is None else index
    names = {}
    for h in participants or []:
        if not isinstance(h, dict):
            continue
        number = h.get('numero', h.get('numPmu'))
        if number is not None:
            names[str(number)] = h.get('nom', h.get('nomCheval', ''))
    ages = {str(h.get('numero', h.get('numPmu'))): str(h.get('age_ans', h.get('age', '')))
            for h in participants or [] if isinstance(h, dict)}
    ids_pmu = {str(h.get('numero', h.get('numPmu'))): h.get('id_pmu')
               for h in participants or [] if isinstance(h, dict)}
    counts = Counter(nom_normalise(name) for name in names.values())
    cid = course_geny_connue(cache, f"{course['date']}_{course['code']}")
    if cid:
        manifest = load(cache/'manifestes'/f'{cid}.json', {}) or {}
        for block in manifest.get('courses', []):
            if block.get('course_id') != cid:
                continue
            for h in block.get('partants', []):
                ident = str(h.get('id', ''))
                if ident in index.noms.get(nom_normalise(h.get('nom')), {}):
                    index.contextes[(nom_normalise(h['nom']), cid, str(h.get('numero', '')))].add(ident)
    matches = {}
    for number, name in names.items():
        age = ages[number]
        year = int(course['date'][:4]) - int(age) if age.isdigit() else None
        link, method = index.resoudre(name, cid, number, nom_repris=counts[nom_normalise(name)] > 1, annee=year, id_pmu=ids_pmu.get(number))
        ident = link.get('id', '')
        doc = {}
        if ident:
            doc = load(cache/'historiques'/ident/'historique_geny.json', {}) or {}
            if doc.get('statut') != 'COMPLET':
                partial = load(cache/'historiques_partiels'/ident/'historique_geny.json', {}) or {}
                if partial.get('identite_verifiee') is True:
                    doc = partial
            if (doc.get('statut') not in ('COMPLET', 'PARTIEL', 'PARTIEL_HISTORIQUE')
                    or not isinstance(doc.get('performances'), list)):
                doc = {}
        matches[number] = {'cheval_id': ident, 'historique': doc, 'methode': method}
    return matches
