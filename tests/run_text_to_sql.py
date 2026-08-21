import argparse,json,os,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
import httpx
CASE_RE=re.compile(r"^## \u6e2c\u8a66\u500b\u6848\s+(\d+)\s*$",re.M)
Q_RE=re.compile(r"^>\s*(.+?)\s*$",re.M)
F=chr(96)*3
SQL_RE=re.compile(re.escape(F)+r"sql\s*\n(.*?)"+re.escape(F),re.S|re.I)
def load_cases(p):
 t=p.read_text(encoding="utf-8"); hs=list(CASE_RE.finditer(t)); out=[]
 for i,h in enumerate(hs):
  s=t[h.start():hs[i+1].start() if i+1<len(hs) else len(t)]; q=Q_RE.search(s); bs=SQL_RE.findall(s)
  if not q or not bs: raise ValueError("invalid case "+h.group(1))
  sql=[]
  for b in bs:
   for x in b.split(";"):
    x="\n".join(y for y in x.splitlines() if not y.strip().startswith("--")).strip()
    if x: sql.append(x+";")
  out.append({"case_id":h.group(1),"question":q.group(1).strip(),"expected_sql":sql})
 return out
def norm(x): return re.sub(r"\s+"," "," ".join(y for y in x.splitlines() if not y.strip().startswith("--"))).strip().rstrip(";").lower()
def sse(raw):
 out=[]
 for f in re.split(r"\r?\n\r?\n",raw):
  d=[x[5:].lstrip() for x in f.splitlines() if x.startswith("data:")]
  if d: out.append(json.loads("\n".join(d)))
 return out
def sqls(events):
 out=[]
 for e in events:
  p=e.get("payload") or {}; a=p.get("arguments") or {}
  if e.get("type")=="tool_call" and p.get("name")=="execute_sql_query" and isinstance(a,dict) and a.get("query"): out.append(str(a["query"]))
 return out
def run(c,case,token,timeout):
 h={"Authorization":"Bearer "+token}; r=c.post("/api/conversations",json={"title":"Text-to-SQL E2E "+case["case_id"]},headers=h); r.raise_for_status(); cid=r.json()["id"]
 r=c.post("/api/messages",data={"content":case["question"],"conversation_id":str(cid)},headers=h); r.raise_for_status(); mid=r.json()["reply"]["id"]
 r=c.get("/api/messages/"+str(mid)+"/stream",params={"after_sequence":0},headers={**h,"Accept":"text/event-stream"},timeout=timeout); raw=r.text; r.raise_for_status(); ev=sse(raw); actual=sqls(ev); exp=[norm(x) for x in case["expected_sql"]]; got=[norm(x) for x in actual]
 return {"case_id":case["case_id"],"question":case["question"],"conversation_id":cid,"message_id":mid,"expected_sql":case["expected_sql"],"actual_sql":actual,"expected_sql_normalised":exp,"actual_sql_normalised":got,"sql_count_match":len(exp)==len(got),"exact_sql_match":exp==got,"event_types":[x.get("type") for x in ev],"sequences":[x.get("sequence") for x in ev],"terminal_event":ev[-1].get("type") if ev else None,"raw_sse":raw,"events":ev}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--cases",type=Path,default=Path("/runner/text_to_sql_qa_test_cases.md")); p.add_argument("--base-url",default=os.getenv("BASE_URL","http://simplechat-frontend")); p.add_argument("--email",default=os.getenv("TEST_EMAIL")); p.add_argument("--password",default=os.getenv("TEST_PASSWORD")); p.add_argument("--display-name",default=os.getenv("TEST_DISPLAY_NAME","Text-to-SQL E2E")); p.add_argument("--output-dir",type=Path,default=Path(os.getenv("RESULTS_DIR","/results"))); p.add_argument("--case",action="append",dest="ids"); p.add_argument("--timeout",type=float,default=300); a=p.parse_args()
 if not a.email or not a.password: p.error("set TEST_EMAIL and TEST_PASSWORD")
 cases=load_cases(a.cases); cases=[x for x in cases if not a.ids or x["case_id"] in a.ids]; a.output_dir.mkdir(parents=True,exist_ok=True); st=datetime.now(timezone.utc); rid=st.strftime("%Y%m%dT%H%M%SZ"); result=[]; error=None; t=time.monotonic()
 with httpx.Client(base_url=a.base_url.rstrip("/"),follow_redirects=True) as c:
  try:
   r=c.post("/api/auth/register",json={"email":a.email,"password":a.password,"display_name":a.display_name})
   if r.status_code not in (201,400): raise RuntimeError("register "+str(r.status_code))
   r=c.post("/api/auth/login",json={"email":a.email,"password":a.password}); r.raise_for_status(); token=r.json()["access_token"]
   for x in cases:
    try: result.append(run(c,x,token,a.timeout))
    except Exception as e: result.append({"case_id":x["case_id"],"question":x["question"],"error":str(e)})
  except Exception as e: error=str(e)
 art={"schema_version":1,"run_id":rid,"started_at":st.isoformat(),"elapsed_seconds":round(time.monotonic()-t,3),"base_url":a.base_url,"case_file":str(a.cases),"selected_cases":[x["case_id"] for x in cases],"run_error":error,"results":result}; out=a.output_dir/("text_to_sql_"+rid+".json"); out.write_text(json.dumps(art,ensure_ascii=False,indent=2),encoding="utf-8"); print(out)
 return 1 if error or any(x.get("error") or x.get("terminal_event")!="done" or not x.get("sql_count_match") for x in result) else 0
if __name__=="__main__": sys.exit(main())
