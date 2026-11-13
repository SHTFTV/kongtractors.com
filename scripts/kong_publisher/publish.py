#!/usr/bin/env python3
"""Sole Kong article writer. Reviewed briefs -> pages -> fixed site outputs.
No LLM calls, new paid resources, secrets, shell/source execution or unreviewed
feed-to-production route. The independent portfolio collector stays independent.
"""
import argparse, copy, datetime as dt, email.utils, hashlib, html, json, os, re, shutil, struct, subprocess, sys
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit, urlunsplit
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[2]
PACIFIC=ZoneInfo('America/Los_Angeles')
STATE='operations/publisher-state.json'
FIXED={'index.html','blog/index.html','feed.xml','sitemap.xml','vercel.json',STATE}
SPONSOR=re.compile(r'\b(?:sponsored|advertorial|paid (?:partnership|promotion|placement|content))\b',re.I)
class Rejected(Exception): pass
class Visible(HTMLParser):
    def __init__(self): super().__init__(); self.skip=0; self.parts=[]
    def handle_starttag(self,t,a):
        if t in ('script','style','noscript'): self.skip+=1
    def handle_endtag(self,t):
        if t in ('script','style','noscript') and self.skip: self.skip-=1
    def handle_data(self,s):
        if not self.skip:self.parts.append(s)
def visible(raw):
    p=Visible();p.feed(raw.decode('utf-8',errors='replace'));return ' '.join(p.parts)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def stable(obj):return digest(json.dumps(obj,sort_keys=True,separators=(',',':')).encode())
def canonical(u):
    p=urlsplit(u)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):raise Rejected('SOURCE_URL_NOT_HTTPS')
    return urlunsplit(('https',p.netloc.lower(),p.path or '/',p.query,''))
def get(u):
    # Reviewed exact public URLs only. Follow HTTPS redirects, no local/file URLs.
    r=subprocess.run(['curl','--fail','--silent','--show-error','--location','--proto','=https','--proto-redir','=https','--connect-timeout','10','--max-time','40','--retry','1','--retry-delay','2','--max-filesize','25000000',u],capture_output=True)
    if r.returncode:raise Rejected('SOURCE_FETCH_FAILED:'+str(r.returncode)+':'+u)
    return r.stdout

def jpg_dimensions(raw):
    if raw[:2]!=b'\xff\xd8':raise Rejected('FEATURED_IMAGE_NOT_JPEG')
    i=2
    while i<len(raw):
        if raw[i]!=255:i+=1;continue
        while raw[i]==255:i+=1
        marker=raw[i];i+=1
        if marker in (0xd8,0xd9):continue
        n=int.from_bytes(raw[i:i+2],'big')
        if marker in (0xc0,0xc1,0xc2):
            h,w=struct.unpack('>HH',raw[i+3:i+7]);return w,h
        i+=n
    raise Rejected('IMAGE_DIMENSIONS_UNREADABLE')

def check_runtime(root,policy,fetch):
    if policy['repository']!='SHTFTV/kongtractors.com' or policy['branch']!='main' or policy['domain']!='https://kongtractors.com':raise Rejected('WRONG_RESOURCE_BINDING')
    if os.getenv('GITHUB_ACTIONS')=='true':
        if os.getenv('GITHUB_REPOSITORY')!=policy['repository'] or os.getenv('GITHUB_REF')!='refs/heads/main':raise Rejected('WRONG_RUNTIME_REPOSITORY_OR_BRANCH')
    for path,expected in policy['codeManifest'].items():
        if digest((root/path).read_bytes())!=expected:raise Rejected('CODE_MANIFEST_CHANGED:'+path)
    sot=(root/'operations/KONGTRACTORS-SOT.md').read_bytes()
    if digest(sot)!=policy['siteSotSha256']:raise Rejected('SITE_SOT_CHANGED')
    register=json.loads(fetch(policy['sharedPreflight']['url']))
    if stable(register)!=policy['sharedPreflight']['canonicalJsonSha256'] or register['version']!=policy['sharedPreflight']['version']:raise Rejected('SHARED_PREFLIGHT_CHANGED_REVIEW_REQUIRED')
    # Existing held actions remain held. This workflow neither installs the
    # private policy bundle nor performs shared-v3 or secret changes.
    for case in register.get('cases',[]):
        if case.get('site')=='kongtractors.com' and case.get('operation') in ('unattended_repository_write','production_content_release') and case.get('state')=='rejected-held':raise Rejected('EXACT_KONG_ACTION_HELD:'+case['id'])
    return {'siteSotSha256':digest(sot),'sharedPreflightVersion':register['version'],'sharedPreflightDigest':stable(register),'codeManifestDigest':stable(policy['codeManifest'])}

def validate_brief(root,b,policy,fetch,now):
    slug=b.get('slug','')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+){2,100}',slug):raise Rejected('INVALID_SLUG')
    review=b.get('review',{})
    if review.get('paidPromotion') or review.get('state') in ('sponsored','excluded-paid'):raise Rejected('EXCLUDED_PAID_PROMOTION')
    if review.get('state')!='reviewed' or not review.get('factsAndLimitsChecked') or review.get('desktopPhoneVisualCheck')!='passed':raise Rejected('EDITORIAL_REVIEW_INCOMPLETE')
    reviewed=dt.datetime.fromisoformat(review['reviewedAt'])
    if reviewed.tzinfo is None or reviewed>now or (now-reviewed).days>policy['maxReviewAgeDays']:raise Rejected('STALE_OR_INVALID_REVIEW')
    if len(b.get('bodyHtml',''))<1600 or re.search(r'<(?:script|iframe|form|object)\b|\bon\w+\s*=',b['bodyHtml'],re.I):raise Rejected('INVALID_REVIEWED_BODY')
    source=canonical(b['sourceCanonicalUrl'])
    if source not in [s['url'] for s in b['sources']]:raise Rejected('CANONICAL_SOURCE_NOT_REVIEWED')
    seen=set()
    for s in b['sources']:
        u=canonical(s['url'])
        if u in seen:raise Rejected('DUPLICATE_SOURCE')
        seen.add(u)
        if urlsplit(u).hostname not in policy['allowedSourceHosts']:raise Rejected('SOURCE_HOST_NOT_APPROVED')
        data=fetch(u)
        if s['type']=='pdf':
            if not data.startswith(b'%PDF-') or digest(data)!=s['sha256']:raise Rejected('REVIEWED_DOCUMENT_CHANGED:'+u)
        else:
            text=visible(data)
            if SPONSOR.search(text):raise Rejected('EXCLUDED_SOURCE_DISCLOSURE:'+u)
            if not all(term.lower() in text.lower() for term in s.get('requiredText',[])):raise Rejected('REVIEWED_FACT_ANCHOR_MISSING:'+u)
    media=b['media'];path=media['path']
    if not re.fullmatch(r'assets/[a-z0-9-]+\.jpg',path):raise Rejected('INVALID_FEATURED_PATH')
    data=(root/path).read_bytes()
    if jpg_dimensions(data)!=(1600,900) or digest(data)!=media['sha256']:raise Rejected('FEATURED_IMAGE_IDENTITY_CHANGED')
    return source

def render(root,b,now):
    date=now.astimezone(PACIFIC).isoformat(timespec='seconds');display=now.astimezone(PACIFIC).strftime('%B %d, %Y').replace(' 0',' ')
    url='https://kongtractors.com/blog/'+b['slug']+'.html';im='/'+b['media']['path'];e=html.escape
    schema={'@context':'https://schema.org','@type':'Article','headline':b['title'],'description':b['description'],'datePublished':date,'dateModified':date,'mainEntityOfPage':url,'articleSection':'Compact equipment guides','image':{'@type':'ImageObject','url':'https://kongtractors.com'+im,'width':1600,'height':900,'creditText':'Ditch Witch / The Charles Machine Works, Inc.; Kong editorial panel'},'isBasedOn':[s['url'] for s in b['sources']],'author':{'@type':'Organization','name':'Kong Journal'},'publisher':{'@type':'Organization','name':'Kong Tractors','url':'https://kongtractors.com'}}
    fields={'TITLE':e(b['title']),'DESCRIPTION':e(b['description']),'URL':url,'IMAGE_URL':'https://kongtractors.com'+im,'DATE':date,'SCHEMA':json.dumps(schema).replace('<','\\u003c'),'CATEGORY':e(b['category']),'DECK':e(b['deck']),'DISPLAY_DATE':display,'IMAGE':im,'ALT':e(b['media']['alt']),'CREDIT':b['media']['creditHtml'],'BODY':b['bodyHtml'],'SOURCES':''.join('<li><a href="'+e(s['url'],quote=True)+'">'+e(s['label'])+'</a></li>' for s in b['sources']),'EDITORIAL_NOTE':e(b['editorialNote'])}
    article=(root/'editorial/templates/article.html').read_text()
    for key,val in fields.items():article=article.replace('@@'+key+'@@',val)
    if '@@' in article:raise Rejected('TEMPLATE_TOKEN_UNRESOLVED')
    card=f'<a class="kj-card" href="/blog/{b["slug"]}.html"><img src="{im}" width="1600" height="900" loading="lazy" alt="{e(b["media"]["alt"],quote=True)}" style="aspect-ratio:16/9;object-fit:contain;background:#101110"><div><p class="k-kicker">COMPACT EQUIPMENT / ACCESS GUIDE</p><time datetime="{date}">{display}</time><h3>{e(b["title"])}</h3><p>{e(b["description"])}</p><span>READ THE GUIDE ↗</span></div></a>'
    outputs={'blog/'+b['slug']+'.html':article}
    for path in ['index.html','blog/index.html']:
        text=(root/path).read_text()
        if text.count('<div class="kj-cards">')!=1:raise Rejected('ARCHIVE_INSERTION_TARGET_CHANGED:'+path)
        text=text.replace('<div class="kj-cards">','<div class="kj-cards">'+card,1)
        if path=='index.html':text=re.sub(r'Latest article: <time.*?</time>',f'Latest article: <time datetime="{date}">{display}</time>',text)
        outputs[path]=text
    feed=(root/'feed.xml').read_text();item=f'<item><title>{e(b["title"])}</title><link>{url}</link><guid>{url}</guid><pubDate>{email.utils.format_datetime(now.astimezone(PACIFIC))}</pubDate><description>{e(b["description"])}</description></item>'
    if '<item>' not in feed:raise Rejected('FEED_INSERTION_TARGET_CHANGED')
    outputs['feed.xml']=feed.replace('<item>',item+'<item>',1)
    outputs['sitemap.xml']=(root/'sitemap.xml').read_text().replace('</urlset>',f'<url><loc>{url}</loc><lastmod>{now.astimezone(PACIFIC).date()}</lastmod></url></urlset>')
    conf=json.loads((root/'vercel.json').read_text());conf['redirects'] += [{'source':'/blog/'+b['slug']+suffix,'destination':'/blog/'+b['slug']+'.html','permanent':True} for suffix in ['', '/']];outputs['vercel.json']=json.dumps(conf,indent=2)+'\n'
    import xml.etree.ElementTree as ET
    for path in ['feed.xml','sitemap.xml']:ET.fromstring(outputs[path])
    return outputs,{'id':b['id'],'slug':b['slug'],'url':url,'title':b['title'],'datePublished':date,'model':b['model'],'useCase':b['useCase'],'sourceCanonicalUrl':b['sourceCanonicalUrl'],'sourceDedupeKey':digest(b['sourceCanonicalUrl'].encode()),'featuredImage':'https://kongtractors.com'+im,'featuredImageSha256':b['media']['sha256'],'status':'written-awaiting-live-verification'}

def run(root,fetch=get,now=None,only=None):
    now=now or dt.datetime.now(dt.timezone.utc);policy=json.loads((root/'editorial/publisher-policy.json').read_text());checks=check_runtime(root,policy,fetch)
    state=json.loads((root/STATE).read_text()) if (root/STATE).exists() else {'version':1,'published':[],'blocked':{},'excluded':{}}
    before=copy.deepcopy(state);report={'observedAt':now.isoformat(),'trigger':os.getenv('GITHUB_EVENT_NAME','local-preview'),'repository':policy['repository'],'sourceCommit':os.getenv('GITHUB_SHA'),'loadedPolicy':checks,'published':[],'skipped':[],'blocked':[],'excluded':[],'scope':'Reviewed original briefs only; metadata discovery is separate; no paid model calls'}
    history='\n'.join(f.read_text() for f in (root/'blog').glob('*.html'))
    prior=json.loads((root/'operations/curator-publications.json').read_text()).get('publishedOrPending',[])
    sources={x.get('sourceCanonicalUrl',x.get('canonicalSourceUrl')) for x in state['published']+prior};models={(x.get('model'),x.get('useCase')) for x in state['published']+prior}
    already_today=any(dt.datetime.fromisoformat(x['datePublished']).astimezone(PACIFIC).date()==now.astimezone(PACIFIC).date() for x in state['published'])
    outputs={}
    for path in sorted((root/'editorial/briefs').glob('*.json')):
        b=json.loads(path.read_text());key=b.get('id',path.stem)
        if only and key!=only:continue
        if key in state['excluded']:
            report['skipped'].append({'id':key,'reason':'durably-excluded'});continue
        if b.get('sourceCanonicalUrl') in sources or (b.get('model'),b.get('useCase')) in models or ('/blog/'+b.get('slug','')+'.html') in history:
            report['skipped'].append({'id':key,'reason':'already-published'});continue
        if dt.datetime.fromisoformat(b['notBefore'])>now:
            report['skipped'].append({'id':key,'reason':'not-due'});continue
        if already_today:
            report['skipped'].append({'id':key,'reason':'one-new-article-per-Pacific-day'});continue
        blocked=state['blocked'].get(key)
        if blocked and dt.datetime.fromisoformat(blocked['nextAttempt'])>now:
            report['skipped'].append({'id':key,'reason':'blocked-backoff','blocker':blocked['reason']});continue
        try:
            validate_brief(root,b,policy,fetch,now)
            candidate,pub=render(root,b,now)
        except (Rejected,ValueError,KeyError,OSError) as exc:
            reason=str(exc)
            if reason.startswith('EXCLUDED_'):
                row={'id':key,'sourceCanonicalUrl':b.get('sourceCanonicalUrl'),'reason':reason,'excludedAt':now.isoformat()};state['excluded'][key]=row;state['blocked'].pop(key,None);report['excluded'].append(row)
            else:
                row={'id':key,'reason':reason,'observedAt':now.isoformat(),'nextAttempt':(now+dt.timedelta(hours=6)).isoformat()};state['blocked'][key]=row;report['blocked'].append(row)
            continue
        if any(path not in FIXED and path!='blog/'+b['slug']+'.html' for path in candidate):raise Rejected('OUTPUT_PATH_OUTSIDE_CONTRACT')
        outputs.update(candidate);state['published'].append(pub);state['blocked'].pop(key,None);report['published'].append(pub);already_today=True
    if state!=before:outputs[STATE]=json.dumps(state,indent=2)+'\n'
    # All candidate files are built and validated before touching the checkout.
    for path,content in outputs.items():
        dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(content)
    report['changedPaths']=sorted(outputs);report['remainingBlockers']=list(state['blocked'].values());report['pendingLive']=[x for x in state['published'] if x['status']=='written-awaiting-live-verification'];return report

def commit_and_push(root,report):
    paths=report['changedPaths']
    if not paths:return None
    git=lambda *a:subprocess.check_output(['git','-C',str(root),*a],text=True).strip()
    base=git('rev-parse','HEAD');git('fetch','origin','main')
    if git('rev-parse','origin/main')!=base:raise Rejected('MAIN_CHANGED_NO_FORCE_PUSH_RETRY_NEXT_RUN')
    dirty=set(subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True).splitlines())
    expected=set(paths)
    for row in dirty:
        path=row[3:]
        if path not in expected:raise Rejected('UNEXPECTED_WORKTREE_CHANGE:'+path)
    git('config','user.name','Kong Publisher')
    git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add','--',*paths);git('diff','--cached','--check')
    git('commit','-m','Publish reviewed Kong equipment guide' if report['published'] else 'Record Kong publisher blocked or excluded item')
    # The ephemeral native job token is restricted to this repository. It is
    # never saved in git config, source, artifacts or deployment environment.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ask=Path(tmp)/'askpass.sh';ask.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s" "x-access-token";; *) printf "%s" "$GITHUB_TOKEN";; esac\n');ask.chmod(0o700)
        env={**os.environ,'GIT_ASKPASS':str(ask),'GIT_TERMINAL_PROMPT':'0'}
        subprocess.run(['git','-C',str(root),'push','origin','HEAD:main'],env=env,check=True)
    return git('rev-parse','HEAD')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(ROOT));ap.add_argument('--preview-dir');ap.add_argument('--only');ap.add_argument('--push',action='store_true');ap.add_argument('--report',required=True);a=ap.parse_args();root=Path(a.root).resolve()
    if a.preview_dir:
        if a.push:raise SystemExit('Preview cannot push')
        dest=Path(a.preview_dir).resolve()
        if dest.exists():raise SystemExit('Preview directory already exists')
        shutil.copytree(root,dest,ignore=shutil.ignore_patterns('.git','__pycache__'));root=dest
    report={}
    try:
        report=run(root,only=a.only)
        if a.push:
            if os.getenv('GITHUB_ACTIONS')!='true' or not os.getenv('GITHUB_TOKEN'):raise Rejected('PUSH_ONLY_IN_BOUND_NATIVE_WORKFLOW')
            report['publicationCommit']=commit_and_push(root,report)
    except Exception as exc:
        report.update(fatal=str(exc),status='blocked');Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2)+'\n');raise
    report['status']='article-written' if report.get('published') else ('blocked-items-retained' if report.get('remainingBlockers') else 'idle-no-reviewed-new-briefs')
    Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
