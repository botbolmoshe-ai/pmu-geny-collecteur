"""Test d'une page de donnees hippiques Equidia en lecture seule; pas d'historique presume."""
import json,datetime
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
URLS=["https://www.equidia.fr/courses","https://www.equidia.fr/"]
def probe(url):
 r={"url":url,"http":None,"performances_historiques":0,"historique_valide":False}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=18) as resp:
   raw=resp.read(300000);s=raw.decode("utf-8","replace").lower();r.update(http=resp.status,octets=len(raw),mentions_cheval=s.count("cheval"),mentions_performances=s.count("performance"),type_contenu=resp.headers.get("Content-Type",""))
 except HTTPError as e:r.update(http=e.code,erreur="HTTPError")
 except (URLError,TimeoutError,OSError) as e:r["erreur"]=type(e).__name__
 return r
if __name__=="__main__":print(json.dumps({"source":"equidia","test_type":"PAGES_HIPPIQUES_REELLES","date_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"sondes":[probe(u) for u in URLS],"historique_valide":False},ensure_ascii=False))
