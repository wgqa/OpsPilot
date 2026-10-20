from __future__ import annotations
import asyncio,hashlib,json,os,time,uuid,sys
from datetime import datetime,timezone
from pathlib import Path
import httpx
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
OUTPUT=ROOT/'docs/evidence/vnext/m3-closeout-01/runs/journey-01'
known_secrets=[v for k,v in os.environ.items() if k in {'OPSPILOT_MODEL_API_KEY','OPSPILOT_WEB_SUPPORT_PASSWORD','OPSPILOT_WEB_APPROVER_PASSWORD','OPSPILOT_WEB_SUPPORT_B_PASSWORD','OPSPILOT_WEB_APPROVER_B_PASSWORD'} and v]

def write(record):
 record={'at':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),**record}
 text=json.dumps(record,ensure_ascii=False)
 for value in known_secrets:text=text.replace(value,'[REDACTED]')
 with (OUTPUT/'provider-wire.jsonl').open('a',encoding='utf-8') as f:f.write(text+'\n')

def observe(request):
 if request.method!='POST':return None
 try: raw=request.content; body=json.loads(raw)
 except (ValueError,httpx.RequestNotRead):return None
 if not isinstance(body,dict) or 'model' not in body or not isinstance(body.get('messages'),list):return None
 request_id='wire-'+str(uuid.uuid4())
 write({'kind':'PROVIDER_REQUEST','request_ref':request_id,'body_sha256':hashlib.sha256(raw).hexdigest(),'payload':body,'headers_omitted':True,'url_omitted':True,'observer_only':True})
 return request_id
original_async=httpx.AsyncClient.send
async def async_send(self,request,*args,**kwargs):
 ref=observe(request)
 try: response=await original_async(self,request,*args,**kwargs)
 except BaseException as error:
  if ref:write({'kind':'PROVIDER_TRANSPORT_EXCEPTION','request_ref':ref,'exception_class':type(error).__name__})
  raise
 if ref:write({'kind':'PROVIDER_RESPONSE_HEADERS','request_ref':ref,'status_code':response.status_code})
 return response
httpx.AsyncClient.send=async_send
original_sync=httpx.Client.send
def sync_send(self,request,*args,**kwargs):
 ref=observe(request)
 response=original_sync(self,request,*args,**kwargs)
 if ref:write({'kind':'PROVIDER_RESPONSE_HEADERS','request_ref':ref,'status_code':response.status_code})
 return response
httpx.Client.send=sync_send
write({'kind':'APPLICATION_BOOT','actual_api_pid':os.getpid(),'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('opspilot/domain/chat.py','opspilot/domain/episodic_memory.py','opspilot/investigator.py','opspilot/web/app.py','opspilot/web/worker.py')},'observer_description':'Real httpx send forwarding unchanged; request body only; no headers or secret tables'})
from opspilot.web.server import main
raise SystemExit(main())
