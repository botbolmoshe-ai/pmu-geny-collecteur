"""Contrat commun de publication du rapprochement PMU–Geny."""

CHAMP = 'statut_correspondance_geny'
COLONNE = 'Correspondance PMU–Geny'
CONFIRMEE = 'CORRESPONDANCE_CONFIRMEE'
NON_TROUVEE = 'CORRESPONDANCE_NON_TROUVEE'
AMBIGUE = 'CORRESPONDANCE_AMBIGUE'
BLOQUEE = 'RECHERCHE_BLOQUEE'
NON_EFFECTUEE = 'RECHERCHE_NON_EFFECTUEE'

STATUTS = {
    CONFIRMEE: ('Correspondance Geny confirmée', '#DCFCE7'),
    NON_TROUVEE: ('Correspondance Geny non trouvée', '#FEE2E2'),
    AMBIGUE: ('Correspondance Geny ambiguë', '#FEF3C7'),
    BLOQUEE: ('Recherche Geny bloquée', '#FFEDD5'),
    NON_EFFECTUEE: ('Recherche Geny non effectuée', '#E5E7EB'),
}
KPI_PREFIX = 'Correspondance Geny · '


def statut_ligne(row):
    value = row.get(COLONNE) or row.get(CHAMP)
    return value if value in STATUTS else NON_EFFECTUEE


def libelle_historique(value):
    if str(value or '').startswith('HISTO_OK'):
        return 'Carrière validée et publiée'
    return {
        'HISTO_PARTIEL_GENY': 'Historique partiel',
        'HISTO_PUBLICATION_EN_ATTENTE': 'Publication en attente',
        'GENY_IDENTIFIE_CARRIERE_MANQUANTE': 'Carrière à collecter',
        'HISTO_NON_COLLECTE': 'Historique absent',
        'HISTO_AMBIGU': 'Identité à vérifier',
    }.get(value, 'État indisponible')
