"""Synchronisation idempotente pmu-data -> Google Sheets (3 onglets existants).

Aucune information inventée; les champs absents restent vides. Utilise un compte de service
partagé comme éditeur sur le Google Sheet. Les secrets ne sont jamais loggés.
"""
import csv
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

SHEET_TABS = ('Courses & Prévisions', 'Historique chevaux', 'Résultats & Analyse')
COMPARE_COLUMNS = ('baseline_rang','baseline_top3','baseline_final_rang','baseline_final_top3',
                   'ml_rang','ml_top3','ml_proba_podium','cote_avant_depart','cote_heure_utc',
                   'arrivee_rang','arrivee_podium','ml_etat','meteo_pluie_mm','meteo_vent_kmh',
                   'meteo_temperature_c','meteo_humidite_pct','meteo_capture_utc')
REPORT_COLUMNS = ('score_baseline','score_baseline_final','score_ml','etat_ml',
                  'source_export','derniere_sync_utc')
HIST_MAPPING = {'identifiant_cheval':'cheval_id','cheval':'nom','date_course_historique':'date',
                'hippodrome':'hippodrome','discipline':'discipline','distance_m':'distance_m',
                'classement':'classement','chrono':'chrono','source_url':'texte_source'}


def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f,delimiter=';'))


def load_json(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}


def colname(n):
    s=''
    while n:
        n,r=divmod(n-1,26);s=chr(65+r)+s
    return s


def course_info(cache,code,date):
    data=load_json(cache/'sources_pmu'/f'programme_{date}.json')
    for x in data.get('programme',[]):
        if x.get('code')==code:return x
    return {}


def course_key(date,hippodrome,code):
    hip=str(hippodrome).strip().upper()
    for prefix in ('HIPPODROME DE PARIS-', 'HIPPODROME DE ', "HIPPODROME D'", 'HIPPODROME DU ', 'HIPPODROME DES '):
        if hip.startswith(prefix):hip=hip[len(prefix):];break
    return '|'.join([date,hip,code])


def source_rows(cache):
    courses, history, reports = {}, {}, {}
    for path in sorted((cache/'exports').glob('GENY-*/comparatif_predictions.csv')):
        try: comparisons=read_csv(path)
        except (OSError,ValueError):continue
        for r in comparisons:
            date=r.get('date','');code=r.get('course','');n=r.get('numero','')
            if not date or not code or not n:continue
            info=course_info(cache,code,date)
            if not info:continue
            hip=info.get('hippodrome','')
            k=course_key(date,hip,code);row_key=f'{k}|{n}'
            doc={'course_key':k,'date_course':date,'hippodrome':hip,'rncn':code,
                 'heure_depart_paris':r.get('depart',''),'numero':n,'cheval':r.get('nom',''),
                 'non_partant':r.get('statut_np',''),'historique_statut':'',
                 'statut_prevision':r.get('ml_etat',''),'mode_calcul_top3':'BASELINE+ML'}
            for c in COMPARE_COLUMNS:doc[c]=r.get(c,'')
            courses[row_key]=doc
            if r.get('arrivee_rang'):
                reports[k]={'course_key':k,'date_course':date,'hippodrome':hip,'rncn':code,
                            'heure_depart_paris':r.get('depart',''),
                            'score_baseline':r.get('baseline_hits_course',''),
                            'score_baseline_final':r.get('baseline_final_hits_course',''),
                            'score_ml':r.get('ml_hits_course',''),
                            'etat_ml':r.get('ml_etat',''),
                            'source_export':str(path.relative_to(cache)),
                            'derniere_sync_utc':datetime.now(timezone.utc).isoformat(),
                            'statut_evaluation':'ARRIVEE_RECUE_A_VERIFIER'}
    for path in sorted((cache/'exports').glob('GENY-*/performances.csv')):
        try: perfs=read_csv(path)
        except (OSError,ValueError):continue
        for r in perfs:
            ident=r.get('cheval_id','');date=r.get('date','');hip=r.get('hippodrome','')
            if not ident or not date:continue
            k=f'{ident}|{date}|{hip.strip().upper()}'
            doc={out:r.get(inn,'') for out,inn in HIST_MAPPING.items()}
            doc['cle_performance']=k
            doc['statut_verification']='EXTRACTION_GENY'
            history[k]=doc
    return {'Courses & Prévisions':courses,'Historique chevaux':history,'Résultats & Analyse':reports}


def ensure_headers(existing, additions):
    return existing + [x for x in additions if x not in existing]


def plan_sheet(existing_headers,existing_rows,new_items,tab,now=None):
    """Planning sans mutation: met à jour uniquement les colonnes propriétaires du bridge."""
    keys={'Courses & Prévisions':('course_key','numero'),
          'Historique chevaux':('cle_performance',),
          'Résultats & Analyse':('course_key',)}[tab]
    additions=COMPARE_COLUMNS if tab=='Courses & Prévisions' else REPORT_COLUMNS if tab=='Résultats & Analyse' else ()
    headers=ensure_headers(existing_headers,tuple(additions))
    if not all(x in headers for x in keys):raise ValueError(f'Colonnes cle manquantes pour {tab}: {keys}')
    def rowkey(row):return '|'.join(str(row.get(x,'')).strip() for x in keys)
    present={rowkey(r):idx+2 for idx,r in enumerate(existing_rows) if all(str(r.get(k,'')).strip() for k in keys)}
    changes=[];append=[]
    for item in new_items.values():
        k=rowkey(item)
        if k in present:
            # writes only values actually present/nonempty; leaves other cells untouched.
            for name,val in item.items():
                if (name in headers and val is not None and str(val)!=''
                        and str(existing_rows[present[k]-2].get(name,'')) != str(val)):
                    changes.append((present[k],headers.index(name)+1,str(val)))
        else:
            append.append([str(item.get(h,'')) if item.get(h) is not None else '' for h in headers]);present[k]=-1
    return headers,changes,append


def main():
    cache=Path(os.getenv('PMU_CACHE','cache_pmu'))
    spreadsheet=os.getenv('GOOGLE_SHEETS_ID','1BjzDzC6NsLRMax2XjrCIcCIIgz6hyCJ1YTWOa5hiGLo')
    secret=os.getenv('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON','')
    if not secret:
        print('SYNC_GOOGLE_SHEETS=NON_CONFIGURE: secret absent');return 0
    try:
        import google.oauth2.service_account
        from google.auth.transport.requests import AuthorizedSession
        info=json.loads(secret)
        creds=google.oauth2.service_account.Credentials.from_service_account_info(
            info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
        session=AuthorizedSession(creds)
    except (ImportError,ValueError,KeyError,TypeError) as exc:
        print(f'SYNC_GOOGLE_SHEETS=ERREUR_IDENTIFIANTS {type(exc).__name__}');return 2
    base=f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet}'
    source=source_rows(cache)
    metadata=session.get(base,params={'fields':'sheets(properties(sheetId,title,gridProperties(columnCount)))'},timeout=30)
    if metadata.status_code != 200:
        print(f'SYNC_GOOGLE_SHEETS=ERREUR_META http={metadata.status_code}')
        return 2
    by_name={x['properties']['title']:x['properties'] for x in metadata.json().get('sheets',[])}
    errors=0
    for tab in SHEET_TABS:
        import urllib.parse
        quoted=urllib.parse.quote("'"+tab.replace("'","''")+"'!A1:BS5000",safe='!:\'')
        response=session.get(f'{base}/values/{quoted}',timeout=30)
        if response.status_code!=200:
            print(f'SYNC_GOOGLE_SHEETS=ERREUR_LECTURE onglet={tab} http={response.status_code}');errors+=1;continue
        values=response.json().get('values',[])
        headers=values[0] if values else []
        existing=[dict(zip(headers,row)) for row in values[1:]]
        try: all_headers,updates,appends=plan_sheet(headers,existing,source[tab],tab)
        except ValueError as exc:print('SYNC_GOOGLE_SHEETS=SCHEMA_INCOMPATIBLE',str(exc));errors+=1;continue
        updates_cells=[]
        # Only write bridge-owned fields of existing rows (the user retains all other cells).
        extra=all_headers[len(headers):]
        # Dimensionner la grille avant toute écriture hors limite actuelle.
        properties=by_name.get(tab)
        if properties is None:
            print(f'SYNC_GOOGLE_SHEETS=ONGLET_ABSENT {tab}');errors+=1;continue
        current_width=properties.get('gridProperties',{}).get('columnCount',0)
        if len(all_headers)>current_width:
            grow={'requests':[{'appendDimension':{'sheetId':properties['sheetId'],
                  'dimension':'COLUMNS','length':len(all_headers)-current_width}}]}
            response=session.post(base+':batchUpdate',json=grow,timeout=30)
            if response.status_code!=200:
                print(f'SYNC_GOOGLE_SHEETS=ERREUR_COLONNES onglet={tab} http={response.status_code}')
                errors+=1;continue
        if extra:
            updates_cells.append({'range':f"'{tab}'!{colname(len(headers)+1)}1:{colname(len(all_headers))}1",'values':[extra]})
        for r,c,v in updates:
            updates_cells.append({'range':f"'{tab}'!{colname(c)}{r}",'values':[[v]]})
        # Use a single batchUpdate per tab, plus append for new rows.
        for offset in range(0,len(updates_cells),350):
            chunk=updates_cells[offset:offset+350]
            res=session.post(f'{base}/values:batchUpdate',json={'valueInputOption':'RAW','data':chunk},timeout=45)
            if res.status_code!=200:
                print(f'SYNC_GOOGLE_SHEETS=ERREUR_MAJ onglet={tab} http={res.status_code}');errors+=1;break
        if appends:
            url=f'{base}/values/'+urllib.parse.quote("'"+tab+"'!A1",safe='!:\'')+':append'
            res=session.post(url,params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},
                             json={'values':appends},timeout=45)
            if res.status_code!=200:
                print(f'SYNC_GOOGLE_SHEETS=ERREUR_AJOUT onglet={tab} http={res.status_code}');errors+=1
        print(f'SYNC_GOOGLE_SHEETS onglet={tab} lignes_source={len(source[tab])} '
              f'cellules_mises_a_jour={len(updates)} lignes_ajoutees={len(appends)}')
    return 1 if errors else 0

if __name__=='__main__':sys.exit(main())
