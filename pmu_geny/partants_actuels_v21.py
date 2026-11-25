"""Metadonnees des partants: lecture prudente de champs explicites PMU, sans deviner."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import re
from .auto_v18 import _list, _num, save
from .departs_trot import depart_partant_pmu
from .echeances_production import instant

FIELDS = {
    "driver_jockey": ("driver", "jockey", "nomDriver", "nomJockey", "driverJockey"),
    "entraineur": ("entraineur", "trainer", "nomEntraineur"),
    "proprietaire": ("proprietaire", "owner", "nomProprietaire"),
    "ferrure": ("deferre", "ferrure", "codeFerrure", "typeFerrure", "ferrureCheval"),
    "musique_pmu": ("musique", "musiqueCheval", "derniereMusique"),
    "sexe": ("sexe", "sexeCheval", "sexeParticipant"),
    "age_ans": ("age", "ageCheval", "ageParticipant"),
    "gains_euros": ("gainsCarriere", "gainsParticipant", "gains", "gainCarriere",
                     "montantGains", "gainTotal", "gainsCheval"),
}


def profil_pmu_exclusif(actual):
    """Lecture sans mutation : un complément tiers ancien n'est plus un critère."""
    actual=dict(actual)
    provenance=dict(actual.get('provenance_champs') or {})
    for field,proof in list(provenance.items()):
        if proof.get('source') in ('equidia','zeturf'):
            actual.pop(field,None)
            provenance.pop(field)
    actual['provenance_champs']=provenance
    actual['divergences_sources']=[]
    return qualifier_ferrure(actual)


def qualifier_ferrure(profile):
    profile=dict(profile)
    raw=profile.get('ferrure') or profile.get('ferrure_brute','')
    code=ferrure_normalisee(raw)
    proof=(profile.get('provenance_champs') or {}).get('ferrure',{})
    if code:
        profile['ferrure']=code
        profile['ferrure_qualification']='CONVENTION_PMU' if proof.get('convention') else 'CODE_RECONNU'
    elif raw:
        profile['ferrure_brute']=raw
        profile['ferrure']=''
        profile['ferrure_qualification']='CODE_INCONNU'
    else:
        profile['ferrure_qualification']='NON_RECUPEREE'
    return profile

def _label(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for k in ("nomComplet", "nom", "libelle", "libelleCourt", "nomPersonne", "code"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""

def age_valide(value):
    if isinstance(value,bool):return None
    raw=str(value or '').strip()
    if re.fullmatch(r'\d{1,2}',raw):
        age=int(raw)
        return age if 2<=age<=25 else None
    return None

def gains_valides(value):
    # PMU gainsParticipant.gainsCarriere est publie en centimes : 88817500
    # correspond a 888175 EUR (croise avec la page Zone-Turf du Quinté).
    if isinstance(value,dict) and 'gainsCarriere' in value:
        raw=value['gainsCarriere']
        if isinstance(raw,bool) or not isinstance(raw,(int,float)) or raw<0:return None
        return round(raw/100,2) if raw/100<100_000_000 else None
    if isinstance(value,dict):
        for key in ('montant','valeur','gains','total','montantGains'):
            if key in value:return gains_valides(value[key])
        return None
    if isinstance(value,bool) or value is None:return None
    text=str(value).replace('\u00a0','').replace(' ','').replace('€','').strip()
    if not re.fullmatch(r'\d+(?:[.,]\d{1,2})?',text):return None
    amount=float(text.replace(',','.'))
    return round(amount,2) if 0<=amount<100_000_000 else None

def sexe_normalise(value):
    if isinstance(value,dict):
        value=value.get('libelle') or value.get('code') or value.get('nom') or ''
    key=str(value or '').strip().upper()
    return {
        'M':'Mâle','MALE':'Mâle','MÂLE':'Mâle','MALES':'Mâle','MÂLES':'Mâle','ENTIER':'Mâle','ENTIERS':'Mâle',
        'F':'Femelle','FEMELLE':'Femelle','FEMELLES':'Femelle','JUMENT':'Femelle','POULICHE':'Femelle',
        'H':'Hongre','HONGRE':'Hongre','HONGRES':'Hongre'
    }.get(key,'')

def ferrure_normalisee(value):
    if value is None:return ''
    key=str(value).strip().upper()
    # Correspondances confirmées sur le flux public PMU du 12 novembre :
    # D4 = 4 pieds déferrés, P4 = 4 pieds protégés/plaqués.
    return {
        'DEFERRE_ANTERIEURS_POSTERIEURS':'D4',
        'DEFERRE_ANTERIEURS':'DA',
        'DEFERRE_POSTERIEURS':'DP',
        'PROTEGE_ANTERIEURS_POSTERIEURS':'P4',
        'PROTEGE_ANTERIEURS':'PA',
        'PROTEGE_POSTERIEURS':'PP',
        'PROTEGE_ANTERIEURS_DEFERRRE_POSTERIEURS':'DP/PA',
        'PROTEGE_ANTERIEURS_DEFERRE_POSTERIEURS':'DP/PA',
        'DEFERRE_ANTERIEURS_PROTEGE_POSTERIEURS':'DA/PP',
        'D4':'D4','DA':'DA','DP':'DP','P4':'P4','PA':'PA','PP':'PP',
        'DP/PA':'DP/PA','DA/PP':'DA/PP',
        'FERRE':'F','FERRÉ':'F','F':'F'
    }.get(key,'')

def ferrure_historique_explicite(value):
    """Un code ambigu exige un champ ou libellé explicite de ferrure.

    Dans une carrière, PP désigne aussi la petite piste ; « Da Costa » est
    un nom de driver. Le texte de la ligne ne donne pas leur contexte.
    """
    text=str(value or '').strip()
    codes=r'(?:DP/PA|DA/PP|D4|P4|DP|DA|PA|PP|F)'
    if re.fullmatch(codes,text,re.I):return text.upper()
    match=re.search(r'\bferrure\s*[:=]\s*('+codes+r')(?![A-Za-z0-9])',text,re.I)
    if match:return match.group(1).upper()
    match=re.search(r'(?<![A-Za-z0-9])(?:DP/PA|DA/PP|D4|P4)(?![A-Za-z0-9])',text,re.I)
    return match.group(0).upper() if match else ''


def faux_code_ferrure_historique(value,code):
    """Erreurs textuelles démontrables de l'ancien bridge, pas une valeur vide générique."""
    text=str(value or '')
    return bool(code=='PP' and re.search(r'\|\s*[\d\s]+\|\s*PP\s*\|\s*[GD]\s*\|',text)
                or code=='DA' and re.search(r'\bDa Costa\b',text,re.I))

def statut_participation(item):
    flag = item.get('nonPartant')
    if isinstance(flag, str):
        flag = {'true': True, 'false': False}.get(flag.lower())
    status = str(item.get('statut', '')).upper()
    if flag is True or status in ('NP', 'NON_PARTANT'):
        return 'NON_PARTANT'
    if flag is False or status == 'PARTANT':
        return 'PARTANT'
    return 'NP_NON_VERIFIE'


def extraire_partants(raw, *, course=None):
    resultat = {}
    for item in _list(raw, "participants", "partants"):
        if not isinstance(item,dict):
            continue
        n=_num(item, "numPmu", "num", "numero", "numeroPmu")
        if n is None or n in resultat:
            continue
        fields={}
        for label,aliases in FIELDS.items():
            for alias in aliases:
                val=_label(item.get(alias))
                if val:
                    fields[label]=val
                    break
        for alias in FIELDS["age_ans"]:
            age=age_valide(item.get(alias))
            if age is not None:fields['age_ans']=age;break
        for alias in FIELDS["gains_euros"]:
            gains=gains_valides(item.get(alias))
            if gains is not None:fields['gains_euros']=gains;break
        for alias in FIELDS["sexe"]:
            sexe=sexe_normalise(item.get(alias))
            if sexe:fields['sexe']=sexe;break
        if fields.get('sexe'):
            fields['sexe']=sexe_normalise(fields['sexe']) or fields['sexe']
        if fields.get('ferrure'):
            fields['ferrure']=ferrure_normalisee(fields['ferrure']) or fields['ferrure']
        elif (item.get('allure')=='TROT' and item.get('idCheval')
              and item.get('statut') in ('PARTANT','NON_PARTANT','NP')
              and all(item.get(alias) is None for alias in FIELDS['ferrure'])):
            # Le flux officiel PMU omet la déclaration de déferrage pour les
            # chevaux ferrés. Convention recoupée avec les mêmes partants Geny
            # explicitement FF / « Ferré des 4 ». Ne pas l'étendre aux objets
            # incomplets, aux valeurs inconnues ou aux participants de galop.
            fields['ferrure']='F'
            fields['provenance_champs']={'ferrure':{'source':'PMU_API_PARTICIPANTS',
                'champ':'deferre','valeur_brute':None,'convention':'TROT_SANS_DECLARATION_DEFERRAGE'}}
        for nom_key in ("nomCheval","nom","nomParticipant"):
            nom=_label(item.get(nom_key))
            if nom:
                fields["nom"]=nom
                break
        fields["statut_np"] = statut_participation(item)
        if course and fields['statut_np'] == 'PARTANT':
            depart = depart_partant_pmu(course, item)
            if depart:
                fields['depart_trot'] = depart
        resultat[n]=qualifier_ferrure(fields)
    return resultat

def enregistrer(cache:Path, course:dict, raw, *, observe=None):
    captured = observe if observe is not None else datetime.now(timezone.utc)
    depart = instant(course.get('depart'))
    avant_depart = depart is not None and captured < depart
    resultat=extraire_partants(raw, course=course if avant_depart else None)
    if not resultat:
        return "PARTANTS_NON_VERIFIES"
    samples=_list(raw,"participants","partants")
    observed=sorted(str(k) for k in samples[0].keys()) if samples and isinstance(samples[0],dict) else []
    doc={"date":course["date"], "course":course["code"],
         "champs_participant_pmu_observes":observed,
         # Champs publics diagnostiques des trois premiers partants, sans
         # déduction de la structure PMU.
         "diagnostic_profils_pmu":[
             {"nom":str(item.get("nom",""))[:80],
              "deferre":item.get("deferre"),
              "gainsParticipant":item.get("gainsParticipant")}
             for item in samples[:3] if isinstance(item,dict)],
         "source":"PMU_API_PARTICIPANTS",
         "capture_utc":captured.isoformat(),
         "chevaux":{str(n):values for n,values in resultat.items()}}
    r,c=course['code'].split('C',1)
    source_url='https://online.turfinfo.api.pmu.fr/rest/client/1/programme/'+datetime.fromisoformat(course['date']).strftime('%d%m%Y')+'/'+r+'/C'+c+'/participants'
    path = Path(cache)/"partants_actuels"/f'{course["date"]}_{course["code"]}.json'
    if not avant_depart:
        from .ml_v19 import load
        previous = load(path, {}) or {}
        for numero, fields in doc['chevaux'].items():
            old = previous.get('chevaux', {}).get(numero, {})
            if old.get('nom') == fields.get('nom') and old.get('depart_trot'):
                fields['depart_trot'] = old['depart_trot']
    for fields in resultat.values():
        if avant_depart and fields.get('depart_trot'):
            fields['depart_trot'].update(source='PMU_API_PARTICIPANTS', url=source_url,
                                         capture_utc=doc['capture_utc'])
        if fields.get('ferrure'):
            provenance=fields.setdefault('provenance_champs',{}).setdefault('ferrure',{'source':'PMU_API_PARTICIPANTS'})
            provenance.update(url=source_url,capture_utc=doc['capture_utc'])
    save(path,doc)
    from .sources_experts_v23 import completer_partants
    completer_partants(cache,course)
    return "PARTANTS_ACTUELS_ENREGISTRES"

