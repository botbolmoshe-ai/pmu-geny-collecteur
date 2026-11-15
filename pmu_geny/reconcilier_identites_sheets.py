"""Réparer les doublons inter-sources prouvés sous le verrou Sheets commun."""
import hashlib
import json
from datetime import datetime, timezone

from . import historiques_incrementaux as inc
from .controle_sync_sheets import HISTORY,KEY,lire_cles_independantes,verifier_avant,verifier_apres
from .identites_chevaux import canoniser_ligne
from .liaison_chevaux_v22 import nom_normalise
from .moteur_sheets import verrou_local
from .sync_google_sheets import canonical_headers,lire_feuille_complete


def contexte(row):
    fields=('date_course_historique','hippodrome','discipline','distance_m','classement')
    if any(row.get(k) is None or str(row[k])=='' for k in fields):return None
    return tuple(nom_normalise(row[k]) for k in fields)


def reparer(engine,*,checkpoint=inc.checkpoint_distant):
    """Aucune fusion de nom seul ; sauvegarde distante avant le batch atomique."""
    with verrou_local(engine.spreadsheet):
        properties=engine.metadata()[HISTORY]
        values=lire_feuille_complete(engine.session,engine.base,HISTORY,properties)
        headers=canonical_headers(values[0])
        rows=[dict(zip(headers,row)) for row in values[1:]]
        independent=lire_cles_independantes(engine.session,engine.base,HISTORY,properties,headers)
        control=verifier_avant(headers,rows,{},[],observed_keys=independent)
        canonical=engine.source()[HISTORY]
        removals=[];updates=[];proofs=[]
        for index,old in enumerate(rows):
            normalized=canoniser_ligne(old)
            if normalized.get('identifiant_cheval')==old.get('identifiant_cheval'):continue
            ident=normalized['identifiant_cheval']
            if not inc.capture_valide(engine.cache,ident):raise ValueError('CAPTURE_CANONIQUE_NON_VALIDEE')
            context=contexte(normalized)
            source=[r for r in canonical.values() if str(r.get('identifiant_cheval'))==ident and contexte(r)==context]
            targets=[(i,r) for i,r in enumerate(rows) if str(r.get('identifiant_cheval'))==ident and contexte(r)==context]
            if context is None or len(source)!=1 or len(targets)!=1:
                raise ValueError('DOUBLON_INTERSOURCE_NON_PROUVE: '+str(old.get(KEY)))
            target_index,target=targets[0]
            if nom_normalise(old.get('cheval'))!=nom_normalise(target.get('cheval')):
                raise ValueError('NOMS_INTERSOURCES_NON_CONCORDANTS')
            if old.get('ferrure') and target.get('ferrure') and old['ferrure']!=target['ferrure']:
                raise ValueError('FERRURES_INTERSOURCES_NON_CONCORDANTES')
            for field in ('chrono','ferrure'):
                a=str(target.get(field) or '').replace('"',"''")
                b=str(source[0].get(field) or '').replace('"',"''")
                if a!=b:raise ValueError('LIGNE_CANONIQUE_DIFFERENTE_DE_LA_CAPTURE')
            # Les champs historiques complémentaires ne sont pas perdus.
            for field in ('driver_jockey','entraineur','rncn','nombre_partants','gains_course_eur'):
                value=old.get(field)
                if value is not None and str(value)!='' and not target.get(field) and field in headers:
                    updates.append((target_index,headers.index(field),value))
                    target[field]=value
            removals.append(index)
            proofs.append({'ligne_supprimee':index+2,'ancienne':old,
                           'ligne_conservee':target_index+2,'canonique':dict(target),
                           'performance_source':source[0]})
        if not removals:return {'lignes_supprimees':0,'statut':'SANS_MODIFICATION'}
        digest=hashlib.sha256(json.dumps(proofs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        backup=engine.cache/'historiques_versions'/'reconciliations_identites'/(digest+'.json')
        audit={'utc':datetime.now(timezone.utc).isoformat(),'spreadsheet':engine.spreadsheet,
               'preuves':proofs,'lignes_avant':len(rows),'lignes_supprimees':len(removals),
               'en_tetes_originales':values[0],
               'lignes_originales':[{'numero_ligne':i+2,'valeurs':values[i+1]}
                   for i in sorted(set(removals)|{p['ligne_conservee']-2 for p in proofs})],
               'statut':'SAUVEGARDE_AVANT_ECRITURE'}
        inc.ecrire(backup,audit)
        checkpoint(engine.cache)  # Un refus de sauvegarde interdit toute écriture Sheets.
        for index in removals:control['expected_keys'].subtract([str(rows[index][KEY])])
        control['expected_keys']+=type(control['expected_keys'])()
        control['report']['lignes_attendues']-=len(removals)
        control['report']['suppressions_inter_sources_prouvees']=len(removals)
        requests=[]
        for row,column,value in updates:
            requests.append({'updateCells':{'start':{'sheetId':properties['sheetId'],
                'rowIndex':row+1,'columnIndex':column},
                'rows':[{'values':[{'userEnteredValue':{'stringValue':str(value)}}]}],
                'fields':'userEnteredValue'}})
        requests.extend({'deleteDimension':{'range':{'sheetId':properties['sheetId'],
            'dimension':'ROWS','startIndex':index+1,'endIndex':index+2}}}
            for index in sorted(removals,reverse=True))
        engine.check(engine.session.post(engine.base+':batchUpdate',json={'requests':requests},timeout=60))
        fresh=engine.metadata()[HISTORY]
        after=lire_feuille_complete(engine.session,engine.base,HISTORY,fresh)
        if canonical_headers(after[0])!=headers:raise ValueError('ENTETES_MODIFIEES_PENDANT_RECONCILIATION')
        result=verifier_apres(control,[dict(zip(headers,row)) for row in after[1:]])
        audit.update(statut='VALIDE',controle=result)
        inc.ecrire(backup,audit);checkpoint(engine.cache)
        print('RECONCILIATION_IDENTITES '+json.dumps({'lignes_supprimees':len(removals),
              'champs_complementaires_conserves':len(updates),'statut':'VALIDE','sauvegarde':str(backup)}),flush=True)
        return {'lignes_supprimees':len(removals),'statut':'VALIDE'}
