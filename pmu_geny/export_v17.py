"""Exports déterministes à partir du stockage durable V16; aucune requête réseau.

Une ligne par cheval (suivi), une ligne par course historique (performances).
Statuts PMU strictement séparés des historiques Geny. Encodage UTF-8 BOM,
séparateur ';' pour Excel français.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

FIELDS_SUIVI = ['course_id','numero','cheval_id','nom','statut_participation','eligible_top3',
 'source_np','date_verification_np','historique_statut','nombre_annonce_geny',
 'nombre_extrait','nombre_performances_persistantes','historique_source','historique_maj_utc']
FIELDS_PERF = ['course_id','numero','cheval_id','nom','date','hippodrome','discipline',
 'distance_m','classement','chrono','texte_source']


def _json(path: Path, fallback=None):
    if not path.exists(): return fallback
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError): return fallback


def _write(path: Path, cols: list[str], records: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as h:
        w = csv.DictWriter(h, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(records)
    tmp.replace(path)


def exporter(manifest: dict, cache: Path, sorties: Path) -> list[dict]:
    state = _json(cache / 'etat_persistant.json', {}) or {}
    journal = state.get('chevaux', {})
    bilans = []
    for course in manifest['courses']:
        cid = course['course_id']
        regist = _json(cache / 'participations' / f'{cid}.json', {}) or {}
        np_map = {str(p['cheval_id']): p for p in regist.get('chevaux', [])}
        suivi, perfs = [], []
        for cheval in course['partants']:
            ident = str(cheval['id']); numero = int(cheval['numero'])
            part = np_map.get(ident, {})
            statut_np = part.get('statut_participation', 'NP_NON_VERIFIE')
            if statut_np not in {'PARTANT','NON_PARTANT','NP_NON_VERIFIE'}:
                statut_np = 'NP_NON_VERIFIE'
            doc = _json(cache / 'historiques' / ident / 'historique_geny.json', {}) or {}
            historique = journal.get(ident, {})
            liste = doc.get('performances', [])
            if not isinstance(liste, list): liste = []
            hist_statut = doc.get('statut') or historique.get('statut') or 'NON_COLLECTE'
            for perf in liste:
                if not isinstance(perf, dict): continue
                perfs.append({'course_id': cid, 'numero': numero, 'cheval_id': ident,
                    'nom': cheval['nom'], **{k: perf.get(k,'') for k in FIELDS_PERF[4:]}})
            suivi.append({'course_id': cid, 'numero': numero, 'cheval_id': ident,
                'nom': cheval['nom'], 'statut_participation': statut_np,
                'eligible_top3': 'NON' if statut_np=='NON_PARTANT' else ('OUI' if statut_np=='PARTANT' else 'A_VERIFIER'),
                'source_np': part.get('source_np',''), 'date_verification_np': part.get('date_verification_np',''),
                'historique_statut': hist_statut,
                'nombre_annonce_geny': doc.get('nombre_annonce_geny', historique.get('nombre_annonce_geny', '')),
                'nombre_extrait': doc.get('nombre_extrait', historique.get('nombre_extrait','')),
                'nombre_performances_persistantes': len(liste),
                'historique_source': doc.get('source_url', ''),
                'historique_maj_utc': doc.get('extrait_utc', historique.get('maj_utc',''))})
        target = sorties / cid
        _write(target / 'suivi_chevaux.csv', FIELDS_SUIVI, suivi)
        _write(target / 'performances.csv', FIELDS_PERF, perfs)
        resume = {'course_id':cid,'chevaux':len(suivi),'performances':len(perfs),
                  'np_confirme':sum(x['statut_participation']=='NON_PARTANT' for x in suivi),
                  'np_non_verifie':sum(x['statut_participation']=='NP_NON_VERIFIE' for x in suivi),
                  'historiques_complets':sum(x['historique_statut']=='COMPLET' for x in suivi)}
        (target / 'synthese.json').write_text(json.dumps(resume,ensure_ascii=False,indent=2),encoding='utf-8')
        bilans.append(resume)
    return bilans


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest',required=True)
    p.add_argument('--cache',default='cache_pmu')
    p.add_argument('--sortie',default='cache_pmu/exports')
    args = p.parse_args()
    manifest = _json(Path(args.manifest))
    if not manifest or not manifest.get('courses'): raise SystemExit('Manifeste manquant ou invalide')
    for b in exporter(manifest,Path(args.cache),Path(args.sortie)):
        print('EXPORT V17 :',json.dumps(b,ensure_ascii=False))

if __name__=='__main__': main()
