"""Apprentissage sur les données admissibles, sans seuil de promotion ni déploiement."""
from datetime import datetime
from pathlib import Path
from .ml_v19 import dataset,load,save


def executer(cache,now,empreinte):
    cache=Path(cache);path=cache/'ml/cycle_experimental.json'
    previous=load(path,{}) or {}
    if previous.get('empreinte_donnees')==empreinte and previous.get('version_cycle')==1:
        return {**previous,'execution':'DONNEES_INCHANGEES'}
    records,courses=dataset(cache,now)
    days=sorted({r['depart'][:10] for r in records})
    result={'version_cycle':1,'empreinte_donnees':empreinte,'execute_utc':now.isoformat(),
            'statut':'ATTENTE_DONNEES_TEMPORELLES','courses_admissibles':courses,
            'lignes_admissibles':len(records),'promotion_production':False}
    pair=None
    # Choisir selon la disponibilité temporelle, jamais selon les scores de test.
    for test in reversed(days):
        for validation in reversed([d for d in days if d<test]):
            train=[r for r in records if r['depart'][:10]<validation]
            valid=[r for r in records if r['depart'][:10]==validation]
            held=[r for r in records if r['depart'][:10]==test]
            if not train or not valid or not held or len({r['y'] for r in train})<2:continue
            if (max(datetime.fromisoformat(r['verifie_utc']) for r in train)
                    >=min(datetime.fromisoformat(r.get('observation_utc', r['capture_utc'])) for r in valid)):continue
            if (max(datetime.fromisoformat(r['verifie_utc']) for r in train+valid)
                    >=min(datetime.fromisoformat(r.get('observation_utc', r['capture_utc'])) for r in held)):continue
            pair=(validation,test);break
        if pair:break
    if pair:
        from .experience_ml import run
        output=cache/'ml/experiences'/('automatique-'+empreinte[:20])
        report=run(cache,output,*pair,now=now)
        result.update(statut=report['statut'],rapport=str((output/'rapport.json').relative_to(cache)),
                      validation_day=pair[0],test_day=pair[1],
                      modele=report['modele_choisi_avant_test'],test_ml=report['test_ml'],
                      comparaison=report.get('ecart_ml_forme_capture'),decoupage=report['decoupage'])
    else:result['motif']='Trois périodes avec étiquettes disponibles avant les captures suivantes sont nécessaires.'
    save(path,result)
    return result
