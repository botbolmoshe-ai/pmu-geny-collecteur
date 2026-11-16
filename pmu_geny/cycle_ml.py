"""Une tentative ML par jour et empreinte, apres 20 h Paris, dans le job existant."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .ml_v19 import load, save, train

PARIS = ZoneInfo('Europe/Paris')


def run(cache, now=None, force=False):
    cache = Path(cache)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Fuseau horaire obligatoire')
    local = now.astimezone(PARIS)
    digest = hashlib.sha256()
    for folder in ('ml/instantanes', 'arrivees'):
        for path in sorted((cache / folder).glob('*.json')):
            digest.update(str(path.relative_to(cache)).encode())
            digest.update(path.read_bytes())
    fingerprint = digest.hexdigest()
    from .cycle_ml_experimental import executer
    experimental=executer(cache,now,fingerprint)
    if not force and local.hour < 20:
        return {'etat': 'ENTRAINEMENT_DIFFERE_20H_PARIS','experimental':experimental}
    attempt_path = cache / 'ml/cycle.json'
    previous = load(attempt_path, {}) or {}
    key = {'jour_paris': local.date().isoformat(), 'empreinte_donnees': fingerprint}
    if not force and all(previous.get(k) == v for k, v in key.items()):
        return {'etat': 'DEJA_TRAITE', **key, 'resultat_precedent': previous.get('etat'),'experimental':experimental}
    # Une erreur laisse la tentative precedente intacte et autorise la reprise.
    result = train(cache, now=now)
    result.update(key)
    result['experimental']=experimental
    save(cache / 'ml/entrainement.json', result)
    save(attempt_path, {**key, 'tentative_utc': now.isoformat(), 'etat': result['etat']})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='cache_pmu')
    parser.add_argument('--force', action='store_true', help='Ignore uniquement la planification, pas les seuils ni la validation')
    args = parser.parse_args()
    print(json.dumps(run(args.cache, force=args.force), ensure_ascii=False))


if __name__ == '__main__':
    main()
