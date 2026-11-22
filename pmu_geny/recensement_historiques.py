"""Suivi durable d'un passage de collecte sur tous les chevaux d'un hippodrome."""
from collections import Counter
from datetime import date
from pathlib import Path
import re

from .liaison_chevaux_v22 import nom_normalise


def ouvrir(cache, jour, hippodrome):
    from .historiques_incrementaux import lire

    if date.fromisoformat(jour).isoformat() != jour:
        raise ValueError('Date des courses attendue au format AAAA-MM-JJ')
    lieu = nom_normalise(hippodrome)
    if not lieu:
        raise ValueError('Hippodrome obligatoire')
    programme = lire(cache/'sources_pmu'/f'programme_{jour}.json').get('programme', [])
    lieux = {nom_normalise(c['hippodrome']) for c in programme if lieu in nom_normalise(c['hippodrome'])}
    if len(lieux) != 1:
        raise ValueError(f'Hippodrome absent ou ambigu dans le programme PMU du {jour}')
    lieu, = lieux
    courses = {c['code']: c for c in programme if nom_normalise(c['hippodrome']) == lieu}
    path = Path('collecte_incrementale/recensements') / f"{jour}_{re.sub(r'[^A-Z0-9]+', '_', lieu)}.json"
    ancien = lire(cache/path)
    suivi = {'date_courses': jour, 'hippodrome': lieu, 'courses': sorted(courses), 'chevaux': {}}
    for code, course in courses.items():
        engagement = f'{jour}_{code}'
        doc = lire(cache/'partants_actuels'/f'{engagement}.json')
        partants = doc.get('chevaux', {})
        if not partants or len(partants) < (course.get('nombre_declares') or 0):
            raise ValueError(f'Liste officielle absente ou incomplète pour {engagement}')
        for numero, cheval in partants.items():
            cle = f'{engagement}_{numero}'
            precedent = ancien.get('chevaux', {}).get(cle, {})
            nom = cheval.get('nom', '')
            ligne = precedent.copy() if precedent.get('nom') == nom else {'statut': 'A_EXAMINER'}
            if cheval.get('statut_np') == 'NON_PARTANT':
                ligne['statut'] = 'NON_PARTANT'
            elif ligne['statut'] == 'NON_PARTANT':
                ligne['statut'] = 'A_EXAMINER'
            suivi['chevaux'][cle] = {**ligne, 'nom': nom, 'course': code, 'numero': numero}
    return path, suivi


def tache(suivi, state, associations, pause, syncs):
    """N'utiliser que le périmètre demandé, y compris pour les reprises Sheets."""
    chevaux = state['chevaux']
    for contexte, ligne in suivi['chevaux'].items():
        cle = associations.get(contexte)
        if ligne['statut'] != 'A_PUBLIER':
            continue
        if cle in chevaux and cle not in syncs:
            return cle, 'SYNC'
        if cle not in chevaux:
            ligne.update(statut='PUBLICATION_A_REPRENDRE', motif='IDENTITE_NON_RECONCILIEE')
    for contexte, ligne in suivi['chevaux'].items():
        if ligne['statut'] != 'A_EXAMINER':
            continue
        cle = associations.get(contexte)
        cheval = chevaux.get(cle) or {}
        if not (cheval.get('geny') or cheval.get('course_url') or cheval.get('recherche_geny_par_nom')):
            ligne['statut'] = 'IDENTITE_NON_RESOLUE'
            continue
        if not pause:
            return cle, 'COLLECTE'
    if any(ligne['statut'] == 'A_EXAMINER' for ligne in suivi['chevaux'].values()):
        return None, 'COOLDOWN'
    return None, 'RECENSEMENT_TERMINE'


def lignes_associees(suivi, associations, key, statut):
    return [ligne for contexte, ligne in suivi['chevaux'].items()
            if associations.get(contexte) == key and ligne['statut'] == statut]


def bilan(suivi):
    chevaux = suivi['chevaux'].values()
    statuts = dict(Counter(ligne['statut'] for ligne in chevaux))
    return {'courses': len(suivi['courses']), 'chevaux': len(chevaux),
            'examines': len(chevaux) - statuts.get('A_EXAMINER', 0),
            'tentatives': sum('tentative_utc' in ligne for ligne in chevaux),
            'statuts': statuts}
