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
