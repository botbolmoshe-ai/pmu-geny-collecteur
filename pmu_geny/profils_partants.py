"""Signaux hippiques indépendants, évalués avec les preuves disponibles avant départ."""
from dataclasses import dataclass
from datetime import date
import re

from .echeances_production import PARIS, instant
from .formes_contextuelles_v32 import _classement, _discipline, _distance_factor

VERSION_PROFILS = 'trot-attele-v2'
CRACK = 'Crack'
HAUT_POTENTIEL = 'Haut potentiel'
PRIORITE = {CRACK: 2, HAUT_POTENTIEL: 1}
LIENS_VERIFIES = {
    'NOM_EXACT_UNIQUE', 'NOM_EXACT_ET_ID_GENY_CONFIRME',
    'NOM_AMBIGU_ID_CONFIRME', 'ID_GENY_MANIFESTE_VERIFIE',
}
GROUPE = re.compile(r'(?:groupe|gr\.)\s*(I{1,3}|[123])', re.IGNORECASE)
NIVEAUX = {'I': 1, 'II': 2, 'III': 3, '1': 1, '2': 2, '3': 3}
DISQUALIFICATIONS = {'d', 'da', 'dai', 'di', 'disq', 'dpg'}
GAINS_MINIMUM_CRACK_EUROS = 250_000
SORTIES_MINIMUM_FIABILITE = 6
SORTIES_MAXIMUM_FIABILITE = 10
DISQUALIFICATIONS_MAX_CRACK_PCT = 20
DISQUALIFICATIONS_MAX_POTENTIEL_PCT = 10
ECART_MINIMUM_RENDEZ_VOUS_JOURS = 30


@dataclass(frozen=True)
class Sortie:
    jour: date
    anciennete: int
    points: float | None
    proche: bool
    groupe: int | None
    disqualifie: bool | None


def sorties_verifiees(course, lien, observation):
    """Une sortie par jour non ambigu, documentée avant la décision."""
    depart = instant(course.get('depart'))
    document = lien.get('historique') or {}
    capture = instant(document.get('extrait_utc'))
    if (_discipline(course.get('discipline')) != 'a' or not depart
            or not observation.tzinfo or observation >= depart
            or lien.get('methode') not in LIENS_VERIFIES or not lien.get('cheval_id')
            or document.get('statut') not in ('COMPLET', 'PARTIEL', 'PARTIEL_HISTORIQUE')
            or not document.get('source_url') or not capture or capture > observation):
        return []
    jour_course = depart.astimezone(PARIS).date()
    jour_capture = capture.astimezone(PARIS).date()
    jours = {}
    for ligne in document.get('performances', []):
        if not isinstance(ligne, dict) or _discipline(ligne.get('discipline')) != 'a':
            continue
        try:
            jour = date.fromisoformat(ligne.get('date'))
        except (ValueError, TypeError):
            continue
        anciennete = (jour_course - jour).days
        rang = str(ligne.get('classement') or '').strip().casefold()
        if not 1 <= anciennete <= 365 or jour > jour_capture or rang in ('np', 'non partant'):
            continue
        points = 0.0 if rang == 'tb' else _classement(rang)
        distance, connue = _distance_factor(course.get('distance_m'), ligne.get('distance_m'))
        cellules = str(ligne.get('texte_source') or '').split('|')
        groupes = {NIVEAUX[match[1].upper()] for cellule in cellules[4:]
                   if (match := GROUPE.fullmatch(cellule.strip()))}
        groupe = next(iter(groupes)) if len(groupes) == 1 else None
        disqualifie = rang in DISQUALIFICATIONS if points is not None and rang != 'r' else None
        signature = (ligne.get('hippodrome'), ligne.get('distance_m'), ligne.get('classement'),
                     ligne.get('texte_source'))
        jours.setdefault(jour, {})[signature] = Sortie(
            jour, anciennete, points, connue and distance >= .85, groupe, disqualifie)
    return [next(iter(jours[jour].values())) if len(jours[jour]) == 1
            else Sortie(jour, (jour_course - jour).days, None, False, None, None)
            for jour in sorted(jours, reverse=True)]


def _fiabilite_recente(sorties, maximum_pct):
    recentes = sorties[:SORTIES_MAXIMUM_FIABILITE]
    if len(recentes) < SORTIES_MINIMUM_FIABILITE or any(
            sortie.disqualifie is None for sortie in recentes):
        return None
    disqualifications = sum(sortie.disqualifie for sortie in recentes)
    if 100 * disqualifications <= maximum_pct * len(recentes):
        return f'{disqualifications} disq. sur {len(recentes)}'
    return None


def detecter_crack(sorties, gains_euros):
    """Un champion de Groupe I/II dont les gains et la fiabilité sont documentés."""
    if (type(gains_euros) not in (int, float)
            or not GAINS_MINIMUM_CRACK_EUROS <= gains_euros < 100_000_000):
        return None
    fiabilite = _fiabilite_recente(sorties, DISQUALIFICATIONS_MAX_CRACK_PCT)
    if fiabilite is None:
        return None
    podiums_elite = [sortie for sortie in sorties if sortie.groupe in (1, 2)
                     and sortie.points is not None and sortie.points >= 2.5]
    victoires = sum(sortie.points == 5 for sortie in podiums_elite)
    if (len(podiums_elite) >= 2 and victoires >= 1
            and any(sortie.anciennete <= 120 for sortie in podiums_elite)):
        gains = f'{gains_euros:,.2f}'.removesuffix('.00').replace(',', '\u202f').replace('.', ',')
        victoires_libelle = 'victoire' if victoires == 1 else 'victoires'
        return (f'{len(podiums_elite)} podiums en Groupe I/II, dont {victoires} {victoires_libelle}'
                f' · {gains} € de gains carrière · {fiabilite}')
    return None


def detecter_haut_potentiel(sorties, age):
    """Un jeune trotteur en progrès, avec des résultats proches de la distance cible."""
    if type(age) is not int or not 2 <= age <= 5:
        return None
    fiabilite = _fiabilite_recente(sorties, DISQUALIFICATIONS_MAX_POTENTIEL_PCT)
    if fiabilite is None:
        return None
    rendez_vous = [sortie for sortie in sorties if sortie.groupe is not None
                   and sortie.points is not None]
    if (len(rendez_vous) < 2 or rendez_vous[0].anciennete > 120
            or rendez_vous[-1].anciennete - rendez_vous[0].anciennete < ECART_MINIMUM_RENDEZ_VOUS_JOURS):
        return None
    recentes, precedentes = sorties[:3], sorties[3:6]
    podiums = [sortie for sortie in recentes if sortie.points >= 2.5]
    progression = (sum(sortie.points for sortie in recentes)
                   - sum(sortie.points for sortie in precedentes)) / 3
    if (recentes[-1].anciennete <= 120 and len(podiums) >= 2
            and any(sortie.points == 5 for sortie in recentes)
            and any(sortie.proche for sortie in podiums) and progression >= 1):
        hausse = f'{progression:.1f}'.replace('.', ',')
        return (f'{len(podiums)} podiums sur 3, forme en hausse (+{hausse}/5)'
                f' · {fiabilite} · {len(rendez_vous)} sorties en Groupe I–III')
    return None
