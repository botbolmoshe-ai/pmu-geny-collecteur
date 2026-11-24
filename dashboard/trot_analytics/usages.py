"""Contrat commun de présentation des données évaluées et des données utilisées."""
from dataclasses import dataclass

EXPERIMENTAL = 'EXPÉRIMENTAL — NON UTILISÉ DANS LES PRONOSTICS'
PRODUCTION = 'UTILISÉ DANS LES PRONOSTICS'


def en_observation(usage):
    return usage == EXPERIMENTAL


@dataclass(frozen=True)
class Groupe:
    libelles: dict
    usage: str

    @property
    def italique(self):
        return en_observation(self.usage)


IPR = Groupe({
    'ipr_score': 'IPR · Score (/100)',
    'ipr_rang_shadow': 'IPR · Rang observé',
    'ipr_confiance': 'IPR · Confiance',
    'ipr_n_historiques_comparables': 'IPR · Courses comparables',
    'ipr_couverture': 'IPR · Couverture des preuves (%)',
    'ipr_version': 'IPR · Version',
    'ipr_calcul_utc': 'IPR · Calcul UTC',
    'ipr_statut': 'IPR · Statut',
    'ipr_motifs': 'IPR · Motifs',
}, EXPERIMENTAL)


GENY_HISTORIQUE = Groupe({
    'piste_geny': 'Geny · Piste',
    'corde_geny': 'Geny · Corde',
    'depart_geny': 'Geny · Départ',
    'terrain_geny': 'Geny · Terrain brut',
    'categorie_geny': 'Geny · Catégorie',
    'groupe_geny': 'Geny · Groupe',
    'allocation_geny_eur': 'Geny · Allocation (€)',
    'driver_geny': 'Geny · Driver / Jockey',
    'chrono_geny_sec_km': 'Geny · Chrono (s/km)',
    'cote_geny_historique': 'Geny · Cote historique',
    'geny_parsing_version': 'Geny · Version du parseur',
    'geny_parsing_motifs': 'Geny · Diagnostic du parseur',
    'texte_source': 'Geny · Texte brut',
    'url_source_geny': 'Geny · URL source',
}, EXPERIMENTAL)
