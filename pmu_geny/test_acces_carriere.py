"""Test GitHub isole : une seule fiche cheval, sans decouverte des partants."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .extraction_historique_par_cheval import extraire_cheval

OSCAR_URL = 'https://www.geny.com/cheval/2904327-oscar-fougeray/course/1697378'

def main() -> int:
    p = argparse.ArgumentParser(description='Controle carriere et limitation Geny, un seul cheval')
    p.add_argument('--url', default=OSCAR_URL)
    p.add_argument('--id', default='2904327')
    p.add_argument('--sortie', default='resultats/test_v9')
    a = p.parse_args()
    result = extraire_cheval(a.url, a.id, Path(a.sortie))
    dest = Path(a.sortie)/a.id
    path = dest/'controle_acces.json'
    access = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'statut_acces': 'DIAGNOSTIC_INDISPONIBLE'}
    print('CONTROLE V9 :', access['statut_acces'], flush=True)
    print('CARRIERE ACCESSIBLE :', access.get('carriere_accessible'), flush=True)
    print('HISTORIQUE EXTRAIT :', access.get('historique_extrait'), flush=True)
    print('HISTORIQUE COMPLET :', access.get('historique_complet'), flush=True)
    print('STATUT COLLECTE :', result.get('statut'), flush=True)
    print('DIAGNOSTICS :', dest.resolve(), flush=True)
    # Le 429 est une limitation attendue, distincte d'une defaillance du workflow.
    return 0 if access['statut_acces'] in ('ACCES_LIMITE_429','CARRIERE_ACCESSIBLE') else 1

if __name__ == '__main__':
    raise SystemExit(main())
