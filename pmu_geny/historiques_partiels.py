"""Conserver les lignes Geny vérifiables sans annoncer une carrière complète."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from dashboard.trot_analytics.dates import PARIS

from .controle_historique import PARTIELS, classifier
from .liaison_chevaux_v22 import nom_geny_concordant


def conserver(cache, horse, report):
    from . import historiques_incrementaux as inc
    if report.get('statut') not in PARTIELS or not report.get('identite_verifiee'):
        return False
    geny=report.get('geny') or {};ident=str(geny.get('id',''))
    if (not re.fullmatch(r'\d{4,15}',ident) or horse.get('id') and horse['id']!=ident
            or not nom_geny_concordant(horse.get('nom'), geny)):
        return False
    doc=inc.lire(Path(report['dossier'])/'historique_geny.json')
    parsed=urlparse(str(doc.get('source_url','')))
    match=re.match(r'/cheval/(\d+)(?:\D|$)',parsed.path)
    stamp=inc.instant(doc.get('extrait_utc'));now=datetime.now(timezone.utc)
    if (parsed.scheme!='https' or parsed.hostname not in ('geny.com','www.geny.com')
            or not match or match[1]!=ident or not stamp or stamp>now):return False
    rows=[]
    for row in doc.get('performances',[]):
        if not isinstance(row,dict):continue
        try:day=date.fromisoformat(row.get('date',''))
        except (ValueError,TypeError):continue
        if day>stamp.astimezone(PARIS).date():continue
        if all(str(row.get(k) or '').strip() for k in ('hippodrome','discipline','distance_m','classement')):
            rows.append(row)
    # Même contrôle de doublons et de champs que pour une carrière complète.
    if not rows or classifier({'nombre_annonce_geny':len(rows),'nombre_extrait':len(rows),
                               'performances':rows})[0]!='COMPLET':return False
    target=Path(cache)/'historiques_partiels'/ident/'historique_geny.json'
    previous=inc.lire(target)
    if previous and len(previous.get('performances',[]))>len(rows):return False
    if previous:
        digest=hashlib.sha256(json.dumps(previous,sort_keys=True).encode()).hexdigest()
        inc.ecrire(Path(cache)/'historiques_versions'/ident/('partiel-'+digest+'.json'),previous)
    name = geny.get('nom') or horse['nom']
    partial={**doc,'nom':name,'identifiant_cheval':ident,'statut':'PARTIEL_HISTORIQUE',
             'complet':False,'performances':rows,'nombre_extrait':len(rows),
             'motifs_incompletude':report.get('motifs',[]),'identite_verifiee':True}
    from .ferrures_geny import couverture
    couverture(partial)
    inc.ecrire(target,partial)
    horse.update(id=ident,geny=geny,sync='A_FAIRE',collecte='PARTIEL_HISTORIQUE',
                 nombre_performances_partielles=len(rows),
                 prochain_essai_utc=(now+timedelta(hours=6)).isoformat())
    journal=inc.lire(Path(cache)/'etat_persistant.json',{'version':1,'chevaux':{}})
    existing=journal.setdefault('chevaux',{}).get(ident,{})
    if existing.get('statut')!='COMPLET':
        journal['chevaux'][ident]={**existing,'id':ident,'nom':name,'statut':'PARTIEL',
            'maj_utc':stamp.isoformat(),'nombre_extrait':len(rows),'origine':'GENY_PARTIEL_VERIFIE'}
        inc.ecrire(Path(cache)/'etat_persistant.json',journal)
    return True
