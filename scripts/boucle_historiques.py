"""File durable : un processus/cheval, sauvegarde et Sheets avant de poursuivre."""
import argparse,csv,json,os,shutil,subprocess,sys,time
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.synchroniser_un_historique import persister,synchroniser,git
STATE=ROOT/'collecte_unitaire/etat.json'
BRANCH='test/boucle-historiques-courus'

def now():return datetime.now(timezone.utc)
def due(stamp,instant):return not stamp or datetime.fromisoformat(stamp)<=instant
def choisir(state,instant):
    # Une synchronisation deja collectee n'exige jamais une nouvelle requete Geny.
    for key,h in state['chevaux'].items():
        if h['collecte']=='COMPLET' and h['sync']!='OK' and h.get('sync_tentatives_execution',h['sync_tentatives'])<3 and due(h.get('prochaine_sync_utc'),instant):return key,'SYNC'
    pending=any(h['collecte']!='COMPLET' and h.get('tentatives_execution',h['tentatives'])<2 for h in state['chevaux'].values())
    sync_pending=any(h['collecte']=='COMPLET' and h['sync']!='OK' and h.get('sync_tentatives_execution',h['sync_tentatives'])<3 for h in state['chevaux'].values())
    if not pending:return (None,'ATTENTE' if sync_pending else 'TERMINE')
    if not due(state.get('prochain_acces_geny_utc'),instant):return None,'COOLDOWN'
    for key,h in state['chevaux'].items():
        if h['collecte']!='COMPLET' and h.get('tentatives_execution',h['tentatives'])<2 and due(h.get('prochain_essai_utc'),instant):return key,'COLLECTE'
    waiting=pending or sync_pending
    return None,'ATTENTE' if waiting else 'TERMINE'

def pousser_checkpoint():
    for attempt in range(3):
        try:
            git('push','origin','HEAD:refs/heads/'+BRANCH)
            return
        except subprocess.CalledProcessError:
            if attempt==2:raise
            time.sleep(5*(attempt+1))
            git('fetch','origin',BRANCH)
            # Ne jamais ecraser une modification concurrente de la branche.
            git('merge-base','--is-ancestor','origin/'+BRANCH,'HEAD')

def enregistrer(state,message,publier=True):
    state['maj_utc']=now().isoformat()
    state['bilan']={'total':len(state['chevaux']),'collectes_completes':sum(h['collecte']=='COMPLET' for h in state['chevaux'].values()),
                    'synchronises':sum(h['sync']=='OK' for h in state['chevaux'].values()),
                    'statuts':dict(Counter(h['collecte'] for h in state['chevaux'].values()))}
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    with (ROOT/'collecte_unitaire/progression.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['cheval','collecte','sheets','performances','tentatives','erreur'])
        for h in state['chevaux'].values():w.writerow([h['nom'],h['collecte'],h['sync'],h.get('nombre_extrait',0),h['tentatives'],h.get('erreur','')])
    if publier:
        git('add','collecte_unitaire')
        if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode:
            git('commit','-m',message)
            pousser_checkpoint()
    print('PROGRESSION '+json.dumps(state['bilan'],ensure_ascii=False),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--max-minutes',type=int,default=210);a=p.parse_args()
    if not os.environ.get('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'):raise RuntimeError('Secret Sheets absent : aucune collecte lancee')
    if git('branch','--show-current')!=BRANCH:raise RuntimeError('Branche de travail inattendue')
    if not STATE.exists():shutil.copy2(ROOT/'collecte_unitaire/etat_initial.json',STATE)
    state=json.loads(STATE.read_text());deadline=time.monotonic()+a.max_minutes*60
    state['execution_statut']='EN_COURS'
    state['execution_debut_utc']=now().isoformat()
    # Un sous-processus tue avant le checkpoint reste reprenable.
    for h in state['chevaux'].values():
        if h['collecte']=='EN_COURS':h['collecte']='A_REPRENDRE'
        h['tentatives_execution']=0;h['sync_tentatives_execution']=0
    enregistrer(state,'Boucle : reprise de la file persistante')
    last_request=0
    while time.monotonic()<deadline:
        key,action=choisir(state,now())
        if action=='TERMINE':break
        if key is None:
            print('ATTENTE '+action,flush=True);time.sleep(45);continue
        h=state['chevaux'][key]
        if action=='COLLECTE':
            # Espacement commun ; chaque extraction utilise son propre processus et navigateur.
            delay=max(0,30-(time.monotonic()-last_request))
            if delay:time.sleep(delay)
            h.update(collecte='EN_COURS',tentatives=h['tentatives']+1)
            h['tentatives_execution']+=1
            enregistrer(state,'Collecte individuelle : '+h['nom'],publier=False)
            result_path=ROOT/'collecte_unitaire/dernier_resultat.json';result_path.unlink(missing_ok=True)
            try:
                subprocess.run([sys.executable,str(ROOT/'scripts/collecter_un_cheval.py'),'--cle',key],cwd=ROOT,timeout=240,check=True)
                report=json.loads(result_path.read_text())
            except Exception as exc:report={'complet':False,'statut':'ERREUR','erreur':f'{type(exc).__name__}: {exc}'}
            last_request=time.monotonic()
            if report.get('geny'):h['geny']=report['geny']
            if report.get('complet'):
                src=Path(report['dossier']);dest=ROOT/'collecte_unitaire/historiques'/h['geny']['id'];dest.mkdir(parents=True,exist_ok=True)
                for file in src.glob('historique_geny.*'):shutil.copy2(file,dest/file.name)
                h.update(collecte='COMPLET',nombre_extrait=report['nombre_extrait'],preuves=report,sync='A_FAIRE')
            else:
                h.update(collecte=report.get('statut','ERREUR'),erreur=report.get('erreur') or str(report.get('motifs',[])),preuves=report,
                         prochain_essai_utc=(now()+timedelta(minutes=5)).isoformat())
                # Une URL invalide est re-resolue sur la course lors de la reprise.
                if h['collecte'] not in ('ACCES_LIMITE_429','ACCES_REFUSE_403'):h['geny']=None
                if h['collecte'] in ('ACCES_LIMITE_429','ACCES_REFUSE_403'):
                    state['prochain_acces_geny_utc']=(now()+timedelta(minutes=30)).isoformat()
                    h['prochain_essai_utc']=state['prochain_acces_geny_utc']
            enregistrer(state,'Resultat individuel : '+h['nom']+' '+h['collecte'])
            if h['collecte']!='COMPLET':continue
        try:
            h['sync_tentatives']+=1
            h['sync_tentatives_execution']+=1
            if not h.get('stockage_durable_ok'):
                persister(h);h['stockage_durable_ok']=True
                enregistrer(state,'Historique sauvegarde dans pmu-data : '+h['nom'],publier=False)
            h['sync_details']=synchroniser(h,state['spreadsheet_id'])
            h.update(sync='OK',sync_utc=now().isoformat(),erreur='')
        except Exception as exc:
            h.update(sync='A_REPRENDRE',erreur=f'{type(exc).__name__}: {exc}',prochaine_sync_utc=(now()+timedelta(minutes=2)).isoformat())
        enregistrer(state,'Sheets : '+h['nom']+' '+h['sync'])
    state['execution_terminee_utc']=now().isoformat()
    state['execution_statut']='COMPLETE' if all(h['sync']=='OK' for h in state['chevaux'].values()) else 'PARTIELLE_REPRENABLE'
    enregistrer(state,'Boucle : '+state['execution_statut'])

if __name__=='__main__':main()
