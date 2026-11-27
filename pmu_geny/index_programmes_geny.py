"""Actualiser les index Geny à partir du dernier programme PMU durable."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dashboard.trot_analytics.dates import PARIS

from .cadence_geny import CadenceGeny
from .echeances_production import instant, lire, pause_geny_active, sauver
from .persistance_production import publier

DELAI_REPRISE = timedelta(minutes=25)


def dates_a_traiter(cache, now):
    cache = Path(cache)
    if pause_geny_active(cache, now):
        return []
    today = now.astimezone(PARIS).date()
    tentatives = lire(cache / "etat_persistant.json").get("tentatives_index_geny", {})
    dates = []
    for day in (today, today + timedelta(days=1)):
        date = day.isoformat()
        programme = lire(cache / "sources_pmu" / f"programme_{date}.json").get("programme", [])
        if not any((depart := instant(c.get("depart"))) and depart > now for c in programme):
            continue
        index = lire(cache / "sources_geny" / f"index_{date}.json")
        stamp = instant(index.get("consultation_utc"))
        if index.get("statut") == "OK" and index.get("schema_index") == 2 and stamp and timedelta(0) <= now-stamp < timedelta(hours=6):
            continue
        derniere = instant(tentatives.get(date))
        if derniere and timedelta(0) <= now-derniere < DELAI_REPRISE:
            continue
        dates.append(date)
    return dates


def run(cache, clock=None, fetch=None, checkpoint=None):
    cache = Path(cache)
    clock = clock or (lambda: datetime.now(timezone.utc))
    debut = clock()
    dates = dates_a_traiter(cache, debut)
    if not dates:
        return
    cadence = CadenceGeny(cache)
    if cadence.delai(debut):
        return
    if fetch is None:
        from .rapprochement_v20_6 import index_programme

        fetch = index_programme
    # Une consultation par créneau de cadence. Les dates restantes sont
    # reprises au passage suivant dans la même file Geny.
    date = dates[0]
    cadence.reserver(debut)
    journal = cache / "etat_persistant.json"
    etat = lire(journal)
    tentatives = etat.get("tentatives_index_geny", {})
    etat["tentatives_index_geny"] = {d: t for d, t in tentatives.items()
                                     if (stamp := instant(t)) and timedelta(0) <= debut-stamp < DELAI_REPRISE}
    etat["tentatives_index_geny"][date] = debut.isoformat()
    sauver(journal, etat)
    if checkpoint:
        checkpoint(date)
    refuse = False
    try:
        result = fetch(cache, date, journal)
        refuse = result.get("statut") == "GENY_BLOQUE"
        print("INDEX_PROGRAMME_GENY", date, result.get("statut"), flush=True)
    except Exception as exc:
        print(f"::warning::INDEX_PROGRAMME_GENY {date} {type(exc).__name__}", flush=True)
    finally:
        cadence.terminer(clock(), refus=refuse)
        if checkpoint:
            checkpoint(date)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    args = parser.parse_args()

    def checkpoint(date):
        publier(args.cache, chemins=(f"sources_geny/index_{date}.json", "etat_persistant.json"),
                message="Geny : index du programme et cadence")

    run(args.cache, checkpoint=checkpoint)


if __name__ == "__main__":
    main()
