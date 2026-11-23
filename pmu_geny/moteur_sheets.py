"""Moteur unique d'écriture Sheets, commun aux publications cheval et cycle."""
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import timezone
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from dashboard.trot_analytics.dates import DATE_PATTERN, DATETIME_PATTERN, afficher_instant, date_kind, depuis_nombre, meme_date_sheets, vers_cellule_operationnelle, vers_nombre

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


def regrouper_cellules(tab, updates):
    """Regrouper les cellules contiguës d'une colonne sans écrire dans les trous."""
    from .sync_google_sheets import colname
    result=[];previous_row=previous_col=None;block=None
    for row,col,value in sorted(updates,key=lambda x:(x[1],x[0])):
        if col==previous_col and row==previous_row+1 and len(block['values'])<2000:
            block['values'].append([value])
        else:
            block={'range':f"'{tab}'!{colname(col)}{row}",'values':[[value]]}
            result.append(block)
        previous_row,previous_col=row,col
    return result


def formats_dates(sheet_id, headers, only=None):
    requests = []
    for col, field in enumerate(headers):
        kind = date_kind(field)
        if kind is None or (only is not None and field not in only):
            continue
        pattern = DATE_PATTERN if kind == "DATE" else DATETIME_PATTERN
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": kind, "pattern": pattern}}},
            "fields": "userEnteredFormat.numberFormat",
        }})
    return requests


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
            params={'fields':'sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)),conditionalFormats)'},timeout=30))
        return {x['properties']['title']: {**x['properties'], 'conditionalFormats': x.get('conditionalFormats', [])}
                for x in doc['sheets']}

    def source(self):
        from .sync_google_sheets import source_rows,limiter_cours_registre,RETIRED_SHEET_COLUMNS
        raw=limiter_cours_registre(source_rows(self.cache))
        return {tab:{key:{field:value for field,value in row.items()
                         if field not in RETIRED_SHEET_COLUMNS.get(tab,())}
                     for key,row in rows.items()} for tab,rows in raw.items()}

    def _formater_observations(self, tab, sheet_id, headers, groupe, *, appends=False):
        from .sync_google_sheets import colname

        positions = {headers.index(name): label for name, label in groupe.libelles.items()}
        ranges = [f"'{tab}'!{colname(i+1)}1:{colname(i+1)}2" for i in positions]
        champs = {'ranges': ranges, 'fields': (
            'sheets(data(startColumn,rowData(values(note,userEnteredValue,userEnteredFormat(textFormat(italic))))))'
        )}
        def relire():
            doc = self.check(get_lecture(self.session, self.base, params=champs, timeout=30))
            return {block['startColumn'] if 'startColumn' in block else 0:
                    [row.get('values', [{}])[0] if row.get('values') else {}
                     for row in block.get('rowData', [])]
                    for sheet in doc.get('sheets', []) for block in sheet.get('data', [])}

        def conforme(cells, label):
            return (len(cells) == 2 and cells[0].get('userEnteredValue', {}).get('stringValue') == label
                    and cells[0].get('note') == groupe.usage and all(
                        cell.get('userEnteredFormat', {}).get('textFormat', {}).get('italic', False) == groupe.italique
                        for cell in cells))

        observed = relire()
        requests = []
        for i, label in positions.items():
            if not appends and conforme(observed.get(i, []), label):
                continue
            column = {'sheetId': sheet_id, 'startColumnIndex': i, 'endColumnIndex': i + 1}
            format_cell = {'userEnteredFormat': {'textFormat': {'italic': groupe.italique}}}
            requests.extend([
                {'repeatCell': {'range': {**column, 'startRowIndex': 0, 'endRowIndex': 1},
                                'cell': {**format_cell, 'note': groupe.usage},
                                'fields': 'userEnteredFormat.textFormat.italic,note'}},
                {'repeatCell': {'range': {**column, 'startRowIndex': 1}, 'cell': format_cell,
                                'fields': 'userEnteredFormat.textFormat.italic'}},
            ])
        if requests:
            self.check(self.session.post(self.base+':batchUpdate', json={'requests': requests}, timeout=30))
            observed = relire()
        if not all(conforme(observed.get(i, []), label) for i, label in positions.items()):
            raise ErreurSynchronisation('En-têtes ou format des observations non confirmés dans Sheets')
        print(f'COLONNES_OBSERVATION_VERIFIEES={len(positions)} italique={groupe.italique}', flush=True)

    def _formater_profils(self, properties, headers):
        from dashboard.trot_analytics.profils import (
            CRACK_CONFIRME, HAUT_POTENTIEL, PALETTE, SEPARATEUR_PROFILS,
        )
        from .sync_google_sheets import colname

        colonnes = [headers.index(nom) for nom in ('cheval', 'profil_partant')]
        lignes = properties['gridProperties']['rowCount']
        plages = [{'sheetId': properties['sheetId'], 'startRowIndex': 1, 'endRowIndex': lignes,
                   'startColumnIndex': i, 'endColumnIndex': i + 1} for i in colonnes]
        anciennes = properties['conditionalFormats']
        prochain_index = len(anciennes)
        requetes = []
        ref = f'${colname(colonnes[1] + 1)}2'

        def rgb(couleur):
            return {canal: round(int(couleur[i:i+2], 16) / 255, 6)
                    for canal, i in zip(('red', 'green', 'blue'), (1, 3, 5))}

        def meme_format(actuel, attendu):
            # Sheets renvoie parfois les composantes RGB en simple précision.
            return actuel.get('textFormat', {}).get('bold') is True and all(
                abs(obtenu.get(canal, 0) - valeur) < 1e-6
                for obtenu, cible in (
                    (actuel.get('backgroundColorStyle', {}).get('rgbColor', {}),
                     attendu['backgroundColorStyle']['rgbColor']),
                    (actuel.get('textFormat', {}).get('foregroundColorStyle', {}).get('rgbColor', {}),
                     attendu['textFormat']['foregroundColorStyle']['rgbColor']),
                ) for canal, valeur in cible.items())

        for statut, (fond, texte, _) in PALETTE.items():
            if statut == CRACK_CONFIRME:
                cumul = SEPARATEUR_PROFILS + HAUT_POTENTIEL
                valeurs = (CRACK_CONFIRME, CRACK_CONFIRME + cumul, 'Crack', 'Crack' + cumul)
                formule = '=' + '+'.join(f'({ref}="{valeur}")' for valeur in valeurs) + '>0'
                ancienne_formule = f'={ref}="Crack"'
            else:
                formule = ancienne_formule = f'={ref}="{statut}"'
            condition = {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': formule}]}
            format_cellule = {
                'backgroundColorStyle': {'rgbColor': rgb(fond)},
                'textFormat': {'bold': True, 'foregroundColorStyle': {'rgbColor': rgb(texte)}},
            }
            regle = {'ranges': plages, 'booleanRule': {'condition': condition, 'format': format_cellule}}
            index = next((i for i, ancienne in enumerate(anciennes)
                          if ancienne.get('booleanRule', {}).get('condition', {}).get('values')
                          in ([{'userEnteredValue': formule}], [{'userEnteredValue': ancienne_formule}])
                          and ancienne['booleanRule']['condition'].get('type') == 'CUSTOM_FORMULA'), None)
            if index is None:
                requetes.append({'addConditionalFormatRule': {'index': prochain_index, 'rule': regle}})
                prochain_index += 1
            elif (anciennes[index].get('ranges') != plages
                  or anciennes[index]['booleanRule']['condition'] != condition
                  or not meme_format(anciennes[index]['booleanRule'].get('format', {}), format_cellule)):
                requetes.append({'updateConditionalFormatRule': {
                    'sheetId': properties['sheetId'], 'index': index, 'rule': regle}})
        if requetes:
            self.check(self.session.post(self.base + ':batchUpdate',
                json={'requests': requetes}, timeout=30))

    def _synchroniser_onglet(self,tab,incoming,properties,*,full_source,allow_structure):
        from .sync_google_sheets import lire_feuille_complete,canonical_headers,plan_sheet,colname,DISPLAY_NAMES,reconcilier_cles_historiques,RETIRED_SHEET_COLUMNS,SHEET_HEADER_LABELS
        values=lire_feuille_complete(self.session,self.base,tab,properties,raw_dates=True)
        if not values:raise ErreurSynchronisation('Onglet sans en-tetes : '+tab)
        if allow_structure:
            removed=[i for i,name in enumerate(canonical_headers(values[0])) if name in RETIRED_SHEET_COLUMNS.get(tab,())]
            if removed:
                self.check(self.session.post(self.base+':batchUpdate',json={'requests':[
                    {'deleteDimension':{'range':{'sheetId':properties['sheetId'],'dimension':'COLUMNS',
                                               'startIndex':i,'endIndex':i+1}}}
                    for i in reversed(removed)]},timeout=30))
                properties=self.metadata()[tab]
                values=lire_feuille_complete(self.session,self.base,tab,properties,raw_dates=True)
                if not values:raise ErreurSynchronisation('En-tetes absents apres retrait des colonnes')
            labels=SHEET_HEADER_LABELS.get(tab,{})
            replacements=[{'range':f"'{tab}'!{colname(i+1)}1",'values':[[labels[name]]]} for i,name in
                          enumerate(canonical_headers(values[0])) if name in labels and values[0][i]!=labels[name]]
            if replacements:
                self.check(self.session.post(self.base+'/values:batchUpdate',
                    json={'valueInputOption':'RAW','data':replacements},timeout=30))
                values=lire_feuille_complete(self.session,self.base,tab,properties,raw_dates=True)
        headers=canonical_headers(values[0])
        existing=[{name: depuis_nombre(name, value) for name, value in zip(headers, row)}
                  for row in values[1:]]
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
        structure = []
        if len(effective_headers)>width:
            structure.append({'appendDimension':{'sheetId':properties['sheetId'],'dimension':'COLUMNS',
                                                 'length':len(effective_headers)-width}})
        exemplars = {
            'gagnant_direct_selection': 'top3_direct_top3',
            'gagnant_ml_selection': 'ml_top3',
            **{f'gagnant_{mode}_{field}': reference
               for mode in ('direct', 'ml')
               for field, reference in (
                   ('numero', f'top3_{mode}_numeros'), ('nom', f'top3_{mode}_noms'),
                   ('rang', f'score_{mode}'), ('verdict', f'score_{mode}'))},
        }
        sheet_id = properties['sheetId']
        for index, name in enumerate(extra, start=len(headers)):
            reference = exemplars.get(name)
            if reference not in headers:
                continue
            source = headers.index(reference)
            structure.extend([
                {'copyPaste': {
                    'source': {'sheetId':sheet_id,'startColumnIndex':source,'endColumnIndex':source+1},
                    'destination': {'sheetId':sheet_id,'startColumnIndex':index,'endColumnIndex':index+1},
                    'pasteType': 'PASTE_FORMAT',
                }},
                {'updateDimensionProperties': {
                    'range': {'sheetId':sheet_id,'dimension':'COLUMNS','startIndex':index,'endIndex':index+1},
                    'properties': {'pixelSize':205 if name.endswith('_nom') else 175},
                    'fields': 'pixelSize',
                }},
            ])
        encoder = vers_nombre if tab == HISTORY else vers_cellule_operationnelle
        staged = {(row, col): encoder(effective_headers[col - 1], value)
                  for row, col, value in updates}
        if allow_structure:
            for row_number, raw in enumerate(values[1:], start=2):
                for col, (field, value) in enumerate(zip(headers, raw), start=1):
                    if tab != HISTORY and date_kind(field) == "DATE_TIME":
                        continue  # La représentation d'un instant existant ne motive aucune réécriture.
                    converted = encoder(field, value)
                    if converted != value:
                        staged.setdefault((row_number, col), converted)
        updates = [(row, col, value) for (row, col), value in staged.items()]
        appends = [[encoder(field, value) for field, value in zip(effective_headers, row)]
                   for row in appends]
        changed_dates = {field for field in extra if date_kind(field)}
        changed_dates.update(effective_headers[col - 1] for _, col, _ in updates
                             if date_kind(effective_headers[col - 1]))
        if appends:
            changed_dates.update(field for field in effective_headers if date_kind(field))
        if changed_dates:
            only = changed_dates if changed_dates == {'ipr_calcul_utc'} else None
            structure.extend(formats_dates(sheet_id, effective_headers, only))
        if structure:
            self.check(self.session.post(self.base+':batchUpdate',json={'requests':structure},timeout=30))
        cells=[]
        if extra:cells.append({'range':f"'{tab}'!{colname(len(headers)+1)}1:{colname(len(effective_headers))}1",
                               'values':[[DISPLAY_NAMES.get(k,k) for k in extra]]})
        cells.extend(regrouper_cellules(tab,updates))
        for start in range(0,len(cells),350):
            self.check(self.session.post(self.base+'/values:batchUpdate',
                json={'valueInputOption':'RAW','data':cells[start:start+350]},timeout=45))
        if appends:
            path=quote("'"+tab+"'!A1",safe="!:'")
            self.check(self.session.post(self.base+'/values/'+path+':append',
                params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},
                json={'values':appends},timeout=45))
        if tab == 'Courses & Prévisions' and allow_structure and {'cheval', 'profil_partant'} <= set(effective_headers):
            self._formater_profils(self.metadata()[tab] if appends else properties, effective_headers)
        if tab == 'Courses & Prévisions' and allow_structure:
            from .ipr import actif
            from dashboard.trot_analytics.usages import IPR
            if actif():
                self._formater_observations(tab, sheet_id, effective_headers, IPR, appends=bool(appends))
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

    def lire_courses(self, tables):
        from .sync_google_sheets import canonical_headers, lire_feuille_complete
        tab = 'Courses & Prévisions'
        if tab not in tables:
            raise ErreurSynchronisation('Onglet absent : ' + tab)
        values = lire_feuille_complete(self.session, self.base, tab, tables[tab])
        if not values:
            raise ErreurSynchronisation('Onglet sans en-têtes : ' + tab)
        headers = canonical_headers(values[0])
        return [dict(zip(headers, row)) for row in values[1:] if row]

    def _synchroniser_kpi(self,tables,source,*,relire_courses=False):
        from .kpi_registre import KPI_TAB, PUBLISHED_PREFIXES, calculer_kpi, plan_kpi, totaux_reference
        if KPI_TAB not in tables:
            raise ErreurSynchronisation('Onglet absent : ' + KPI_TAB)
        path=quote("'"+KPI_TAB+"'!A:E",safe="!:'")
        values=self.check(get_lecture(self.session,self.base+'/values/'+path,
            params={'valueRenderOption':'UNFORMATTED_VALUE'},timeout=30)).get('values',[])
        sheets_courses = self.lire_courses(tables) if relire_courses else None
        if sheets_courses is not None:
            from .sync_google_sheets import COTES_COLUMNS, sheet_value
            published = {(row.get('course_key'), str(row.get('numero'))): row for row in sheets_courses}
            verified = set()
            for row in source['Courses & Prévisions'].values():
                if 'cote_releve_utc' not in row:
                    continue
                key = (row['course_key'], str(row['numero']))
                actual = published.get(key, {})
                for field in COTES_COLUMNS:
                    if field in row and not meme_date_sheets(
                            field, sheet_value(field, row[field]), sheet_value(field, actual.get(field))):
                        raise ErreurSynchronisation(f'Cote Sheets différente du collecteur : {key}, {field}')
                if row['cote_releve_utc']:
                    verified.add(key)
            print(f'COTES_SHEETS_VERIFIEES {len(verified)} cotes sur '
                  f'{len({key for key, _ in verified})} courses', flush=True)
        metrics = calculer_kpi(self.cache, source, sheets_courses=sheets_courses)
        # La colonne Valeur mélange dates, taux et effectifs. Seules les
        # valeurs horodatées sont présentées en texte français, en UTC.
        metrics = {key: (afficher_instant(value, timezone.utc) or value, definition)
                   for key, (value, definition) in metrics.items()}
        updates=plan_kpi(values,metrics)
        if updates:
            properties = tables[KPI_TAB]
            row_count = properties['gridProperties']['rowCount']
            last_row = max(int(re.search(r'\d+$', entry['range'])[0]) for entry in updates)
            if last_row > row_count:
                self.check(self.session.post(self.base+':batchUpdate', json={'requests': [
                    {'appendDimension': {'sheetId': properties['sheetId'], 'dimension': 'ROWS',
                                         'length': last_row-row_count}}]}, timeout=30))
            self.check(self.session.post(self.base+'/values:batchUpdate',
                json={'valueInputOption':'RAW','data':updates},timeout=45))
        totals = totaux_reference(metrics)
        managed = {key: (value, definition, totals.get(key, '')) for key, (value, definition) in metrics.items()
                   if key.startswith(PUBLISHED_PREFIXES)}
        if managed:
            if updates:
                values = self.check(get_lecture(self.session, self.base+'/values/'+path,
                    params={'valueRenderOption':'UNFORMATTED_VALUE'}, timeout=30)).get('values', [])
            seen = set()
            for row in values[1:]:
                if len(row) < 2 or row[1] not in managed:
                    continue
                key = row[1]
                if key in seen:
                    raise ErreurSynchronisation('Indicateur KPI en double : ' + key)
                seen.add(key)
                for index, expected in enumerate(managed[key], 2):
                    if index == 4 and key not in totals:
                        continue
                    actual = row[index] if index < len(row) else ''
                    if actual != expected and not (
                            isinstance(expected, (float, int)) and isinstance(actual, (float, int))
                            and abs(expected - actual) <= 1e-12):
                        raise ErreurSynchronisation('Vérification Sheets KPI échouée : ' + key)
            if seen != managed.keys():
                raise ErreurSynchronisation('Indicateurs KPI absents après synchronisation')
            identity = {key: managed[key][0] for key in sorted(seen)
                        if key.startswith(('Rattrapage · Chevaux ', 'Rattrapage · Contextes '))}
            if identity:
                print('KPI_IDENTIFICATION_GENY_VERIFIES ' + json.dumps(identity, ensure_ascii=False), flush=True)
            print(f'KPI_MATURITE_ML_VERIFIES={sum(k.startswith("Maturité ML · ") for k in seen)}',
                  f'KPI_SHEETS_VERIFIES={len(seen)}', flush=True)
        if relire_courses:
            print('KPI_COHORTES_SHEETS ' + json.dumps({
                key: value for key, (value, _) in metrics.items()
                if key.startswith(('J · ', 'J+1 · ', 'Rattrapage · lot de 96 · '))},
                ensure_ascii=False), flush=True)
        print(f'SYNC_GOOGLE_SHEETS onglet={KPI_TAB} indicateurs_actualises={len(updates)}',flush=True)
        if os.getenv('PMU_KPI_HISTORY')=='true':
            from .historique_kpi import enregistrer
            enregistrer(self,tables)
        return {KPI_TAB:{'indicateurs_actualises':len(updates), 'indicateurs_verifies':len(managed)}}

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

    def synchroniser_cycle(self,include_kpi=True):
        from .sync_google_sheets import SHEET_TABS
        source=self.source()
        return self.synchroniser_tables({tab:source[tab] for tab in SHEET_TABS},scope='CYCLE_PMU',
            full_source=True,allow_structure=True,kpi_source=source if include_kpi else None)

    def synchroniser_cheval(self,horse,*,include_kpi=True,include_courses=True):
        from .liaison_chevaux_v22 import nom_normalise
        source=self.source();ident=horse['geny']['id']
        history={k:v for k,v in source[HISTORY].items() if str(v.get('identifiant_cheval'))==ident}
        if not history and horse.get('nombre_performances')!=0:
            raise ErreurSynchronisation('Aucune performance a synchroniser pour '+ident)
        allowed={'course_key','numero','historique_statut','historique_nb_courses_datees','historique_maj_utc'}
        courses={k:{f:v for f,v in row.items() if f in allowed} for k,row in source['Courses & Prévisions'].items()
                 if nom_normalise(row.get('cheval'))==nom_normalise(horse['nom'])
                 and str(row.get('historique_statut','')).startswith(('HISTO_OK','HISTO_PARTIEL'))}
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
        with verrou_local(self.spreadsheet):return self._synchroniser_kpi(self.metadata(),self.source(),relire_courses=True)
