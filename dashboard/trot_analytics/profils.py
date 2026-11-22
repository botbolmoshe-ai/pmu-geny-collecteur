"""Libellés et couleurs communs au registre et à Streamlit."""

CRACK_CONFIRME = 'Crack confirmé'
HAUT_POTENTIEL = 'Haut potentiel'
NON_EVALUABLE = 'Non évaluable'
AUCUN_PROFIL = 'Aucun profil'
SEPARATEUR_PROFILS = ' + '
# Fond, texte et symbole. Le violet/or est prioritaire en cas de cumul.
PALETTE = {
    CRACK_CONFIRME: ('#4b2574', '#ffdf75', '★'),
    HAUT_POTENTIEL: ('#123b72', '#75eee1', '◆'),
}
COLONNE_PROFIL = 'Profil du cheval'
COLONNE_INDICES = 'Profil · Indices'


def libelles_profils(value):
    """Normaliser l'ancien libellé du registre à la lecture."""
    libelles = str(value or '').split(SEPARATEUR_PROFILS)
    return tuple(CRACK_CONFIRME if libelle == 'Crack' else libelle for libelle in libelles if libelle)
