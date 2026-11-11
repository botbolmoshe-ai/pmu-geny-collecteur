"""Lien stable entre partant PMU (course, numéro) et cheval Geny.

Le nom exact normalise est la cle logique d'identite, le numero de course sert
uniquement au rattachement du partant actuel. L'identifiant Geny stable peut
confirmer la correspondance et departager des homonymes.
"""
from __future__ import annotations
import unicodedata
from pathlib import Path
from .ml_v19 import load

def nom_normalise(value):
    value=unicodedata.normalize('NFKD',str(value or '').upper())
    return ''.join(ch for ch in value if ch.isalnum() and not unicodedata.combining(ch))

def etablir(cache, course, participants=None):
    cache=Path(cache)
    date,code=course['date'],course['code']
    noms={}
    for h in participants or []:
        if not isinstance(h,dict):continue
        numero=h.get('numero',h.get('numPmu'))
        name=h.get('nom',h.get('nomCheval',''))
        if numero is not None:noms[str(numero)]=nom_normalise(name)
    journal=(load(cache/'etat_persistant.json',{}) or {}).get('chevaux',{})
    known={}
    for ident,meta in journal.items():
        if meta.get('statut') not in ('COMPLET','PARTIEL'):continue
        doc=load(cache/'historiques'/str(ident)/'historique_geny.json',{}) or {}
        if doc.get('statut') not in ('COMPLET','PARTIEL') or not isinstance(doc.get('performances'),list):continue
        key=nom_normalise(meta.get('nom',''))
        if key:known.setdefault(key,[]).append((str(ident),doc))
    by_number={}
    correspondences=load(cache/'orchestration'/'correspondances_geny.json',{}) or {}
    cid=correspondences.get(f'{date}_{code}')
    if cid:
        manifest=load(cache/'manifestes'/f'{cid}.json',{}) or {}
        blocks=manifest.get('courses',[])
        if len(blocks)==1 and blocks[0].get('course_id')==cid:
            for h in blocks[0].get('partants',[]):
                num=str(h.get('numero',''))
                name=nom_normalise(h.get('nom',''))
                if not num or not name or noms.get(num)!=name:continue
                ident=str(h.get('id',''))
                doc=load(cache/'historiques'/ident/'historique_geny.json',{}) or {}
                if doc.get('statut') in ('COMPLET','PARTIEL') and isinstance(doc.get('performances'),list):
                    by_number[num]=(ident,doc,'ID_GENY_MANIFESTE_VERIFIE')
    matches={}
    for numero,name in noms.items():
        candidates=known.get(name,[])
        if len(candidates)==1:
            ident,doc=candidates[0]
            method='NOM_EXACT_UNIQUE'
            if numero in by_number and by_number[numero][0]==ident:
                method='NOM_EXACT_ET_ID_GENY_CONFIRME'
            matches[numero]={'cheval_id':ident,'historique':doc,'methode':method}
        elif len(candidates)>1:
            if numero in by_number and any(x[0]==by_number[numero][0] for x in candidates):
                ident,doc,_=by_number[numero]
                matches[numero]={'cheval_id':ident,'historique':doc,'methode':'NOM_AMBIGU_ID_CONFIRME'}
            else:
                matches[numero]={'cheval_id':'','historique':{},'methode':'NOM_AMBIGU'}
        else:
            matches[numero]={'cheval_id':'','historique':{},'methode':'NON_ASSOCIE'}
    return matches
