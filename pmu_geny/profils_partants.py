"""Signaux hippiques indépendants, évalués avec les preuves disponibles avant départ."""
from dataclasses import dataclass
from datetime import date
import re

from .echeances_production import PARIS, instant
from .formes_contextuelles_v32 import _classement, _discipline, _distance_factor

VERSION_PROFILS = 'trot-attele-v1'
CRACK = 'Crack'
HAUT_POTENTIEL = 'Haut potentiel'
PRIORITE = {CRACK: 2, HAUT_POTENTIEL: 1}
LIENS_VERIFIES = {
    'NOM_EXACT_UNIQUE', 'NOM_EXACT_ET_ID_GENY_CONFIRME',
    'NOM_AMBIGU_ID_CONFIRME', 'ID_GENY_MANIFESTE_VERIFIE',
}
GROUPE_ELITE = re.compile(r'(?:groupe|gr\.)\s*(?:I{1,2}|[12])', re.IGNORECASE)


@dataclass(frozen=True)
class Sortie:
    jour: date
    anciennete: int
    points: float | None
    proche: bool
    elite: bool


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
        elite = any(GROUPE_ELITE.fullmatch(cellule.strip()) for cellule in cellules[4:])
        signature = (ligne.get('hippodrome'), ligne.get('distance_m'), ligne.get('classement'),
                     ligne.get('texte_source'))
        jours.setdefault(jour, {})[signature] = Sortie(jour, anciennete, points, connue and distance >= .85, elite)
    return [next(iter(jours[jour].values())) if len(jours[jour]) == 1
            else Sortie(jour, (jour_course - jour).days, None, False, False)
            for jour in sorted(jours, reverse=True)]


def detecter_crack(sorties):
    """Un champion confirmé par ses résultats documentés en Groupe I ou II."""
    qualifiees = [sortie for sortie in sorties if sortie.points is not None]
    podiums_elite = [sortie for sortie in qualifiees if sortie.elite and sortie.points >= 2.5]
    victoires = sum(sortie.points == 5 for sortie in podiums_elite)
    if (len(qualifiees) >= 4 and len(podiums_elite) >= 2 and victoires >= 1
            and any(sortie.anciennete <= 120 for sortie in podiums_elite)):
        return f'{len(podiums_elite)} podiums en Groupe I/II, dont {victoires} victoire(s)'
    return None


def detecter_haut_potentiel(sorties, age):
    """Un jeune trotteur en progrès, avec des résultats proches de la distance cible."""
    if type(age) is not int or not 2 <= age <= 5 or len(sorties) < 6:
        return None
    if any(sortie.points is None for sortie in sorties[:6]):
        return None
    recentes, precedentes = sorties[:3], sorties[3:6]
    podiums = [sortie for sortie in recentes if sortie.points >= 2.5]
    progression = (sum(sortie.points for sortie in recentes)
                   - sum(sortie.points for sortie in precedentes)) / 3
    if (recentes[-1].anciennete <= 120 and len(podiums) >= 2
            and any(sortie.points == 5 for sortie in recentes)
            and any(sortie.proche for sortie in podiums) and progression >= 1):
        return f'{len(podiums)} podiums sur 3, forme en hausse (+{progression:.1f}/5)'
    return None
