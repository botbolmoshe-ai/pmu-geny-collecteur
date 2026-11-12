"""Essai reel, lecture seule, de donnees de courses PMU. Ne valide pas l'historique par simple HTTP 200."""
import json,datetime
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
BASE="https://online.turfinfo.api.pmu.fr/rest/client/1/programme/"
DATE="12112026"
URLS=[BASE+DATE,BASE+DATE+"/R1/C1/participants"]
def probe(url):
 r={"url":url,"http":None,"chevaux_identifies":0,"performances_historiques":0,"historique_valide":False}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=18) as resp:
   raw=resp.read(1500000);r["http"]=resp.status;r["octets"]=len(raw)
   try:
    data=json.loads(raw);r["json_valide"]=True
    if isinstance(data,dict):
     r["cles_racine"]=list(data)[:20]
     for key in ("participants","partants"):
      if isinstance(data.get(key),list):
       r["chevaux_identifies"]=sum(isinstance(x,dict) and bool(x.get("nom")) for x in data[key]);r["noms_exemples"]=[x.get("nom") for x in data[key][:3] if isinstance(x,dict)]
    # Un tableau de partants n'est pas un historique individuel.
   except (ValueError,UnicodeError):r["json_valide"]=False
 except HTTPError as e:r.update(http=e.code,erreur="HTTPError")
 except (URLError,TimeoutError,OSError) as e:r["erreur"]=type(e).__name__
 return r
if __name__=="__main__":print(json.dumps({"source":"pmu","test_type":"DONNEES_COURSE_REELLES","date_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"sondes":[probe(u) for u in URLS],"historique_valide":False},ensure_ascii=False))
