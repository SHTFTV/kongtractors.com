"""Verify committed article outputs on the production domain; retain pending on failure."""
import argparse,datetime as dt,hashlib,json,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
from playwright.sync_api import sync_playwright
from publish import commit_and_push, STATE

def check(root,report,out,browser_path=None):
    out.mkdir(parents=True,exist_ok=True);results=[]
    targets={x['url']:x for x in report.get('pendingLive',report.get('published',[]))}.values()
    with sync_playwright() as p:
        launch={'headless':True}
        if browser_path:launch['executable_path']=browser_path
        browser=p.chromium.launch(**launch)
        ctx=browser.new_context()
        for pub in targets:
            url=pub['url'];last=None
            # Existing Vercel Git integration needs time to deploy the writer commit.
            for attempt in range(60):
                try:
                    r=ctx.request.get(url,timeout=20000)
                    if r.status==200 and pub['title'] in r.text():break
                    last='HTTP '+str(r.status)
                except Exception as exc:last=str(exc)
                time.sleep(5)
            else:raise RuntimeError('LIVE_ARTICLE_UNVERIFIED: '+str(last))
            im=ctx.request.get(pub['featuredImage']);assert im.status==200
            assert hashlib.sha256(im.body()).hexdigest()==pub['featuredImageSha256']
            record={'url':url,'httpStatus':r.status,'imageBytesMatch':True,'viewports':[]}
            for w in [1280,390]:
                page=ctx.new_page(viewport={'width':w,'height':900});page.goto(url);page.wait_for_load_state('networkidle')
                data=page.evaluate('''()=>({canonical:document.querySelector('link[rel=canonical]').href,schema:JSON.parse(document.querySelector('script[type="application/ld+json"]').textContent),og:document.querySelector('meta[property="og:image"]').content,twitter:document.querySelector('meta[name="twitter:image"]').content,overflow:document.documentElement.scrollWidth>innerWidth,images:[...document.images].map(i=>({ok:i.complete&&i.naturalWidth>0,src:i.src,w:i.naturalWidth,h:i.naturalHeight}))})''')
                assert data['canonical']==url and data['schema']['datePublished']==pub['datePublished']
                assert data['schema']['image']['url']==data['og']==data['twitter']==pub['featuredImage']
                assert not data['overflow'] and all(i['ok'] for i in data['images'])
                hero=page.locator('.lx-cover');assert hero.get_attribute('src')==pub['featuredImage'].removeprefix('https://kongtractors.com')
                hero.screenshot(path=str(out/f'hero-{w}.png'));page.screenshot(path=str(out/f'article-top-{w}.png'))
                for path,label in [('/','home'),('/blog/','archive')]:
                    page.goto('https://kongtractors.com'+path);card=page.locator('a.kj-card[href="/blog/'+pub['slug']+'.html"]');assert card.count()==1;card.scroll_into_view_if_needed();card.locator('img').evaluate('(i)=>i.loading="eager"');page.wait_for_function('(u)=>[...document.images].filter(i=>i.src===u).every(i=>i.complete&&i.naturalWidth>0)',arg=pub['featuredImage']);page.wait_for_timeout(300)
                    assert card.locator('img').get_attribute('src')==pub['featuredImage'].removeprefix('https://kongtractors.com')
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');card.screenshot(path=str(out/f'{label}-card-{w}.png'))
                record['viewports'].append({'width':w,**data});page.close()
            for path in ['/feed.xml','/sitemap.xml']:
                r=ctx.request.get('https://kongtractors.com'+path);assert r.status==200;ET.fromstring(r.text());assert url in r.text();record[path]={'http':200,'validXml':True,'articlePresent':True}
            for suffix in ['', '/']:
                r=ctx.request.get(url.removesuffix('.html')+suffix);assert r.status==200 and r.url==url
            record['verifiedAt']=dt.datetime.now(dt.timezone.utc).isoformat();results.append(record)
        ctx.close();browser.close()
    return results

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--report',required=True);ap.add_argument('--output',required=True);ap.add_argument('--browser-path');ap.add_argument('--record-live',action='store_true');a=ap.parse_args();root=Path(a.root).resolve();report=json.loads(Path(a.report).read_text());out=Path(a.output);results=check(root,report,out,a.browser_path);(out/'live-verification.json').write_text(json.dumps(results,indent=2)+'\n')
    if a.record_live and results:
        state=json.loads((root/STATE).read_text());byurl={r['url']:r for r in results}
        for pub in state['published']:
            if pub['url'] in byurl:pub.update(status='live-verified',verifiedAt=byurl[pub['url']]['verifiedAt'],publicationCommit=report.get('publicationCommit'))
        (root/STATE).write_text(json.dumps(state,indent=2)+'\n');report['changedPaths']=[STATE];report['liveEvidenceCommit']=commit_and_push(root,report)
    print(json.dumps({'liveArticles':[r['url'] for r in results],'verified':True}),flush=True)
if __name__=='__main__':main()
