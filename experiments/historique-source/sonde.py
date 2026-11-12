"""Sonde non intrusive de disponibilité des sources publiques d'historique.

Une requête par URL fournie, sans navigateur, contournement ni répétition automatique.
Les résultats servent au diagnostic et ne constituent pas un historique validé.
"""
from __future__ import annotations
import argparse
import json
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SOURCES = {
    "pmu": {"online.turfinfo.api.pmu.fr", "www.pmu.fr", "pmu.fr"},
    "equidia": {"equidia.fr", "www.equidia.fr"},
    "zeturf": {"zeturf.fr", "www.zeturf.fr", "zone-turf.fr", "www.zone-turf.fr"},
}


def sonder(source: str, url: str, timeout: int = 12) -> dict:
    h = urlsplit(url)
    if source not in SOURCES or h.scheme != "https" or h.hostname not in SOURCES[source]:
        raise ValueError("URL non autorisée pour cette source")
    resultat = {"source": source, "url": url, "utc": datetime.now(timezone.utc).isoformat(), "statut": "INCONNU"}
    debut = time.monotonic()
    try:
        req = Request(url, headers={"User-Agent": "PMU-Historique-QualityCheck/1.0"})
        with urlopen(req, timeout=timeout) as response:
            resultat.update(http=response.status, type_contenu=response.headers.get("Content-Type", ""), statut="ACCESSIBLE", octets_lus=len(response.read(65536)))
    except HTTPError as e:
        resultat.update(http=e.code, statut="ACCES_LIMITE" if e.code in (403, 429) else "ERREUR_HTTP")
    except (URLError, TimeoutError, OSError) as e:
        resultat.update(statut="ERREUR_RESEAU", erreur=type(e).__name__)
    resultat["duree_ms"] = round((time.monotonic()-debut)*1000)
    return resultat


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=SOURCES, required=True)
    p.add_argument("--url", required=True)
    args = p.parse_args()
    print(json.dumps(sonder(args.source, args.url), ensure_ascii=False))


if __name__ == "__main__":
    main()
