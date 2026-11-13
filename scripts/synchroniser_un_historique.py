"""Publication incrementale idempotente : un historique et ses lignes de partants."""
import json,os
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]

def synchroniser(horse,spreadsheet,cache=None):
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    from pmu_geny.sync_google_sheets import source_rows,limiter_cours_registre,canonical_headers,plan_sheet,colname
    from pmu_geny.liaison_chevaux_v22 import nom_normalise
    info=json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'])
    session=AuthorizedSession(Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/spreadsheets']))
    base=f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet}'
    def check(response):response.raise_for_status();return response.json()
    metadata=check(session.get(base,params={'fields':'sheets(properties(sheetId,title,gridProperties))'},timeout=30))
    tables={s['properties']['title']:s['properties'] for s in metadata['sheets']}
    cache=Path(cache) if cache is not None else ROOT/'cache_pmu'
    source=limiter_cours_registre(source_rows(cache));ident=horse['geny']['id']
    history={k:v for k,v in source['Historique chevaux'].items() if str(v.get('identifiant_cheval'))==ident}
    if not history and horse.get('nombre_performances')!=0:raise ValueError('Aucune performance a synchroniser pour '+ident)
    allowed={'course_key','numero','historique_statut','historique_nb_courses_datees','historique_maj_utc'}
    courses={k:{f:v for f,v in row.items() if f in allowed} for k,row in source['Courses & Prévisions'].items()
             if nom_normalise(row.get('cheval'))==nom_normalise(horse['nom']) and str(row.get('historique_statut','')).startswith('HISTO_OK')}
    counts={}
    for tab,incoming in [('Historique chevaux',history),('Courses & Prévisions',courses)]:
        prop=tables[tab];width=prop['gridProperties']['columnCount'];height=prop['gridProperties']['rowCount']
        path=quote("'"+tab+"'!A1:"+colname(width)+str(height),safe='!:\'')
        values=check(session.get(base+'/values/'+path,timeout=45)).get('values',[])
        if not values:raise ValueError('Onglet sans en-tetes : '+tab)
        headers=canonical_headers(values[0]);existing=[dict(zip(headers,row)) for row in values[1:]]
        new_headers,updates,appends=plan_sheet(headers,existing,incoming,tab)
        # Aucun changement de structure dans cette synchronisation individuelle.
        updates=[{'range':f"'{tab}'!{colname(c)}{r}",'values':[[v]]} for r,c,v in updates if c<=len(headers)]
        for n in range(0,len(updates),200):check(session.post(base+'/values:batchUpdate',json={'valueInputOption':'RAW','data':updates[n:n+200]},timeout=45))
        if appends:
            rows=[row[:len(headers)] for row in appends]
            check(session.post(base+'/values/'+quote("'"+tab+"'!A1",safe='!:\'')+':append',params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},json={'values':rows},timeout=45))
        counts[tab]={'lignes_ajoutees':len(appends),'cellules_actualisees':len(updates),'lignes_source':len(incoming)}
    from pmu_geny.kpi_registre import KPI_TAB,calculer_kpi,plan_kpi
    if KPI_TAB in tables:
        values=check(session.get(base+'/values/'+quote("'"+KPI_TAB+"'!A1:D100",safe='!:\''),timeout=30)).get('values',[])
        updates=plan_kpi(values,calculer_kpi(cache,source))
        if updates:check(session.post(base+'/values:batchUpdate',json={'valueInputOption':'RAW','data':updates},timeout=45))
        counts[KPI_TAB]={'indicateurs_actualises':len(updates)}
    return counts
