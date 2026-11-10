"""Statuts de participation attestés par la consultation humaine de la fiche PMU.

Aucune lecture Geny et aucune conclusion automatique à partir d'une page PMU
non validée. Une vérification sans source ou sans confirmation est refusée.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

VALID = {'PARTANT', 'NON_PARTANT', 'NP_NON_VERIFIE'}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def enregistrer(manifest: dict, dossier: Path, source_url: str, non_partants: str,
                liste_complete: bool = False, controle_confirme: bool = False) -> list[dict]:
    url = urlparse(source_url)
    if url.scheme != 'https' or url.hostname not in {'pmu.fr','www.pmu.fr'}:
        raise ValueError('Une URL officielle https://www.pmu.fr/... est obligatoire')
    if not controle_confirme:
        raise ValueError('Le contrôle PMU doit être explicitement confirmé après consultation de la fiche')
    numeros = [int(s.strip()) for s in non_partants.split(',') if s.strip()]
    if len(numeros) != len(set(numeros)):
        raise ValueError('Numéros non-partants en doublon')
    resultat = []
    for course in manifest['courses']:
        parts = course['partants']
        tous = {int(p['numero']) for p in parts}
        if not set(numeros).issubset(tous):
            raise ValueError('Numéro NP absent du manifeste')
        cid = course['course_id']
        out = dossier / f'{cid}.json'
        # En absence de liste complète, ne pas écraser les observations fiables
        # antérieures sur d'autres chevaux.
        precedent = _read(out) if out.exists() else {}
        anciens = {int(p['numero']): p for p in precedent.get('chevaux', [])}
        now = datetime.now(timezone.utc).isoformat()
        lignes = []
        for p in parts:
            numero = int(p['numero'])
            old = anciens.get(numero, {})
            if numero in numeros:
                statut = 'NON_PARTANT'
                src, vu = source_url, now
            elif liste_complete:
                # Même sans NP indiqué, une fiche PMU consultée et validée vaut 0 NP.
                statut = 'PARTANT'
                src, vu = source_url, now
            else:
                statut = old.get('statut_participation', 'NP_NON_VERIFIE')
                src, vu = old.get('source_np', ''), old.get('date_verification_np', '')
            lignes.append({'cheval_id': str(p['id']), 'numero': numero, 'nom': p['nom'],
                           'statut_participation': statut, 'source_np': src,
                           'date_verification_np': vu})
        dossier.mkdir(parents=True, exist_ok=True)
        doc = {'schema_version': 1, 'course_id': cid, 'source_reference': 'PMU',
               'date_controle_utc': now, 'source_url': source_url,
               'liste_complete_verifiee': liste_complete, 'chevaux': lignes}
        tmp = out.with_suffix('.tmp')
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(out)
        resultat.append(doc)
    return resultat


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', required=True)
    p.add_argument('--dossier', default='cache_pmu/participations')
    p.add_argument('--url-pmu', required=True)
    p.add_argument('--non-partants', default='', help='Numéros séparés par virgules, vide si aucun')
    p.add_argument('--liste-complete', action='store_true', help='Page PMU complète examinée, tous les autres sont PARTANT')
    p.add_argument('--confirme', action='store_true', help='Confirme la consultation effective de la fiche officielle')
    a = p.parse_args()
    for d in enregistrer(_read(Path(a.manifest)), Path(a.dossier), a.url_pmu, a.non_partants,
                         a.liste_complete, a.confirme):
        print(f"PMU {d['course_id']} : {sum(x['statut_participation']=='NON_PARTANT' for x in d['chevaux'])} NP, "
              f"{sum(x['statut_participation']=='PARTANT' for x in d['chevaux'])} partants confirmés")

if __name__ == '__main__':
    main()
