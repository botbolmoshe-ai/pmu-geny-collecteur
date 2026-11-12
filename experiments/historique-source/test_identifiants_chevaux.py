"""Explorer les identifiants PMU et tester des fiches cheval en lecture seule.
Aucune performance n'est declaree extraite sans lignes datees validees.
"""
import datetime,json,re
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
BASE="https://online.turfinfo.api.pmu.fr/rest/client/1/programme/12112026/R1/C1/participants"
def get(url):
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=15) as r:
   b=r.read(1000000);return r.status,json.loads(b)
 except HTTPError as e:return e.code,None
 except (URLError,OSError,ValueError,TimeoutError):return None,None
def main():
 status,root=get(BASE)
 result={"source":"pmu","type":"IDENTIFIANTS_ET_HISTORIQUES","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"http_participants":status,"chevaux_testes":0,"performances_historiques_validees":0,"chevaux_historique_valide":0,"resultats":[]}
 if not isinstance(root,dict):print(json.dumps(result,ensure_ascii=False));return
 horses=root.get("participants",[])
 result["chevaux_disponibles"]=len(horses)
 result["cles_participant"]=sorted(horses[0]) if horses else []
 for horse in horses[:3]:
  name=horse.get("nom");ids={k:v for k,v in horse.items() if re.search("id|ident|ref|code|numero",k,re.I) and isinstance(v,(int,str))}
  item={"nom":name,"identifiants":ids,"historique_valide":False,"performances_validees":0,"essais":[]}
  # Ne sonder que des chemins de fiches individuels pour des identifiants explicitement exposes.
  for key,val in list(ids.items())[:2]:
   if not re.search("cheval|participant|id",key,re.I) or not str(val).isdigit():continue
   for url in [f"https://online.turfinfo.api.pmu.fr/rest/client/1/cheval/{val}",f"https://online.turfinfo.api.pmu.fr/rest/client/1/chevaux/{val}/performances"]:
    code,data=get(url);item["essais"].append({"url":url,"http":code,"json":isinstance(data,(dict,list)),"cles":list(data)[:12] if isinstance(data,dict) else []})
  result["resultats"].append(item)
 result["chevaux_testes"]=len(result["resultats"])
 print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
