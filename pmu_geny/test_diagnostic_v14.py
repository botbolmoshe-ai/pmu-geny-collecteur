"""Tests sans réseau des pages Geny et de la classification."""
from pathlib import Path
import json
from .collecte_geny_v4 import diagnostic_acces
from .controle_historique import classifier


def run_tests():
    path = Path(__file__).resolve().parent / 'fixtures_v14' / 'diagnostic_geny_403.html'
    raw = path.read_text(encoding='utf-8')
    assert diagnostic_acces(200, 'Accès refusé - Geny', '403\nAccès refusé', raw) == 'ACCES_REFUSE_403'
    assert diagnostic_acces(403, 'Erreur', '', '') == 'ACCES_REFUSE_403'
    assert diagnostic_acces(200, 'Trop de requêtes - Geny', '429\nTrop de requêtes', '') == 'ACCES_LIMITE_429'
    assert diagnostic_acces(200, 'Fiche cheval', 'CARRIÈRE\n sur 2 courses', '') == 'CARRIERE_ACCESSIBLE'
    assert diagnostic_acces(200, 'Fiche cheval', 'RECORDS seulement', '') == 'CARRIERE_NON_DETECTEE'
    assert classifier({'statut':'ACCES_REFUSE_403', 'nombre_extrait':0})[0] == 'ACCES_REFUSE_403'
    print('6 controles V14 OK (403, 429, carriere, classification).')

if __name__ == '__main__':
    run_tests()
