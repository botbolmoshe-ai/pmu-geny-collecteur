"""Filtre métier trot France P1/P2, sans déduction hasardeuse.

Seuils P2 configurables dans ce module, et non des règles PMU officielles.
La source de chaque élément doit être issue du programme PMU pré-départ.
"""
from __future__ import annotations
import re
import unicodedata

# Priorité P2 : hippodromes français où les réunions de trot sont suivies.
# Il s'agit d'une liste éditoriale de suivi, pas d'une classification officielle.
HIPPODROMES_P2 = frozenset({
    'enghien', 'caen', 'cabourg', 'laval', 'le mans', 'nantes',
    'cagnes sur mer', 'marseille borely', 'lyon parilly', 'lyon la soie',
    'toulouse', 'agen', 'beaumont de lomagne', 'mauquenchy', 'reims',
    'amiens', 'chartres', 'graignes', 'vire', 'rouen mauquenchy',
    'angers', 'bordeaux le bouscat', 'meslay du maine', 'pontchateau',
    'la capelle', 'le croise laroche', 'saint malo', 'vichy',
})
ALLOCATION_P1_EUR = 40000
ALLOCATION_MIN_P2_EUR = 12000
PARTANTS_MIN_P2 = 8

def normaliser(value):
    value = unicodedata.normalize('NFD',str(value or '').casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+',' ',value).strip()

def discipline_course(course, reunion):
    """Priorité au champ propre à la course ; réunion utilisable si unique."""
    values=[]
    for field in ('specialite','specialiteCourse','discipline','typeCourse'):
        v=course.get(field)
        if isinstance(v,dict):
            values.extend(v.get(k) for k in ('code','libelle','nom','value'))
        elif isinstance(v,(str,int)): values.append(v)
    if not any(v is not None and str(v).strip() for v in values):
        v=reunion.get('specialites',[])
        if isinstance(v,list) and len(v)==1: values.append(v[0])
        elif isinstance(v,str):values.append(v)
    codes=[]
    for v in values:
        label=normaliser(v)
        if label in {'trot attele','attele','trot a l attele','trot attele'} or 'trot attele' in label:
            codes.append('TROT_ATTELE')
        elif label in {'trot monte','monte'} or 'trot monte' in label:
            codes.append('TROT_MONTE')
        elif label=='trot': codes.append('TROT_SOUS_TYPE_INCONNU')
        elif label: codes.append('AUTRE')
    codes=set(codes)
    if len(codes)==1:return codes.pop()
    return 'DISCIPLINE_NON_VERIFIEE' if not codes else 'DISCIPLINE_AMBIGUE'

def allocation_eur(course):
    for k in ('montantPrix','allocation','allocationTotale','dotation','montantAllocation'):
        v=course.get(k)
        if isinstance(v,dict):v=v.get('montant') or v.get('valeur')
        if isinstance(v,(int,float)) and v>=0:return int(v)
        if isinstance(v,str):
            x=re.sub(r'[^0-9]','',v)
            if x:return int(x)
    return None

def groupe_course(course):
    for k in ('categorie','categorieCourse','typeEpreuve','groupe','niveau','libelle','libelleCourt'):
        v=course.get(k)
        if isinstance(v,dict): v=' '.join(str(z) for z in v.values() if z is not None)
        s=normaliser(v)
        if re.search(r'\bgroupe\s*(?:1|2|3|i|ii|iii)\b',s) or re.search(r'\bg[123]\b',s):return True
    return False

def niveau(course,reunion,hippodrome,nombre_partants):
    """Retourne (niveau, motif, meta). None => exclusion traçable."""
    discipline=discipline_course(course,reunion)
    allocation=allocation_eur(course)
    hp=normaliser(hippodrome)
    groupe=groupe_course(course)
    meta={'discipline':discipline,'allocation_eur':allocation,'groupe':groupe,
          'hippodrome':hippodrome,'nombre_partants':nombre_partants}
    if discipline not in ('TROT_ATTELE','TROT_MONTE','TROT_SOUS_TYPE_INCONNU'):
        reason='DISCIPLINE_INCONNUE' if discipline=='DISCIPLINE_NON_VERIFIEE' else 'HORS_TROT'
        return None,reason,meta
    if hp=='vincennes' or groupe or allocation is not None and allocation>=ALLOCATION_P1_EUR:
        return 'P1','VINCENNES' if hp=='vincennes' else 'GROUPE' if groupe else 'ALLOCATION_ELEVEE',meta
    if hp not in HIPPODROMES_P2:
        return None,'HIPPODROME_HORS_SELECTION',meta
    if nombre_partants < PARTANTS_MIN_P2:return None,'EFFECTIF_INSUFFISANT_P2',meta
    if allocation is not None and allocation<ALLOCATION_MIN_P2_EUR:
        return None,'ALLOCATION_INFERIEURE_SEUIL_P2',meta
    return 'P2','HIPPODROME_MAJEUR_P2' if allocation is not None else 'HIPPODROME_MAJEUR_ALLOCATION_INCONNUE',meta
