"""Refresh optional Geny indexes only after successful PMU publication."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .echeances_production import lire, instant, pause_geny_active

PARIS = ZoneInfo("Europe/Paris")


def dates_a_traiter(cache, plan, now):
    cache = Path(cache)
    if plan.get("mode") != "GLOBAL":
        return []
    if pause_geny_active(cache, now):
        return []
    today = now.astimezone(PARIS).date()
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
        dates.append(date)
    return dates


def run(cache, plan, clock=None, fetch=None):
    cache = Path(cache)
    clock = clock or (lambda: datetime.now(timezone.utc))
    if fetch is None:
        from .rapprochement_v20_6 import index_programme
        fetch = index_programme
    for date in dates_a_traiter(cache, plan, clock()):
        if date not in dates_a_traiter(cache, plan, clock()):
            continue
        result = fetch(cache, date, cache / "etat_persistant.json")
        print("INDEX_GENY_APRES_PUBLICATION", date, result.get("statut"), flush=True)
        if result.get("statut") == "GENY_BLOQUE":
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--verifier", action="store_true")
    args = parser.parse_args()
    plan = lire(args.plan)
    if args.verifier:
        raise SystemExit(0 if dates_a_traiter(args.cache, plan, datetime.now(timezone.utc)) else 1)
    run(args.cache, plan)


if __name__ == "__main__":
    main()
