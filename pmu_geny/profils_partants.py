"""Signaux hippiques indépendants, évalués avec les preuves disponibles avant départ."""
from dataclasses import dataclass
from datetime import date
import re

from dashboard.trot_analytics.profils import (
    AUCUN_PROFIL, CRACK_CONFIRME, HAUT_POTENTIEL, NON_EVALUABLE, SEPARATEUR_PROFILS,
)

from .echeances_production import PARIS, instant
from .formes_contextuelles_v32 import _classement, _discipline, _distance_factor

VERSION_PROFILS = 'trot-attele-v3'
SIGNAUX_PROFILS = ('est_crack', 'est_haut_potentiel')
CRACK = 'Crack'
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


def _fenetre_documentee(sorties):
    return (len(sorties) >= SORTIES_MINIMUM_FIABILITE and all(
        sortie.disqualifie is not None for sortie in sorties[:SORTIES_MAXIMUM_FIABILITE]))


def _fiabilite_recente(sorties, maximum_pct):
    recentes = sorties[:SORTIES_MAXIMUM_FIABILITE]
    if not _fenetre_documentee(sorties):
        return None
    disqualifications = sum(sortie.disqualifie for sortie in recentes)
    if 100 * disqualifications <= maximum_pct * len(recentes):
        return f'{disqualifications} disq. sur {len(recentes)}'
    return None


def _gains_documentes(gains):
    return type(gains) in (int, float) and 0 <= gains < 100_000_000


def detecter_crack(sorties, gains_euros):
    """Un champion de Groupe I/II dont les gains et la fiabilité sont documentés."""
    if not _gains_documentes(gains_euros) or gains_euros < GAINS_MINIMUM_CRACK_EUROS:
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


def evaluer_profils(course, lien, profil, observation):
    """Conserver les deux décisions et les preuves du même relevé pré-départ."""
    partant_confirme = profil.get('statut_np') == 'PARTANT'
    sorties = sorties_verifiees(course, lien, observation) if partant_confirme else []
    gains, age = profil.get('gains_euros'), profil.get('age_ans')
    crack = detecter_crack(sorties, gains)
    potentiel = detecter_haut_potentiel(sorties, age)
    motif = None
    if not partant_confirme:
        motif = 'Statut de partant non confirmé'
    elif _discipline(course.get('discipline')) != 'a':
        motif = 'Règles réservées au trot attelé'
    elif not sorties:
        motif = 'Historique pré-départ vérifié indisponible'
    elif not _fenetre_documentee(sorties):
        motif = 'Au moins six sorties récentes avec résultat interprétable sont requises'
    motif_crack = motif or (None if _gains_documentes(gains) else 'Gains PMU indisponibles')
    _, distance_connue = _distance_factor(course.get('distance_m'), course.get('distance_m'))
    motif_potentiel = motif
    if not motif_potentiel:
        if type(age) is not int or age <= 0:
            motif_potentiel = 'Âge PMU indisponible'
        elif 2 <= age <= 5 and not distance_connue:
            motif_potentiel = 'Distance cible indisponible'
    signal = {
        'nom': profil['nom'],
        'statut': CRACK if crack else HAUT_POTENTIEL if potentiel else '',
        'est_crack': bool(crack) if motif_crack is None else None,
        'est_haut_potentiel': bool(potentiel) if motif_potentiel is None else None,
        'crack': crack,
        'haut_potentiel': potentiel,
        'motif_crack': motif_crack,
        'motif_haut_potentiel': motif_potentiel,
        'gains_carriere_euros': gains,
        'age_ans': age,
        'version_profils': VERSION_PROFILS,
        'calcule_sur_releve_utc': observation.isoformat(),
        'sorties_verifiees': sum(sortie.points is not None for sortie in sorties),
        'sorties_observees': len(sorties),
    }
    if sorties:
        signal.update(
            historique_extrait_utc=lien['historique']['extrait_utc'],
            source_historique=lien['historique']['source_url'],
            identifiant_historique=lien['cheval_id'],
        )
    return signal


def afficher_profils(signal):
    """Projeter les preuves enregistrées dans les deux colonnes existantes."""
    etiquettes, indices = [], []
    for key, label in (('crack', CRACK_CONFIRME), ('haut_potentiel', HAUT_POTENTIEL)):
        preuve = signal.get(key)
        etat = signal.get('est_' + key, bool(preuve))
        if etat and preuve:
            etiquettes.append(label)
            indices.append(f'{label} : {preuve}')
        elif etat is None:
            indices.append(f"{label} : {signal.get('motif_' + key) or NON_EVALUABLE}")
        elif 'est_' + key in signal:
            indices.append(f'{label} : critères non atteints')
    if 'version_profils' in signal:
        if not etiquettes:
            etiquettes.append(NON_EVALUABLE if any(
                signal.get(key) is None for key in ('est_crack', 'est_haut_potentiel')
            ) else AUCUN_PROFIL)
        indices.extend((f"{signal['sorties_verifiees']}/{signal['sorties_observees']} sorties interprétables",
                        f"{signal['version_profils']} · relevé {signal['calcule_sur_releve_utc']}"))
        if signal.get('source_historique'):
            indices.append(f"Geny : {signal['source_historique']} · extrait {signal['historique_extrait_utc']}")
        if signal.get('calcul_utc'):
            indices.append(f"Calcul : {signal['calcul_utc']}")
    return SEPARATEUR_PROFILS.join(etiquettes), '\n'.join(indices)
