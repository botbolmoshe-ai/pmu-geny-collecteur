"""Moteur unique d'écriture Sheets, commun aux publications cheval et cycle."""
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from contextlib import contextmanager
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from dashboard.trot_analytics.dates import DATE_PATTERN, DATETIME_PATTERN, DISPLAY_PREFIX, date_kind, depuis_nombre, meme_date_sheets, vers_cellule_operationnelle, vers_nombre

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
    from .dates_registre import SOURCES
    composite_labels = {DISPLAY_PREFIX + label for label in SOURCES.values()}
    for col, field in enumerate(headers):
        kind = ('DATE_TIME' if field.startswith(DISPLAY_PREFIX) and field not in composite_labels
                else date_kind(field))
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
        self.observations_verifiees = False

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
            params={'fields':'sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)),conditionalFormats,basicFilter)'},timeout=30))
        return {x['properties']['title']: {**x['properties'], 'conditionalFormats': x.get('conditionalFormats', []), 'basicFilter': x.get('basicFilter')}
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

    def _correspondances_archivees(self, existing, incoming):
        from .historiques_incrementaux import course_geny_connue
        from .identites_chevaux import IndexGeny, TentativesGeny, champs_correspondance_geny
        from .liaison_chevaux_v22 import nom_normalise

        participants = [r for r in existing if r.get('course_key') and r.get('numero') and r.get('cheval')]
        cles = Counter((r['course_key'], str(r['numero'])) for r in participants)
        noms = Counter((r['course_key'], nom_normalise(r['cheval'])) for r in participants)
        archives = {}
        for row in participants:
            key, number = row['course_key'], str(row['numero'])
            cle = f'{key}|{number}'
            if cle in incoming or cles[key, number] != 1:
                continue
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}\|[^|]+\|R\d+C\d+', str(key)):
                continue
            archives[cle] = row
        if not archives:
            return {}
        index = IndexGeny(self.cache)
        tentatives = TentativesGeny(self.cache, datetime.now(timezone.utc))
        result = {}
        for cle, row in archives.items():
            date, _, code = row['course_key'].split('|')
            number, name = str(row['numero']), row['cheval']
            engagement = f'{date}_{code}'
            age = str(row.get('age_ans', ''))
            year = int(date[:4]) - int(age) if age.isdigit() else None
            cid = course_geny_connue(self.cache, engagement)
            link, methode = index.resoudre(name, cid, number, annee=year,
                                          nom_repris=noms[row['course_key'], nom_normalise(name)] > 1)
            tentative = tentatives.retrouver(engagement, number, name, None)
            result[cle] = {'course_key': row['course_key'], 'numero': number,
                           **champs_correspondance_geny(tentative, None, link.get('id'), methode)}
        return result

    def _controler_correspondances(self, tab, properties, headers, incoming, *, formater):
        from dashboard.trot_analytics.correspondance_geny import CHAMP, STATUTS
        from .sync_google_sheets import colname

        index = headers.index(CHAMP)
        col = colname(index + 1)
        sheet_id = properties['sheetId']
        plage = {'sheetId': sheet_id, 'startRowIndex': 1, 'startColumnIndex': index, 'endColumnIndex': index + 1}
        scope = f"'{tab}'!{col}2:{col}"
        # Relire les clés indépendamment pour associer chaque note à la bonne ligne.
        cles = []
        for field in ('course_key', 'numero'):
            c = colname(headers.index(field) + 1)
            cles.append(f"'{tab}'!{c}2:{c}")
        values = self.check(get_lecture(self.session, self.base + '/values:batchGet',
            params={'ranges': cles, 'valueRenderOption': 'UNFORMATTED_VALUE'}, timeout=30))
        keys, numbers = ([row[0] if row else '' for row in part.get('values', [])]
                         for part in values['valueRanges'])
        grid = self.check(get_lecture(self.session, self.base,
            params={'ranges': scope, 'fields': 'sheets(data(startRow,rowData(values(note,effectiveValue))))'},
            timeout=30))
        cells = (grid['sheets'][0].get('data') or [{}])[0].get('rowData', [])
        requests = []
        confirmed = set()
        for row, (key, number) in enumerate(zip(keys, numbers), start=2):
            row_key = f'{key}|{number}'
            expected = incoming.get(row_key)
            if not expected or row_key in confirmed:
                continue
            confirmed.add(row_key)
            cell = ((cells[row-2].get('values') or [{}])[0] if row-2 < len(cells) else {})
            if cell.get('effectiveValue', {}).get('stringValue') != expected[CHAMP]:
                raise ErreurSynchronisation('Correspondance Geny non confirmée dans Sheets : ' + row_key)
            note = expected.get('_note_correspondance_geny', '')
            if cell.get('note', '') != note:
                requests.append({'updateCells': {'start': {'sheetId': sheet_id, 'rowIndex': row-1,
                    'columnIndex': index}, 'rows': [{'values': [{'note': note}]}], 'fields': 'note'}})
        if confirmed != incoming.keys():
            raise ErreurSynchronisation('Correspondances Geny absentes après publication')
        if formater:
            anciennes = properties['conditionalFormats']
            for code, (_, fond) in STATUTS.items():
                condition = {'type': 'TEXT_EQ', 'values': [{'userEnteredValue': code}]}
                rgb = {canal: int(fond[i:i+2], 16)/255 for canal, i in zip(('red','green','blue'), (1,3,5))}
                existing = next((i for i, rule in enumerate(anciennes)
                    if rule.get('booleanRule', {}).get('condition') == condition
                    and rule.get('ranges', [{}])[0].get('startColumnIndex') == index), None)
                if existing is None:
                    requests.append({'addConditionalFormatRule': {'index': len(anciennes),
                        'rule': {'ranges': [plage], 'booleanRule': {'condition': condition,
                            'format': {'backgroundColorStyle': {'rgbColor': rgb}}}}}})
            filtre = properties.get('basicFilter')
            if filtre and filtre.get('range', {}).get('endColumnIndex', len(headers)) < len(headers):
                requests.append({'setBasicFilter': {'filter': {**filtre, 'range': {
                    **filtre['range'], 'endColumnIndex': len(headers)}}}})
            elif not filtre:
                requests.append({'setBasicFilter': {'filter': {'range': {'sheetId': sheet_id,
                    'startRowIndex': 0, 'startColumnIndex': 0, 'endColumnIndex': len(headers)}}}})
        for start in range(0, len(requests), 250):
            self.check(self.session.post(self.base+':batchUpdate',
                json={'requests': requests[start:start+250]}, timeout=30))
        return len(confirmed)

    def _synchroniser_onglet(self,tab,incoming,properties,*,full_source,allow_structure,
                             reconciliation=None):
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
        from dashboard.trot_analytics.correspondance_geny import CHAMP
        statut_seul = tab == 'Courses & Prévisions' and not allow_structure and any(CHAMP in row for row in incoming.values())
        if statut_seul:
            deja_publies = {f"{row.get('course_key')}|{row.get('numero')}" for row in existing}
            incoming = {key: row for key, row in incoming.items() if key in deja_publies}
        diagnostics, anomalies = {}, {}
        if tab == 'Courses & Prévisions' and reconciliation is not None:
            from .reconciliation_historiques import CHAMPS_HISTORIQUE, ReconciliationHistoriques
            diagnostics, anomalies = ReconciliationHistoriques(
                self.cache, reconciliation['historique']).participations(existing, incoming)
            # Seule la projection courante possède ces champs de restitution.
            legacy = CHAMPS_HISTORIQUE | {CHAMP, '_note_correspondance_geny'}
            incoming = {key: {field: value for field, value in row.items() if field not in legacy}
                        for key, row in incoming.items()}
            for key, diagnostic in diagnostics.items():
                incoming[key] = {**incoming.get(key, {}), **diagnostic}
            statut_seul = statut_seul or bool(diagnostics and not allow_structure)
        elif statut_seul:
            incoming = {**incoming, **self._correspondances_archivees(existing, incoming)}
        if tab==HISTORY:
            incoming=reconcilier_cles_historiques(existing,incoming)
        all_headers,updates,appends=plan_sheet(headers,existing,incoming,tab)
        effective_headers = all_headers if allow_structure else headers
        if statut_seul and CHAMP not in headers:
            effective_headers = [*headers, CHAMP]
        if not allow_structure:
            allowed = {i for i, field in enumerate(all_headers, 1) if field in effective_headers}
            updates = [(r, effective_headers.index(all_headers[c-1])+1, v) for r, c, v in updates if c in allowed]
            appends = [[row[all_headers.index(field)] for field in effective_headers] for row in appends]
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
        legacy_history = tab == HISTORY and not any(field.startswith(DISPLAY_PREFIX)
                                                    for field in effective_headers)
        encoder = vers_nombre if legacy_history else vers_cellule_operationnelle
        staged = {(row, col): encoder(effective_headers[col - 1], value)
                  for row, col, value in updates}
        if allow_structure:
            for row_number, raw in enumerate(values[1:], start=2):
                for col, (field, value) in enumerate(zip(headers, raw), start=1):
                    if not legacy_history and date_kind(field) == "DATE_TIME":
                        continue  # La représentation d'un instant existant ne motive aucune réécriture.
                    converted = encoder(field, value)
                    if converted != value:
                        staged.setdefault((row_number, col), converted)
        updates = [(row, col, value) for (row, col), value in staged.items()]
        appends = [[encoder(field, value) for field, value in zip(effective_headers, row)]
                   for row in appends]
        from .dates_registre import enrichir_publication
        updates = enrichir_publication(tab, effective_headers, updates, appends)
        changed_dates = {field for field in extra if date_kind(field)}
        changed_dates.update(effective_headers[col - 1] for _, col, _ in updates
                             if date_kind(effective_headers[col - 1]))
        if appends:
            changed_dates.update(field for field in effective_headers
                                 if date_kind(field) or field.startswith(DISPLAY_PREFIX))
        if changed_dates:
            only = changed_dates if changed_dates == {'ipr_calcul_utc'} else None
            structure.extend(formats_dates(sheet_id, effective_headers, only))
        if structure:
            self.check(self.session.post(self.base+':batchUpdate',json={'requests':structure},timeout=30))
        cells=[]
        if extra:cells.append({'range':f"'{tab}'!{colname(len(headers)+1)}1:{colname(len(effective_headers))}1",
                               'values':[[DISPLAY_NAMES.get(k,k) for k in extra]]})
        if any(field.startswith(DISPLAY_PREFIX) for field in effective_headers):
            # Une date technique et son affichage sont écrits dans le même lot.
            by_row_block = {}
            for update in updates:
                by_row_block.setdefault((update[0] - 2) // 200, []).append(update)
            batches = ([cells] if cells else []) + [
                regrouper_cellules(tab, block) for block in by_row_block.values()
            ]
        else:
            cells.extend(regrouper_cellules(tab, updates))
            batches = [cells[start:start + 350] for start in range(0, len(cells), 350)]
        for batch in batches:
            self.check(self.session.post(self.base+'/values:batchUpdate',
                json={'valueInputOption':'RAW','data':batch},timeout=45))
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
                self.observations_verifiees = False
                try:
                    self._formater_observations(tab, sheet_id, effective_headers, IPR, appends=bool(appends))
                    self.observations_verifiees = True
                except Exception as exc:
                    print(f'::warning::Format IPR non certifié ({type(exc).__name__})', flush=True)
        if tab == HISTORY and appends:
            from dashboard.trot_analytics.usages import GENY_HISTORIQUE
            if GENY_HISTORIQUE.libelles.keys() <= set(effective_headers):
                self._formater_observations(tab, sheet_id, effective_headers, GENY_HISTORIQUE, appends=True)
        result={'lignes_ajoutees':len(appends),'cellules_actualisees':len(updates),'lignes_source':len(incoming)}
        correspondances = {key: row for key, row in incoming.items() if CHAMP in row}
        if tab == 'Courses & Prévisions' and CHAMP in effective_headers and correspondances:
            formater = allow_structure or CHAMP in extra
            result['correspondances_geny_verifiees'] = self._controler_correspondances(
                tab, self.metadata()[tab] if formater else properties, effective_headers,
                correspondances, formater=formater)
        if diagnostics:
            # Confirmer les trois champs courants sur les lignes réellement écrites.
            changed = (bool(appends) or any(effective_headers[col - 1] in CHAMPS_HISTORIQUE
                                            for _, col, _ in updates))
            after = self.lire_courses(self.metadata()) if changed else existing
            confirmed = {f"{r.get('course_key')}|{r.get('numero')}": r for r in after}
            for key, expected in diagnostics.items():
                actual = confirmed.get(key, {})
                for field in CHAMPS_HISTORIQUE.intersection(effective_headers):
                    target = expected[field]
                    value = actual.get(field)
                    if field == 'historique_maj_utc':
                        equal = meme_date_sheets(field, value or '', target)
                    else:
                        equal = str(value or '0') == str(target)
                    if not equal:
                        raise ErreurSynchronisation(f'Historique courant différent dans Sheets : {key}, {field}')
            reconciliation['courses'] = after
            result['reconciliation_historiques'] = {
                'participations_verifiees': len(diagnostics),
                'ecarts_avant': dict(anomalies),
                'etats': dict(Counter(row['historique_statut'] for row in diagnostics.values())),
            }
            print('RECONCILIATION_HISTORIQUES ' + json.dumps(result['reconciliation_historiques']), flush=True)
        if control:
            if batches or appends:
                fresh=self.metadata()[tab]
                after=lire_feuille_complete(self.session,self.base,tab,fresh)
                if not after or canonical_headers(after[0])!=effective_headers:
                    raise ErreurSynchronisation('En-tetes modifies pendant la synchronisation')
                after_rows=[dict(zip(effective_headers,row)) for row in after[1:]]
            else:after_rows=existing
            result['controle']=verifier_apres(control,after_rows)
            if reconciliation is not None:
                reconciliation['historique'] = [
                    {name: depuis_nombre(name, value) for name, value in row.items()} for row in after_rows
                ]
        print(f'SYNC_GOOGLE_SHEETS onglet={tab} lignes_source={len(incoming)} '
              f'cellules_mises_a_jour={len(updates)} lignes_ajoutees={len(appends)}',flush=True)
        return result

    def migrer_structure_geny(self, sauvegarde, *, appliquer=False):
        """Sauvegarder ou appliquer le même instantané sous le verrou du registre."""
        from .migration_geny import plages_migration, planifier, verifier
        from .structure_geny import couverture
        from .sync_google_sheets import canonical_headers, colname, lire_feuille_complete, reconcilier_cles_historiques
        from dashboard.trot_analytics.usages import GENY_HISTORIQUE

        with verrou_local(self.spreadsheet):
            props = self.metadata()[HISTORY]
            raw = lire_feuille_complete(self.session, self.base, HISTORY, props, raw_dates=True, render_option='FORMULA')
            if not raw:
                raise ErreurSynchronisation('Historique vide')
            headers = canonical_headers(raw[0])
            if any(len(row) > len(headers) for row in raw[1:]):
                raise ErreurSynchronisation('Données présentes au-delà des en-têtes historiques')
            rows = [dict(zip(headers, row)) for row in raw[1:]]
            independent = lire_cles_independantes(self.session, self.base, HISTORY, props, headers)
            keys = [str(row.get('cle_performance', '')).strip() for row in rows]
            if independent != Counter(filter(None, keys)):
                raise ErreurSynchronisation('Inventaire indépendant des clés incohérent')
            normalized = [{field: depuis_nombre(field, value) for field, value in row.items()} for row in rows]
            archives = reconcilier_cles_historiques(normalized, self.source()[HISTORY])
            columns, updates, conflicts, duplicates = planifier(headers, rows, archives)
            sauvegarde(raw)
            summary = {'lignes': len(rows), 'doublons': duplicates, 'conflits': conflicts,
                       'cellules_planifiees': len(updates), 'colonnes_ajoutees': len(columns) - len(headers)}
            if not appliquer:
                return summary
            sheet_id = props['sheetId']
            width = props['gridProperties']['columnCount']
            if len(columns) > width:
                self.check(self.session.post(self.base + ':batchUpdate', json={'requests': [
                    {'appendDimension': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
                                         'length': len(columns) - width}},
                ]}, timeout=30))
            visible = raw[0] + [GENY_HISTORIQUE.libelles[field] for field in columns[len(headers):]]
            cells = plages_migration(HISTORY, updates)
            if columns != headers:
                cells.insert(0, {'range': f"'{HISTORY}'!{colname(len(headers) + 1)}1:{colname(len(columns))}1",
                                 'values': [visible[len(headers):]]})
            for start in range(0, len(cells), 8):
                payload = {'valueInputOption': 'RAW', 'data': cells[start:start + 8]}
                response = self.session.post(self.base + '/values:batchUpdate', json=payload, timeout=90)
                if response.status_code == 429:
                    time.sleep(60)
                    response = self.session.post(self.base + '/values:batchUpdate', json=payload, timeout=90)
                self.check(response)
            self._formater_observations(HISTORY, sheet_id, columns, GENY_HISTORIQUE)
            fresh = self.metadata()[HISTORY]
            after = lire_feuille_complete(self.session, self.base, HISTORY, fresh, raw_dates=True, render_option='FORMULA')
            verifier(raw, after, headers, visible, updates)
            after_keys = lire_cles_independantes(self.session, self.base, HISTORY, fresh, columns)
            if independent != after_keys:
                raise ErreurSynchronisation('Clés historiques modifiées')
            summary['couverture'] = couverture([dict(zip(columns, row)) for row in after[1:]])
            return summary

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

    def _synchroniser_kpi(self,tables,source,*,relire_courses=False,courses_verifiees=None):
        from .kpi_registre import (
            INDICATEURS_RESULTATS, KPI_TAB, PUBLISHED_PREFIXES, calculer_kpi, plan_kpi, totaux_reference,
        )
        if KPI_TAB not in tables:
            raise ErreurSynchronisation('Onglet absent : ' + KPI_TAB)
        path=quote("'"+KPI_TAB+"'!A:E",safe="!:'")
        values=self.check(get_lecture(self.session,self.base+'/values/'+path,
            params={'valueRenderOption':'UNFORMATTED_VALUE'},timeout=30)).get('values',[])
        sheets_courses = self.lire_courses(tables) if relire_courses else courses_verifiees
        if relire_courses:
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
        from .dates_registre import nombre_kpi
        from .migration_dates_sheets import format_cell
        dates = {key: value for key, (value, _) in metrics.items() if nombre_kpi(value, key) != value}
        metrics = {key: (nombre_kpi(value, key), definition)
                   for key, (value, definition) in metrics.items()}
        updates=plan_kpi(values,metrics)
        if updates:
            properties = tables[KPI_TAB]
            row_count = properties['gridProperties']['rowCount']
            last_row = max(int(re.search(r'\d+$', entry['range'])[0]) for entry in updates)
            structure = []
            if last_row > row_count:
                structure.append({'appendDimension': {'sheetId': properties['sheetId'], 'dimension': 'ROWS',
                                                      'length': last_row-row_count}})
            for entry in updates:
                cell = re.search(r'!([AC])(\d+)', entry['range'])
                if not cell:
                    continue
                first, row = cell[1], int(cell[2])
                label = (entry['values'][0][1] if first == 'A' else
                         values[row - 1][1] if first == 'C' else '')
                if label in dates:
                    structure.append(format_cell(properties['sheetId'], row, 2, 'DATE_TIME',
                                                 note=f'Affichage Europe/Paris. Source : {dates[label]}'))
            if structure:
                self.check(self.session.post(self.base+':batchUpdate',
                    json={'requests': structure}, timeout=30))
            self.check(self.session.post(self.base+'/values:batchUpdate',
                json={'valueInputOption':'RAW','data':updates},timeout=45))
        totals = totaux_reference(metrics)
        managed = {key: (value, definition, totals.get(key, '')) for key, (value, definition) in metrics.items()
                   if key.startswith(PUBLISHED_PREFIXES) or (
                       key in INDICATEURS_RESULTATS and any(len(row) > 1 and row[1] == key for row in values))}
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
                            and abs(expected - actual) <= (1e-10 if key in dates and index == 2 else 1e-12)):
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

    def _lire_historique_courant(self, properties):
        from .sync_google_sheets import canonical_headers, lire_feuille_complete

        values = lire_feuille_complete(self.session, self.base, HISTORY, properties, raw_dates=True)
        if not values:
            raise ErreurSynchronisation('Historique sans en-têtes')
        headers = canonical_headers(values[0])
        rows = [dict(zip(headers, row)) for row in values[1:]]
        independent = lire_cles_independantes(self.session, self.base, HISTORY, properties, headers)
        verifier_avant(headers, rows, {}, [], full_source=False, observed_keys=independent)
        return [{name: depuis_nombre(name, value) for name, value in row.items()} for row in rows]

    def synchroniser_tables(self,source,*,scope,full_source=False,allow_structure=False,
                            kpi_source=None,reconcilier=False):
        start=time.monotonic();before=(self.session.lectures,self.session.ecritures)
        with verrou_local(self.spreadsheet):
            tables=self.metadata();counts={}
            reconciliation = {} if reconcilier else None
            # Vérifier l'historique avant toute publication dans les autres onglets.
            for tab,incoming in sorted(source.items(),key=lambda item:item[0]!=HISTORY):
                if tab not in tables:raise ErreurSynchronisation('Onglet absent : '+tab)
                if not incoming and not full_source and not (reconcilier and tab == 'Courses & Prévisions'):
                    counts[tab]={'lignes_ajoutees':0,'cellules_actualisees':0,'lignes_source':0}
                    continue
                if reconcilier and tab == 'Courses & Prévisions' and 'historique' not in reconciliation:
                    reconciliation['historique'] = self._lire_historique_courant(tables[HISTORY])
                counts[tab]=self._synchroniser_onglet(tab,incoming,tables[tab],
                    full_source=full_source,allow_structure=allow_structure,reconciliation=reconciliation)
            if kpi_source is not None:
                counts.update(self._synchroniser_kpi(tables,kpi_source,
                    courses_verifiees=reconciliation.get('courses') if reconcilier else None))
        print('SHEETS_MOTEUR_UNIQUE '+json.dumps({'perimetre':scope,
            'lectures_api':self.session.lectures-before[0],'ecritures_api':self.session.ecritures-before[1],
            'duree_secondes':round(time.monotonic()-start,3)},ensure_ascii=False),flush=True)
        return counts

    def synchroniser_cycle(self,include_kpi=True):
        from .sync_google_sheets import SHEET_TABS
        source=self.source()
        return self.synchroniser_tables({tab:source[tab] for tab in SHEET_TABS},scope='CYCLE_PMU',
            full_source=True,allow_structure=True,kpi_source=source if include_kpi else None,reconcilier=True)

    def synchroniser_cheval(self,horse,*,include_kpi=True,include_courses=True):
        source=self.source();ident=str(horse['geny']['id'])
        history={k:v for k,v in source[HISTORY].items() if str(v.get('identifiant_cheval'))==ident}
        if not history and horse.get('nombre_performances')!=0:
            raise ErreurSynchronisation('Aucune performance a synchroniser pour '+ident)
        tables = {HISTORY: history}
        if include_courses:
            tables['Courses & Prévisions'] = {}
        return self.synchroniser_tables(tables,scope='CHEVAL' if include_courses else 'RATTRAPAGE',
            kpi_source=source if include_kpi else None,reconcilier=include_courses)

    def inventaire_rattrapage(self):
        """Lecture complète seule : inventaire et preuve des clés déjà publiées."""
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

    def synchroniser_correspondances(self, *, include_kpi=False):
        """Actualiser les diagnostics courants sur les lignes déjà publiées."""
        return self.synchroniser_tables({'Courses & Prévisions': {}}, scope='CORRESPONDANCES_GENY',
            reconcilier=True, kpi_source=self.source() if include_kpi else None)

    def synchroniser_kpi(self):
        with verrou_local(self.spreadsheet):return self._synchroniser_kpi(self.metadata(),self.source(),relire_courses=True)
