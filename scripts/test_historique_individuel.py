"""Un seul cheval tire au hasard : extraction Geny et rapport, sans production."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pmu_geny.extraction_historique_par_cheval import extraire_cheval
from pmu_geny.controle_historique import classifier
from pmu_geny.liaison_chevaux_v22 import nom_normalise

def main():
    selection=json.loads((ROOT/'experiments/test-individuel/tirage.json').read_text())
    horse=selection['cible'];geny=horse['geny'];url=geny['url_geny']
    assert horse['statut_sheet']=='HISTO_NON_COLLECTE' and horse['rang_arrivee']>0
    assert nom_normalise(horse['nom'])==nom_normalise(geny['nom'])
    assert urlparse(url).hostname=='www.geny.com' and urlparse(url).path.startswith('/cheval/'+geny['id']+'-')
    out=ROOT/'resultats/test-individuel';out.mkdir(parents=True,exist_ok=True)
    report={'debut_utc':datetime.now(timezone.utc).isoformat(),'mode':'TEST_UN_CHEVAL_SANS_ECRITURE_PRODUCTION',
            'tirage':selection,'source_url':url,'historique_valide':False,'nombre_extrait':0}
    try:
        result=extraire_cheval(url,geny['id'],out)
        status,reasons=classifier(result)
        folder=out/geny['id']
        text=(folder/'diagnostic_texte_geny.txt').read_text(encoding='utf-8') if (folder/'diagnostic_texte_geny.txt').exists() else ''
        identity=nom_normalise(horse['nom']) in nom_normalise(text[:6000])
        report.update(statut=status,motifs=reasons,code_retour=result.get('code_retour'),
                      nombre_annonce=result.get('nombre_annonce_geny'),nombre_extrait=result.get('nombre_extrait',0),
                      identite_page_verifiee=identity,historique_valide=status=='COMPLET' and identity)
        if (folder/'controle_acces.json').exists():
            report['controle_acces']=json.loads((folder/'controle_acces.json').read_text())
        if (folder/'etat_collecte.json').exists():
            report['etat_collecte']=json.loads((folder/'etat_collecte.json').read_text())
    except Exception as exc:
        report.update(statut='ERREUR_TEST',erreur=f'{type(exc).__name__}: {exc}')
    report['fin_utc']=datetime.now(timezone.utc).isoformat()
    (out/'rapport.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESULTAT_TEST_INDIVIDUEL '+json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report['historique_valide'] else 1

if __name__=='__main__':sys.exit(main())
