"""Entraîner et utiliser un candidat expérimental sans seuil de promotion."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

from .ml_v19 import ACTIVE_FEATURES, ACTIVE_MODEL_SCHEMA, dataset, load, save

STATUT='ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE'
POINTEUR=Path('ml/modele_experimental_actif.json')


def modele_actif(name):
    from .experience_ml import modeles

    return modeles()[name].set_params(simpleimputer__add_indicator=True)


def entrainer(cache,now=None):
    cache=Path(cache);now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('Fuseau obligatoire')
    records,courses=dataset(cache,now)
    experience=load(cache/'ml/cycle_experimental.json',{}) or {}
    name=experience.get('modele')
    if name not in ('gradient_boosting','regression_logistique'):name='regression_logistique'
    digest=hashlib.sha256(json.dumps({'version':2,'schema':ACTIVE_MODEL_SCHEMA,'features':ACTIVE_FEATURES,
        'modele':name,'observations':records},sort_keys=True).encode()).hexdigest()
    old=load(cache/POINTEUR,{}) or {}
    if (old.get('empreinte_entrainement')==digest and old.get('statut')==STATUT
            and modele_disponible(cache) is not None):
        result={**old,'verification_utc':now.isoformat(),'execution':'DONNEES_INCHANGEES'}
        save(cache/POINTEUR,result)
        return result
    result={'statut':'ML_EXPERIMENTAL_ATTENTE_DONNEES','verification_utc':now.isoformat(),
        'empreinte_entrainement':digest,'courses':courses,'lignes':len(records),
        'modele':name,'promotion_production':False,'schema':ACTIVE_MODEL_SCHEMA,
        'variables_modele':list(ACTIVE_FEATURES),
        'nature':'CANDIDAT_EXPERIMENTAL_NON_CALIBRE',
        'evaluation':'A_MESURER_SUR_LES_PREVISIONS_FUTURES_ENREGISTREES'}
    if not records or len({r['y'] for r in records})<2:
        result['motif']='Observations admissibles des deux classes nécessaires.'
        save(cache/POINTEUR,result);return result
    import joblib
    import numpy as np
    from .experience_ml import matrix
    x=matrix(records, ACTIVE_FEATURES)
    if not np.isfinite(x).any():
        result['motif']='Aucune variable numérique exploitable.'
        save(cache/POINTEUR,result);return result
    result['couverture_variables'] = dict(zip(ACTIVE_FEATURES, np.isfinite(x).sum(axis=0).tolist()))
    model=modele_actif(name)
    model.fit(x,[r['y'] for r in records])
    output=cache/'ml/modeles_experimentaux'/digest
    output.mkdir(parents=True,exist_ok=True)
    path=output/'modele.joblib';temporary=path.with_suffix('.tmp')
    last=max(datetime.fromisoformat(r['verifie_utc']) for r in records).isoformat()
    packed={'model':model,'features':ACTIVE_FEATURES,'schema':ACTIVE_MODEL_SCHEMA,'statut':STATUT,
        'modele':name,'entrainement_utc':now.isoformat(),'dernier_label_entrainement_utc':last,
        'courses':courses,'lignes':len(records),'promotion_production':False}
    joblib.dump(packed,temporary);temporary.replace(path)
    result.update(statut=STATUT,entrainement_utc=now.isoformat(),
        dernier_label_entrainement_utc=last,fichier_modele=str(path.relative_to(cache)),
        sha256_modele=hashlib.sha256(path.read_bytes()).hexdigest(),execution='ENTRAINE')
    save(output/'rapport.json',result);save(cache/POINTEUR,result)
    return result


def modele_disponible(cache):
    cache=Path(cache);meta=load(cache/POINTEUR,{}) or {}
    if meta.get('statut')!=STATUT:return None
    path=cache/str(meta.get('fichier_modele',''))
    root=(cache/'ml/modeles_experimentaux').resolve()
    if root not in path.resolve().parents or not path.is_file():return None
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta.get('sha256_modele'):return None
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',default='cache_pmu')
    args=p.parse_args();print(json.dumps(entrainer(args.cache),ensure_ascii=False))


if __name__=='__main__':main()
