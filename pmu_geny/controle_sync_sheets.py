"""Contrôles indépendants du plan d'écriture pour l'historique Sheets.

Un blocage ne supprime rien. Les variantes de clé existantes sont conservées.
Le journal et le résumé GitHub rendent l'incident visible même si HTTP réussit.
"""
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HISTORY = 'Historique chevaux'
KEY = 'cle_performance'
SPORT_FIELDS = ('identifiant_cheval','date_course_historique','hippodrome',
                'discipline','distance_m','classement','chrono')


def cle_sportive(row):
    """Identite independante de la provenance ; ignorer les lignes incomplètes."""
    if not all(str(row.get(f) or '').strip() for f in SPORT_FIELDS[:3]):
        return None
    return tuple(str(row.get(f) or '').strip().upper() for f in SPORT_FIELDS)



class BlocageSynchronisation(ValueError):
    pass


def journaliser(report):
    report = {**report, 'controle_utc': datetime.now(timezone.utc).isoformat()}
    target = Path(os.getenv('PMU_SHEETS_CONTROLES', 'resultats/synchronisation/controles.jsonl'))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False)+'\n')
    print('CONTROLE_SHEETS '+json.dumps(report, ensure_ascii=False), flush=True)
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f"\n- Historique Sheets : **{report['statut']}** — "
                         f"{report.get('motif', '')}; lignes avant={report.get('lignes_avant', '?')}, "
                         f"ajouts prévus={report.get('ajouts_prevus', '?')}, "
                         f"lignes après={report.get('lignes_apres', '?')}.\n")


def bloquer(report, motif):
    journaliser({**report, 'statut': 'BLOQUE', 'motif': motif})
    print('::error title=Synchronisation historique bloquée::'+motif, flush=True)
    raise BlocageSynchronisation(motif)


def inventaire(headers, rows):
    records = [r for r in rows if any(v is not None and str(v) != '' for v in r.values())]
    keys = Counter(str(r.get(KEY) or '').strip() for r in records)
    signatures = Counter(tuple('' if r.get(h) is None else str(r.get(h)) for h in headers) for r in records)
    sports=Counter(key for r in records if (key:=cle_sportive(r)) is not None)
    return {'rows': len(records), 'keys': keys,
            'missing_keys': keys.get('', 0),
            'duplicates': sum(n-1 for n in signatures.values() if n>1),
            'variants': sum(n>1 for k,n in keys.items() if k),
            'sport_duplicates': sum(n-1 for n in sports.values() if n>1)}


def lire_cles_independantes(session, base, tab, properties, headers):
    """Contrôle étroit séparé : ne pas se fier uniquement à la lecture des lignes."""
    from urllib.parse import quote
    from .sync_google_sheets import colname
    from .lectures_sheets import get_lecture
    if KEY not in headers:
        bloquer({'statut':'EN_CONTROLE','phase':'AVANT'}, 'COLONNE_CLE_ABSENTE')
    column = colname(headers.index(KEY)+1)
    height = properties['gridProperties']['rowCount']
    counts = Counter()
    for start in range(2, height+1, 25000):
        end=min(height,start+24999)
        path=quote("'"+tab.replace("'","''")+"'!"+column+str(start)+':'+column+str(end),safe="!:'")
        response=get_lecture(session,base+'/values/'+path,timeout=60)
        if response.status_code!=200:
            bloquer({'statut':'EN_CONTROLE','phase':'AVANT'}, 'LECTURE_INDEPENDANTE_DES_CLES_INCOMPLETE')
        values=response.json().get('values',[])
        if len(values)>end-start+1:
            bloquer({'statut':'EN_CONTROLE','phase':'AVANT'}, 'LECTURE_INDEPENDANTE_DES_CLES_INCOHERENTE')
        counts.update(str(row[0]).strip() for row in values if row and str(row[0]).strip())
    return counts


def verifier_source(incoming):
    source=Counter(str(r.get(KEY) or '').strip() for r in incoming.values())
    if '' in source or any(n>1 for n in source.values()):
        bloquer({'statut':'EN_CONTROLE','phase':'AVANT'}, 'CLES_SOURCE_ABSENTES_OU_REPETEES')
    return source


def verifier_avant(headers, existing, incoming, appends, *, full_source=False, observed_keys=None):
    report = {'statut': 'EN_CONTROLE', 'phase': 'AVANT', 'ajouts_prevus': len(appends)}
    if KEY not in headers:
        bloquer(report, 'COLONNE_CLE_ABSENTE')
    before = inventaire(headers, existing)
    report.update(lignes_avant=before['rows'], cles_avant=len(before['keys']),
                  doublons_valeurs_avant=before['duplicates'], cles_avec_variantes=before['variants'])
    if observed_keys is None or observed_keys != before['keys']:
        bloquer(report, 'LECTURE_DES_LIGNES_DIFFERENTE_DU_CONTROLE_INDEPENDANT_DES_CLES')
    if before['missing_keys']:
        bloquer(report, 'LIGNES_EXISTANTES_SANS_CLE')
    if before['duplicates']:
        bloquer(report, 'COPIES_DE_VALEURS_EXISTANTES_A_CONTROLER')
    if before['variants']:
        bloquer(report, 'CLES_PERFORMANCE_DUPLIQUEES')
    if before['sport_duplicates']:
        bloquer(report, 'PERFORMANCES_SPORTIVES_DUPLIQUEES')
    source = verifier_source(incoming)
    sports_source=[cle_sportive(r) for r in incoming.values()]
    sports_source=[k for k in sports_source if k is not None]
    if len(sports_source)!=len(set(sports_source)):
        bloquer(report, 'PERFORMANCES_SPORTIVES_DUPLIQUEES_DANS_SOURCE')
    # Une variation de signature ne doit jamais réinsérer une performance
    # déjà présente sous une autre clé technique.
    sport_existing={cle_sportive(row):str(row.get(KEY) or '').strip()
                    for row in existing if cle_sportive(row) is not None}
    for row in incoming.values():
        sem=cle_sportive(row)
        if sem is not None and sem in sport_existing and (
                sport_existing[sem] != str(row.get(KEY) or '').strip()):
            bloquer(report, 'REINSERTION_MEME_PERFORMANCE_SOUS_AUTRE_CLE')
    if full_source and before['rows'] and not source:
        bloquer(report, 'SOURCE_COMPLETE_INATTENDUE_VIDE')
    index = headers.index(KEY)
    planned = [str(r[index] or '').strip() if len(r)>index else '' for r in appends]
    if any(not k for k in planned) or len(set(planned)) != len(planned):
        bloquer(report, 'CLES_AJOUTEES_ABSENTES_OU_REPETEES')
    if set(planned) & set(before['keys']):
        bloquer(report, 'REINSERTION_DE_CLES_EXISTANTES')
    missing = set(source)-set(before['keys'])
    if set(planned) != missing:
        bloquer(report, 'AJOUTS_DIFFERENTS_DES_NOUVELLES_CLES_SOURCE')
    # Une croissance de milliers de lignes ne passe plus silencieusement.
    # Un import initial doit être identifié explicitement dans une exécution manuelle.
    bootstrap = not before['rows'] and os.getenv('PMU_SHEETS_IMPORT_INITIAL') == '1'
    cap = max(500, math.ceil(len(before['keys'])*0.10))
    report.update(seuil_ajouts=cap, import_initial_explicite=bootstrap)
    if len(planned)>cap and not bootstrap:
        bloquer(report, 'CROISSANCE_ANORMALE_AJOUTS_SUPERIEURS_AU_SEUIL')
    expected = before['keys'].copy()
    expected.update(planned)
    report.update(statut='AUTORISE', lignes_attendues=before['rows']+len(planned))
    journaliser(report)
    return {'report': report, 'expected_keys': expected, 'headers': headers}


def verifier_apres(control, rows):
    after = inventaire(control['headers'], rows)
    report = {**control['report'], 'phase': 'APRES', 'lignes_apres': after['rows'],
              'doublons_valeurs_apres': after['duplicates']}
    if after['keys'] != control['expected_keys']:
        bloquer(report, 'CLES_OU_MULTIPLICITES_APRES_ECRITURE_INATTENDUES')
    if after['rows'] != report['lignes_attendues']:
        bloquer(report, 'NOMBRE_DE_LIGNES_APRES_ECRITURE_INATTENDU')
    if after['duplicates']:
        bloquer(report, 'DOUBLONS_DE_VALEURS_APRES_ECRITURE')
    if after['variants'] or after['sport_duplicates']:
        bloquer(report, 'DOUBLONS_DE_PERFORMANCE_APRES_ECRITURE')
    report.update(statut='VALIDE', motif='COMPTAGES_ET_CLES_CONFORMES')
    journaliser(report)
    return report
