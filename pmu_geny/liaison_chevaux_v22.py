"""Lien stable entre partant PMU (course, numéro) et cheval Geny.

L'identifiant Geny provient d'un manifeste de course vérifié, jamais du numéro
PMU. Repli possible sur le nom normalisé strict et unique dans les historiques
COMPLETS; aucune correspondance approximative.
"""
from __future__ import annotations
import unicodedata
from pathlib import Path
from .ml_v19 import load

def nom_normalise(value):
    value=unicodedata.normalize('NFKD',str(value or '').casefold())
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
        if meta.get('statut')!='COMPLET':continue
        doc=load(cache/'historiques'/str(ident)/'historique_geny.json',{}) or {}
        if doc.get('statut')!='COMPLET' or not isinstance(doc.get('performances'),list):continue
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
                if doc.get('statut')=='COMPLET' and isinstance(doc.get('performances'),list):
                    by_number[num]=(ident,doc,'ID_GENY_MANIFESTE_VERIFIE')
    matches={}
    for numero,name in noms.items():
        if numero in by_number:
            ident,doc,method=by_number[num]
            matches[numero]={'cheval_id':ident,'historique':doc,'methode':method}
            continue
        candidates=known.get(name,[])
        if len(candidates)==1:
            ident,doc=candidates[0]
            matches[numero]={'cheval_id':ident,'historique':doc,'methode':'NOM_EXACT_UNIQUE'}
        elif len(candidates)>1:
            matches[numero]={'cheval_id':'','historique':{},'methode':'NOM_AMBIGU'}
        else:
            matches[numero]={'cheval_id':'','historique':{},'methode':'NON_ASSOCIE'}
    return matches
