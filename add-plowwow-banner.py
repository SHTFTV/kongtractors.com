from pathlib import Path
import json
r=Path(__file__).parent
ad='''<aside class="kw-wow" aria-label="PlowWow snow removal marketing advertisement"><div class="kw-wow-inner"><img src="/assets/plowwow-mascot.webp" alt="Wow, the PlowWow snow removal mascot, waving with a shovel" width="140" height="150" loading="lazy"><div><p class="kw-wow-label">ADVERTISEMENT · PLOWWOW</p><h2>You handle the snow.<br>Let Wow make some noise.</h2><p class="kw-wow-copy">Snow removal contractor? Put your business in front of property owners with PlowWow snow removal marketing. Explore working with Wow and building seasonal routes.</p></div><a class="kw-wow-link" href="https://www.plowwow.com/contractor-apply">WORK WITH WOW <span aria-hidden="true">↗</span></a></div></aside>'''
files=[]
for p in sorted(r.rglob('*.html')):
 s=p.read_text()
 if 'class="kw-wow"' in s:continue
 s=s.replace('</head>','<link rel="stylesheet" href="/kong-plowwow.css"></head>',1)
 if '<footer' in s:s=s.replace('<footer',ad+'<footer',1)
 else:s=s.replace('</body>',ad+'</body>',1)
 p.write_text(s);files.append(str(p.relative_to(r)))
(r/'plowwow-banner-files.json').write_text(json.dumps(files))
print(len(files))
