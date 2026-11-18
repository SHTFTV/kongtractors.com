"""Verify committed article outputs on the production domain; retain pending on failure."""
import argparse,datetime as dt,hashlib,json,time,subprocess,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from publish import commit_and_push, STATE

def check_targets(root,report,out,browser_path=None,base='https://kongtractors.com',preview=False):
    out.mkdir(parents=True,exist_ok=True);results=[]
    targets={x['url']:x for x in (report.get('previewCandidates',[]) if preview else report.get('pendingLive',report.get('published',[])))}.values()
    with sync_playwright() as p:
        launch={'headless':True}
        if browser_path:launch['executable_path']=browser_path
        browser=p.chromium.launch(**launch)
        ctx=browser.new_context()
        for pub in targets:
            canonical=pub['url'];url=base+urlsplit(canonical).path;image_url=base+urlsplit(pub['featuredImage']).path;last=None
            # Existing Vercel Git integration needs time to deploy the writer commit.
            for attempt in range(60):
                try:
                    r=ctx.request.get(url,timeout=20000)
                    if r.status==200 and pub['title'] in r.text():break
                    last='HTTP '+str(r.status)
                except Exception as exc:last=str(exc)
                time.sleep(5)
            else:raise RuntimeError('LIVE_ARTICLE_UNVERIFIED: '+str(last))
            im=ctx.request.get(image_url);assert im.status==200
            assert hashlib.sha256(im.body()).hexdigest()==pub['featuredImageSha256']
            record={'url':canonical,'observedUrl':url,'previewOnly':preview,'httpStatus':r.status,'imageBytesMatch':True,'viewports':[]}
            for w in [1280,390]:
                page=ctx.new_page();page.set_viewport_size({'width':w,'height':900});page.goto(url);page.wait_for_load_state('networkidle')
                data=page.evaluate('''()=>({canonical:document.querySelector('link[rel=canonical]').href,schema:JSON.parse(document.querySelector('script[type="application/ld+json"]').textContent),title:document.querySelector('h1').innerText,description:document.querySelector('meta[name="description"]').content,ogTitle:document.querySelector('meta[property="og:title"]').content,ogDescription:document.querySelector('meta[property="og:description"]').content,ogUrl:document.querySelector('meta[property="og:url"]').content,twitterTitle:document.querySelector('meta[name="twitter:title"]').content,twitterDescription:document.querySelector('meta[name="twitter:description"]').content,icon:document.querySelector('link[rel="icon"]').href,og:document.querySelector('meta[property="og:image"]').content,twitter:document.querySelector('meta[name="twitter:image"]').content,overflow:document.documentElement.scrollWidth>innerWidth,images:[...document.images].map(i=>({ok:i.complete&&i.naturalWidth>0,src:i.src,w:i.naturalWidth,h:i.naturalHeight}))})''')
                assert data['canonical']==canonical and data['schema']['datePublished']==pub['datePublished']
                assert data['schema']['image']['url']==data['og']==data['twitter']==pub['featuredImage']
                assert data['title']==data['schema']['headline']==data['ogTitle']==data['twitterTitle']==pub['title']
                assert data['description']==data['ogDescription']==data['twitterDescription'] and data['ogUrl']==canonical
                assert urlsplit(data['icon']).path=='/assets/favicon-48.png'
                icon=ctx.request.get(data['icon']);assert icon.status==200 and icon.body().startswith(b'\x89PNG\r\n\x1a\n')
                assert not data['overflow'] and all(i['ok'] for i in data['images'])
                hero=page.locator('.lx-cover');assert hero.get_attribute('src')==pub['featuredImage'].removeprefix('https://kongtractors.com')
                hero.screenshot(path=str(out/f'hero-{w}.png'));page.screenshot(path=str(out/f'article-top-{w}.png'))
                assert page.locator('figcaption').inner_text().strip()
                page.locator('figure').screenshot(path=str(out/f'figure-and-credit-{w}.png'))
                if preview:page.screenshot(path=str(out/f'article-full-{w}.png'),full_page=True)
                for path,label in [('/','home'),('/blog/','archive')]:
                    page.goto(base+path);card=page.locator('a.kj-card[href="/blog/'+pub['slug']+'.html"]');assert card.count()==1;card.scroll_into_view_if_needed();card.locator('img').evaluate('(i)=>i.loading="eager"');page.wait_for_function('(u)=>[...document.images].filter(i=>i.src===u).every(i=>i.complete&&i.naturalWidth>0)',arg=image_url);page.wait_for_timeout(300)
                    assert card.locator('img').get_attribute('src')==pub['featuredImage'].removeprefix('https://kongtractors.com')
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');card.screenshot(path=str(out/f'{label}-card-{w}.png'))
                record['viewports'].append({'width':w,**data});page.close()
            for path in ['/feed.xml','/sitemap.xml']:
                r=ctx.request.get(base+path);assert r.status==200;ET.fromstring(r.text());assert canonical in r.text();record[path]={'http':200,'validXml':True,'articlePresent':True}
            if not preview:
                for suffix in ['', '/']:
                    r=ctx.request.get(url.removesuffix('.html')+suffix);assert r.status==200 and r.url==url
            else:record['productionRedirectsPending']=True
            record['verifiedAt']=dt.datetime.now(dt.timezone.utc).isoformat();results.append(record)
        ctx.close();browser.close()
    return results

def check(root,report,out,browser_path=None,preview=False):
    if not preview:return check_targets(root,report,out,browser_path)
    if report.get('previewOnly') is not True or report.get('published')!=[]:raise RuntimeError('NOT_A_READ_ONLY_PREVIEW_REPORT')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(root)))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:return check_targets(root,report,out,browser_path,'http://127.0.0.1:'+str(server.server_port),True)
    finally:server.shutdown();server.server_close();thread.join(timeout=2)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--report',required=True);ap.add_argument('--output',required=True);ap.add_argument('--browser-path');ap.add_argument('--record-live',action='store_true');ap.add_argument('--preview',action='store_true');a=ap.parse_args();root=Path(a.root).resolve();report=json.loads(Path(a.report).read_text());out=Path(a.output)
    if a.preview and a.record_live:raise SystemExit('Preview cannot record live publication')
    results=check(root,report,out,a.browser_path,a.preview);(out/('preview-verification.json' if a.preview else 'live-verification.json')).write_text(json.dumps(results,indent=2)+'\n')
    if a.preview:
        print(json.dumps({'previewArticles':[r['url'] for r in results],'previewVerified':True,'publicationVerified':False}),flush=True);return
    if a.record_live and results:
        state=json.loads((root/STATE).read_text());byurl={r['url']:r for r in results}
        for pub in state['published']:
            if pub['url'] in byurl:pub.update(status='live-verified',verifiedAt=byurl[pub['url']]['verifiedAt'],publicationCommit=report.get('publicationCommit') or subprocess.check_output(['git','-C',str(root),'log','-1','--format=%H','--','blog/'+pub['slug']+'.html'],text=True).strip())
        (root/STATE).write_text(json.dumps(state,indent=2)+'\n');report['changedPaths']=[STATE];report['liveEvidence']=True;report['liveEvidenceCommit']=commit_and_push(root,report)
    print(json.dumps({'liveArticles':[r['url'] for r in results],'verified':True}),flush=True)
if __name__=='__main__':main()
