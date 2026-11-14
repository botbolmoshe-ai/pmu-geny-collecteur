"""Compatibilité : délégation au moteur Sheets unique, sans logique d'écriture."""
from pathlib import Path
from pmu_geny.moteur_sheets import SynchroniseurSheets
ROOT=Path(__file__).resolve().parents[1]


def synchroniser(horse,spreadsheet,cache=None):
    engine=SynchroniseurSheets(Path(cache) if cache is not None else ROOT/'cache_pmu',spreadsheet)
    try:return engine.synchroniser_cheval(horse)
    finally:engine.fermer()
