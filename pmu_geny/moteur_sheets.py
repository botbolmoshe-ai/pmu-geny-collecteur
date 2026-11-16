"""Moteur unique d'écriture Sheets, commun aux publications cheval et cycle."""
import fcntl
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from .controle_sync_sheets import HISTORY,lire_cles_independantes,verifier_avant,verifier_apres
from .lectures_sheets import get_lecture


class ErreurSynchronisation(RuntimeError):
    pass


class SynchronisationOccupee(ErreurSynchronisation):
    pass


@contextmanager
def verrou_local(spreadsheet):
    # Les runners distincts sont sérialisés par pmu-donnees-production dans Actions.
    # Ce verrou supplémentaire protège les processus locaux visant le même fichier.
    directory=Path(os.getenv('PMU_SHEETS_LOCK_DIR',tempfile.gettempdir()))
    directory.mkdir(parents=True,exist_ok=True)
    name='pmu-sheets-'+hashlib.sha256(spreadsheet.encode()).hexdigest()[:24]+'.lock'
    with (directory/name).open('a') as handle:
        try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SynchronisationOccupee('Une synchronisation locale est déjà en cours') from exc
        try:yield
        finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def ouvrir_session():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    info=json.loads(os.environ['GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'])
    return AuthorizedSession(Credentials.from_service_account_info(
        info,scopes=['https://www.googleapis.com/auth/spreadsheets']))


class SessionMesuree:
    def __init__(self,session):
        self.raw=session;self.lectures=0;self.ecritures=0
    def get(self,*args,**kwargs):
        self.lectures+=1;return self.raw.get(*args,**kwargs)
    def post(self,*args,**kwargs):
        # Ne jamais réessayer aveuglément un append : la reprise relit les clés.
        self.ecritures+=1;return self.raw.post(*args,**kwargs)


class SynchroniseurSheets:
    def __init__(self,cache,spreadsheet,session=None):
        self.cache=Path(cache);self.spreadsheet=spreadsheet
        self.base=f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet}'
        self.session=SessionMesuree(session if session is not None else ouvrir_session())

    def fermer(self):
        close=getattr(self.session.raw,'close',None)
        if close:close()

    @staticmethod
    def check(response):
        if response.status_code!=200:
            raise ErreurSynchronisation(f'Requete Sheets refusee, HTTP {response.status_code}')
        return response.json()

    def metadata(self):
        doc=self.check(get_lecture(self.session,self.base,
            params={'fields':'sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))'},timeout=30))
        return {x['properties']['title']:x['properties'] for x in doc['sheets']}

    def source(self):
        from .sync_google_sheets import source_rows,limiter_cours_registre
        return limiter_cours_registre(source_rows(self.cache))

    def _migrer_entetes(self,tab,values):
        from .sync_google_sheets import DISPLAY_NAMES,colname
        legacy={'Avis expert Zone-Turf':'avis_zeturf','avis_zone_turf':'avis_zeturf'}
        migration=[]
        for idx,label in enumerate(values[0]):
            if label not in legacy:continue
            key=legacy[label]
            if DISPLAY_NAMES[key] in values[0] or key in values[0]:continue
            migration.append({'range':f"'{tab}'!{colname(idx+1)}1:{colname(idx+1)}{len(values)}",
                              'values':[[DISPLAY_NAMES[key]]]+[[''] for _ in values[1:]]})
            values[0][idx]=DISPLAY_NAMES[key]
            for row in values[1:]:
                if len(row)>idx:row[idx]=''
        if migration:self.check(self.session.post(self.base+'/values:batchUpdate',
            json={'valueInputOption':'RAW','data':migration},timeout=45))

    def _synchroniser_onglet(self,tab,incoming,properties,*,full_source,allow_structure):
        from .sync_google_sheets import lire_feuille_complete,canonical_headers,plan_sheet,colname,DISPLAY_NAMES,reconcilier_cles_historiques
        values=lire_feuille_complete(self.session,self.base,tab,properties)
        if not values:raise ErreurSynchronisation('Onglet sans en-tetes : '+tab)
        if allow_structure:self._migrer_entetes(tab,values)
        headers=canonical_headers(values[0])
        existing=[dict(zip(headers,row)) for row in values[1:]]
        if tab==HISTORY:
            incoming=reconcilier_cles_historiques(existing,incoming)
        all_headers,updates,appends=plan_sheet(headers,existing,incoming,tab)
        effective_headers=all_headers if allow_structure else headers
        if not allow_structure:
            updates=[(r,c,v) for r,c,v in updates if c<=len(headers)]
            appends=[row[:len(headers)] for row in appends]
        control=None
        if tab==HISTORY:
            independent=lire_cles_independantes(self.session,self.base,tab,properties,headers)
            control=verifier_avant(effective_headers,existing,incoming,appends,
                                  full_source=full_source,observed_keys=independent)
        extra=effective_headers[len(headers):]
        width=properties['gridProperties']['columnCount']
        if len(effective_headers)>width:
            self.check(self.session.post(self.base+':batchUpdate',json={'requests':[
                {'appendDimension':{'sheetId':properties['sheetId'],'dimension':'COLUMNS',
                                    'length':len(effective_headers)-width}}]},timeout=30))
        cells=[]
        if extra:cells.append({'range':f"'{tab}'!{colname(len(headers)+1)}1:{colname(len(effective_headers))}1",
                               'values':[[DISPLAY_NAMES.get(k,k) for k in extra]]})
        cells.extend({'range':f"'{tab}'!{colname(c)}{r}",'values':[[v]]} for r,c,v in updates)
        for start in range(0,len(cells),350):
            self.check(self.session.post(self.base+'/values:batchUpdate',
                json={'valueInputOption':'RAW','data':cells[start:start+350]},timeout=45))
        if appends:
            path=quote("'"+tab+"'!A1",safe="!:'")
            self.check(self.session.post(self.base+'/values/'+path+':append',
                params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},
                json={'values':appends},timeout=45))
        result={'lignes_ajoutees':len(appends),'cellules_actualisees':len(updates),'lignes_source':len(incoming)}
        if control:
            if cells or appends:
                fresh=self.metadata()[tab]
                after=lire_feuille_complete(self.session,self.base,tab,fresh)
                if not after or canonical_headers(after[0])!=effective_headers:
                    raise ErreurSynchronisation('En-tetes modifies pendant la synchronisation')
                after_rows=[dict(zip(effective_headers,row)) for row in after[1:]]
            else:after_rows=existing
            result['controle']=verifier_apres(control,after_rows)
        print(f'SYNC_GOOGLE_SHEETS onglet={tab} lignes_source={len(incoming)} '
              f'cellules_mises_a_jour={len(updates)} lignes_ajoutees={len(appends)}',flush=True)
        return result

    def _synchroniser_kpi(self,tables,source):
        from .kpi_registre import KPI_TAB,calculer_kpi,plan_kpi
        if KPI_TAB not in tables:return {}
        path=quote("'"+KPI_TAB+"'!A1:D100",safe="!:'")
        values=self.check(get_lecture(self.session,self.base+'/values/'+path,timeout=30)).get('values',[])
        updates=plan_kpi(values,calculer_kpi(self.cache,source))
        if updates:self.check(self.session.post(self.base+'/values:batchUpdate',
            json={'valueInputOption':'RAW','data':updates},timeout=45))
        print(f'SYNC_GOOGLE_SHEETS onglet={KPI_TAB} indicateurs_actualises={len(updates)}',flush=True)
        return {KPI_TAB:{'indicateurs_actualises':len(updates)}}

    def synchroniser_tables(self,source,*,scope,full_source=False,allow_structure=False,kpi_source=None):
        start=time.monotonic();before=(self.session.lectures,self.session.ecritures)
        with verrou_local(self.spreadsheet):
            tables=self.metadata();counts={}
            # Vérifier l'historique avant toute publication dans les autres onglets.
            for tab,incoming in sorted(source.items(),key=lambda item:item[0]!=HISTORY):
                if tab not in tables:raise ErreurSynchronisation('Onglet absent : '+tab)
                if not incoming and not full_source:
                    counts[tab]={'lignes_ajoutees':0,'cellules_actualisees':0,'lignes_source':0}
                    continue
                counts[tab]=self._synchroniser_onglet(tab,incoming,tables[tab],
                    full_source=full_source,allow_structure=allow_structure)
            if kpi_source is not None:counts.update(self._synchroniser_kpi(tables,kpi_source))
        print('SHEETS_MOTEUR_UNIQUE '+json.dumps({'perimetre':scope,
            'lectures_api':self.session.lectures-before[0],'ecritures_api':self.session.ecritures-before[1],
            'duree_secondes':round(time.monotonic()-start,3)},ensure_ascii=False),flush=True)
        return counts

    def synchroniser_cycle(self):
        from .sync_google_sheets import SHEET_TABS
        source=self.source()
        return self.synchroniser_tables({tab:source[tab] for tab in SHEET_TABS},scope='CYCLE_PMU',
            full_source=True,allow_structure=True,kpi_source=source)

    def synchroniser_cheval(self,horse,*,include_kpi=True,include_courses=True):
        from .liaison_chevaux_v22 import nom_normalise
        source=self.source();ident=horse['geny']['id']
        history={k:v for k,v in source[HISTORY].items() if str(v.get('identifiant_cheval'))==ident}
        if not history and horse.get('nombre_performances')!=0:
            raise ErreurSynchronisation('Aucune performance a synchroniser pour '+ident)
        allowed={'course_key','numero','historique_statut','historique_nb_courses_datees','historique_maj_utc'}
        courses={k:{f:v for f,v in row.items() if f in allowed} for k,row in source['Courses & Prévisions'].items()
                 if nom_normalise(row.get('cheval'))==nom_normalise(horse['nom'])
                 and str(row.get('historique_statut','')).startswith('HISTO_OK')}
        tables={HISTORY:history}
        if include_courses:tables['Courses & Prévisions']=courses
        return self.synchroniser_tables(tables,scope='CHEVAL' if include_courses else 'RATTRAPAGE',
            kpi_source=source if include_kpi else None)

    def inventaire_rattrapage(self):
        """Lecture complète seule : inventaire et preuve des clés déjà publiées."""
        from datetime import datetime,timezone
        from .sync_google_sheets import lire_feuille_complete,canonical_headers,reconcilier_cles_historiques
        from .identites_chevaux import source_identifiant
        with verrou_local(self.spreadsheet):
            tables=self.metadata();horses=[];seen=set();keys=set();rows=[];control=None
            for tab in (HISTORY,'Courses & Prévisions'):
                if tab not in tables:raise ErreurSynchronisation('Onglet absent : '+tab)
                values=lire_feuille_complete(self.session,self.base,tab,tables[tab])
                if not values:raise ErreurSynchronisation('Onglet sans en-tetes : '+tab)
                headers=canonical_headers(values[0])
                data=[dict(zip(headers,row)) for row in values[1:]]
                if tab==HISTORY:
                    rows=data
                    independent=lire_cles_independantes(self.session,self.base,tab,tables[tab],headers)
                    control=verifier_apres(verifier_avant(headers,data,{},[],
                        full_source=False,observed_keys=independent),data)
                    keys={str(row.get('cle_performance','')) for row in data}
                for row in data:
                    if not row.get('cheval') and not row.get('identifiant_cheval'):continue
                    identity=(tab,str(row.get('identifiant_cheval','')),str(row.get('cheval','')),
                              str(row.get('course_key','')),str(row.get('numero','')),
                              source_identifiant(row.get('identifiant_cheval'),row.get('source_url')))
                    if identity in seen:continue
                    seen.add(identity)
                    horses.append({'nom':row.get('cheval',''),
                        'id':str(row.get('identifiant_cheval','')) if tab==HISTORY else '',
                        'source_url':row.get('source_url','') if tab==HISTORY else '',
                        'engagement':row.get('course_key',''), 'numero':str(row.get('numero','')),
                        'origine':'SHEETS:'+tab})
            expected={}
            for row in reconcilier_cles_historiques(rows,self.source()[HISTORY]).values():
                expected.setdefault(str(row.get('identifiant_cheval','')),set()).add(row['cle_performance'])
            return {'capture_utc':datetime.now(timezone.utc).isoformat(),'chevaux':horses,
                'ids_couverts':[ident for ident,wanted in expected.items() if wanted<=keys],
                'lignes_historique':len(rows),'controle':control}

    def synchroniser_kpi(self):
        with verrou_local(self.spreadsheet):return self._synchroniser_kpi(self.metadata(),self.source())
