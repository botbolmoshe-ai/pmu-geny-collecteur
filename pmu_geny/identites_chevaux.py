"""Identifiants propres à chaque fournisseur et correspondances vérifiées.

Un numéro Zone-Turf n'est jamais un numéro Geny par convention. Les liens
inter-sources sont explicites, sourcés et révisables dans le registre JSON.
"""
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from .liaison_chevaux_v22 import nom_normalise

REGISTRE = Path(__file__).with_name('identites_chevaux_verifiees.json')


def source_identifiant(ident, url):
    parsed = urlparse(str(url or ''))
    if parsed.scheme != 'https':
        return ''
    if parsed.hostname in ('geny.com', 'www.geny.com'):
        match = re.match(r'/cheval/(\d+)(?:\D|$)', parsed.path)
        return 'geny' if match and match[1] == str(ident) else ''
    if parsed.hostname in ('zone-turf.fr', 'www.zone-turf.fr'):
        match = re.fullmatch(r'/cheval/[^/]+-(\d+)/(?:resume-de-carriere/?)?', parsed.path)
        return 'zone_turf' if match and match[1] == str(ident) else ''
    return ''


@lru_cache(maxsize=1)
def correspondances():
    entries = json.loads(REGISTRE.read_text(encoding='utf-8'))['correspondances']
    seen = set()
    for item in entries:
        stamp = datetime.fromisoformat(item['verification_utc'])
        ids = item['identifiants']
        if (not item.get('nom') or stamp.tzinfo is None or stamp > datetime.now(timezone.utc)
                or not re.fullmatch(r'\d{4,15}', ids['geny'])
                or source_identifiant(ids['geny'], item['url_geny']) != 'geny'
                or not re.fullmatch(r'https://www\.geny\.com/course/\d+/partants-pronostics', item['course_url'])
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}_R\d+C\d+', item['engagement'])
                or not str(item.get('numero', '')).isdigit()
                or len(item.get('performances_rapprochees', [])) < 2):
            raise ValueError('CORRESPONDANCE_IDENTITE_NON_PROUVEE')
        if re.search(r'/course/(\d+)', item['url_geny'])[1] != re.search(r'/course/(\d+)', item['course_url'])[1]:
            raise ValueError('COURSE_IDENTITE_NON_CONCORDANTE')
        for source, ident in ids.items():
            if source != 'geny' and source_identifiant(ident, item['urls_sources'].get(source)) != source:
                raise ValueError('SOURCE_IDENTIFIANT_NON_CONCORDANTE')
            if (source, ident) in seen:
                raise ValueError('CORRESPONDANCE_IDENTITE_AMBIGUE')
            seen.add((source, ident))
    return entries


def qualifier_observation(record):
    """Conserver la provenance ; appliquer seulement une liaison déjà vérifiée."""
    record = dict(record)
    ident = str(record.get('id', ''))
    source = source_identifiant(ident, record.get('source_url'))
    if not source:
        # Certaines anciennes lignes portent déjà l'URL Geny exacte mais
        # encore le numéro Zone-Turf dans la colonne ID.
        for proof in correspondances():
            if (nom_normalise(proof['nom'])==nom_normalise(record.get('nom'))
                    and source_identifiant(proof['identifiants']['geny'],record.get('source_url'))=='geny'):
                source=next((s for s,i in proof['identifiants'].items() if s!='geny' and i==ident),'')
                if source:break
    if not source:
        return record
    record['source_identifiant'] = source
    record['identifiants_sources'] = {source: ident}
    if source == 'geny':
        return record
    matches = [x for x in correspondances() if x['identifiants'].get(source) == ident
               and nom_normalise(x['nom']) == nom_normalise(record.get('nom'))]
    if len(matches) == 1:
        proof = matches[0]
        record.update(id=proof['identifiants']['geny'], url_geny=proof['url_geny'],
                      identifiants_sources=proof['identifiants'], reconciliation_identite=proof)
    else:
        # Un nouveau lien nécessite une vérification explicite ; aucun candidat
        # /cheval/ID n'est construit sur le serveur d'un autre fournisseur.
        record.update(id='', identifiant_externe_non_reconcilie=True)
    return record


def canoniser_ligne(row):
    observation = qualifier_observation({'id': str(row.get('identifiant_cheval', '')),
        'nom': row.get('cheval', ''), 'source_url': row.get('source_url', '')})
    if observation.get('reconciliation_identite'):
        return {**row, 'identifiant_cheval': observation['id']}
    return row


def cle_inter_sources(row):
    """Même performance attestée : seule la notation des secondes est normalisée."""
    from .controle_sync_sheets import cle_sportive
    row = dict(canoniser_ligne(row))
    row['chrono'] = str(row.get('chrono', '')).replace('"', "''")
    return cle_sportive(row)
