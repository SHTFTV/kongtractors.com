"""Read-only independent observer: Vercel execution observes the GitHub writer.
No dispatch, repository mutation, model calls, credentials or synthetic publication.
"""
from http.server import BaseHTTPRequestHandler
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.parse import urlsplit,parse_qs
from datetime import datetime,timezone
import json,hashlib,os,re
RUNS='https://api.github.com/repos/SHTFTV/kongtractors.com/actions/workflows/417669097/runs?event=schedule&per_page=3'
STATE='https://raw.githubusercontent.com/SHTFTV/kongtractors.com/main/operations/publisher-state.json'
SLA_MINUTES=45
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def fetch(url):
 if url not in [RUNS,STATE] and not re.fullmatch(r'https://kongtractors\.com/(?:blog/[a-z0-9-]+\.html|assets/[a-z0-9-]+\.jpg)',url):raise ValueError('UNBOUND_OBSERVATION_URL')
 req=Request(url,headers={'User-Agent':'Kong-Independent-Watchdog/1.0','Accept':'application/json,text/html,image/jpeg','Cache-Control':'no-cache'})
 with build_opener(NoRedirect).open(req,timeout=8) as r:
  if r.status!=200:raise ValueError('UPSTREAM_HTTP_'+str(r.status))
  body=r.read(3000001)
  if len(body)>3000000:raise ValueError('UPSTREAM_SIZE_BOUND')
  return body

def iso(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
def evaluate(runs,state,now,probe=None):
 failures=[];native=[r for r in runs.get('workflow_runs',[]) if r.get('event')=='schedule'];latest=native[0] if native else None
 age=round((now-iso(latest['created_at'])).total_seconds()/60,2) if latest else None
 if latest is None:failures.append('native-schedule-never-observed')
 elif age<0:failures.append('native-schedule-timestamp-invalid')
 elif age>SLA_MINUTES:failures.append('native-schedule-stale')
 elif latest.get('status')=='completed' and latest.get('conclusion')!='success':failures.append('native-schedule-failed')
 pending=[p for p in state.get('published',[]) if p.get('status')!='live-verified']
 if pending:failures.append('publication-awaiting-live-verification')
 if state.get('blocked'):failures.append('reviewed-brief-blocked')
 releases=[p for p in state.get('published',[]) if p.get('status')=='live-verified'];release=releases[-1] if releases else None
 synthetic=probe=='stale-schedule'
 if synthetic:failures=['controlled-native-schedule-stale']
 incident=None
 if failures:
  incident={'id':('kong-watchdog-controlled-gap-v1' if synthetic else 'kong-watchdog-'+str(latest.get('id') if latest else 'missing-schedule')),'site':'kongtractors.com','status':'failed','title':'Kong publisher attention: '+', '.join(failures),'at':now.isoformat(),'runUrl':latest.get('html_url') if latest else None,'synthetic':synthetic}
 return {'site':'kongtractors.com','role':'independent-watchdog','executionProvider':'vercel','actorId':'kong-vercel-read-only-watchdog','observedAt':now.isoformat(),'observerSourceCommit':os.environ.get('VERCEL_GIT_COMMIT_SHA'),'scope':'Native reviewed-brief writer freshness and last committed publication; not autonomous research/authoring','status':'held' if failures else 'healthy','failures':failures,'scheduler':{'provider':'github-actions','thresholdMinutes':SLA_MINUTES,'ageMinutes':age,'runRef':latest.get('html_url') if latest else None,'runId':latest.get('id') if latest else None,'sourceCommit':latest.get('head_sha') if latest else None,'conclusion':latest.get('conclusion') if latest else None},'latestVerifiedPublication':release,'pendingPublications':len(pending),'incident':incident,'synthetic':synthetic,'ownerDeliveryVerified':False,'ownerDelivery':{'status':'unverified','route':'Existing owner reader must consume this public pull endpoint and retain receipt'},'automaticResearchAuthorConfigured':False,'fourRolesApproved':False}

def observe(probe=None):
 now=datetime.now(timezone.utc)
 try:
  runs=json.loads(fetch(RUNS));state=json.loads(fetch(STATE));result=evaluate(runs,state,now,probe)
  pub=result['latestVerifiedPublication']
  if pub and not result['synthetic']:
   body=fetch(pub['url']).decode('utf-8');photo=fetch(pub['featuredImage'])
   ok=pub['datePublished'] in body and pub['title'] in body and hashlib.sha256(photo).hexdigest()==pub['featuredImageSha256']
   result['lastPublicationHTTPAndImageVerified']=ok
   if not ok:
    result['failures'].append('last-publication-or-image-mismatch');result['status']='held';result['incident']={'id':'kong-last-publication-mismatch-'+pub['id'],'site':'kongtractors.com','status':'failed','title':'Kong last publication or featured image differs from verified release','at':now.isoformat(),'synthetic':False}
  return result
 except Exception as exc:
  # An observer transport failure is unknown, not proof the publisher is down.
  print(json.dumps({'watchdogError':type(exc).__name__,'detail':str(exc)[:250]}),flush=True)
  return {'site':'kongtractors.com','role':'independent-watchdog','executionProvider':'vercel','actorId':'kong-vercel-read-only-watchdog','observedAt':now.isoformat(),'observerSourceCommit':os.environ.get('VERCEL_GIT_COMMIT_SHA'),'status':'observation-unavailable','failures':['upstream-observation-unavailable'],'incident':{'id':'kong-watchdog-upstream-observation-unavailable','site':'kongtractors.com','status':'failed','title':'Kong publisher watchdog cannot obtain current source evidence','at':now.isoformat(),'synthetic':False},'ownerDeliveryVerified':False,'fourRolesApproved':False}

class handler(BaseHTTPRequestHandler):
 def do_GET(self):
  query=parse_qs(urlsplit(self.path).query);probe=query.get('probe',[None])[0]
  if probe not in [None,'stale-schedule']:
   self.send_response(400);self.end_headers();return
  result=observe(probe);body=json.dumps(result,separators=(',',':')).encode()
  print(json.dumps({'site':'kongtractors.com','watchdog':result['status'],'failures':result.get('failures'),'synthetic':result.get('synthetic',False)}),flush=True)
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store' if probe else 'public, max-age=0, s-maxage=300');self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(body)
