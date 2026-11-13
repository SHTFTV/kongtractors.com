"""Behavioral tests against isolated repository copies; no production writes."""
import subprocess
import copy,datetime as dt,importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('kong_writer',ROOT/'scripts/kong_publisher/publish.py');writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(writer)
class PublisherTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'repo';shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('.git','__pycache__'))
  self.now=dt.datetime(2026,11,13,20,0,tzinfo=dt.timezone.utc);self.path=self.root/'editorial/briefs/ditch-witch-sk800.json';self.brief=json.loads(self.path.read_text())
  self.policy=json.loads((self.root/'editorial/publisher-policy.json').read_text());self.register={'version':self.policy['sharedPreflight']['version'],'cases':[]};self.policy['sharedPreflight']['canonicalJsonSha256']=writer.stable(self.register);self.save_policy()
 def tearDown(self):self.tmp.cleanup()
 def save_policy(self):(self.root/'editorial/publisher-policy.json').write_text(json.dumps(self.policy))
 def save(self,b=None):self.path.write_text(json.dumps(b or self.brief))
 def fetch(self,url):
  if url==self.policy['sharedPreflight']['url']:return json.dumps(self.register).encode()
  for s in self.brief['sources']:
   if s['url']==url:
    if s['type']=='pdf':return b'%PDF-fixture'
    return ('<html><body>'+' '.join(s.get('requiredText',[]))+'</body></html>').encode()
  return b'<html>SK800 landscape rental</html>'
 def fixtures(self):
  self.brief['review']['desktopPhoneVisualCheck']='passed'
  for s in self.brief['sources']:
   if s['type']=='pdf':s['sha256']=writer.digest(b'%PDF-fixture')
  self.save()
 def run_writer(self,fetch=None,now=None):return writer.run(self.root,fetch or self.fetch,now or self.now)
 def test_writer_emits_article_and_all_discovery_outputs_then_deduplicates(self):
  self.fixtures();r=self.run_writer();self.assertEqual(len(r['published']),1);pub=r['published'][0]
  for path in ['blog/'+self.brief['slug']+'.html','index.html','blog/index.html','feed.xml','sitemap.xml']:
   self.assertIn(pub['url'] if path.endswith('.xml') else self.brief['title'],(self.root/path).read_text())
  self.assertEqual(self.run_writer()['changedPaths'],[])
 def test_blocked_item_does_not_stall_other_brief(self):
  self.fixtures();bad=copy.deepcopy(self.brief);bad.update(id='blocked-fixture',slug='blocked-test-fixture',sourceCanonicalUrl='https://www.ditchwitch.com/blocked-fixture/');bad['sources'][0]['url']=bad['sourceCanonicalUrl'];(self.root/'editorial/briefs/000-blocked.json').write_text(json.dumps(bad))
  def fetch(u):
   if '/blocked-fixture/' in u:raise writer.Rejected('SOURCE_FETCH_FAILED_FIXTURE')
   return self.fetch(u)
  r=self.run_writer(fetch);self.assertEqual(len(r['blocked']),1);self.assertEqual(len(r['published']),1);self.assertIn('blocked-fixture',json.loads((self.root/writer.STATE).read_text())['blocked'])
 def test_source_failure_then_success_clears_persistent_blocker(self):
  self.fixtures()
  def fail(u):
   if u==self.brief['sourceCanonicalUrl']:raise writer.Rejected('SOURCE_TEMPORARILY_DOWN')
   return self.fetch(u)
  self.assertEqual(len(self.run_writer(fail)['blocked']),1);self.assertEqual(self.run_writer()['published'],[])
  r=self.run_writer(now=self.now+dt.timedelta(hours=7));self.assertEqual(len(r['published']),1);self.assertEqual(r['remainingBlockers'],[])
 def test_paid_disclosure_is_durable_and_never_rescued(self):
  self.fixtures()
  def paid(u):
   if u==self.brief['sourceCanonicalUrl']:return b'<article>SK800 landscape rental. Paid partnership.</article>'
   return self.fetch(u)
  r=self.run_writer(paid);self.assertEqual(len(r['excluded']),1);self.assertEqual(r['published'],[]);self.assertEqual(self.run_writer()['published'],[]);self.assertEqual(self.run_writer()['skipped'][0]['reason'],'durably-excluded')
 def test_incomplete_review_cannot_publish(self):
  self.fixtures();self.brief['review']['desktopPhoneVisualCheck']='pending';self.save();self.assertEqual(self.run_writer()['published'],[])
 def test_changed_image_is_blocked_before_site_files_written(self):
  self.fixtures();path=self.root/self.brief['media']['path'];path.write_bytes(path.read_bytes()+b'changed');before=(self.root/'index.html').read_bytes();r=self.run_writer();self.assertEqual(r['published'],[]);self.assertEqual(before,(self.root/'index.html').read_bytes())
 def test_shared_policy_change_fails_closed(self):
  self.register['version']='unexpected';self.assertRaises(writer.Rejected,self.run_writer)
 def test_exact_kong_rejection_remains_held(self):
  self.register['cases']=[{'site':'kongtractors.com','operation':'unattended_repository_write','state':'rejected-held','id':'fixture-held'}];self.policy['sharedPreflight']['canonicalJsonSha256']=writer.stable(self.register);self.save_policy();self.assertRaises(writer.Rejected,self.run_writer)
 def test_code_change_requires_reviewed_manifest(self):
  f=self.root/'scripts/kong_publisher/publish.py';f.write_text(f.read_text()+'\n# changed\n');self.assertRaises(writer.Rejected,self.run_writer)
 def test_one_article_per_pacific_day(self):
  self.fixtures();b=copy.deepcopy(self.brief);b.update(id='second-fixture',slug='second-test-fixture',model='fixture-model',useCase='fixture-only',sourceCanonicalUrl='https://www.ditchwitch.com/second-fixture/');b['sources'][0]['url']=b['sourceCanonicalUrl'];(self.root/'editorial/briefs/zzz-second.json').write_text(json.dumps(b));r=self.run_writer();self.assertEqual(len(r['published']),1);self.assertTrue(any(s['reason']=='one-new-article-per-Pacific-day' for s in r['skipped']))
 def git_fixture(self):
  git=lambda *args:subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True,text=True)
  remote=Path(self.tmp.name)/'remote.git';subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
  git('init','-b','main');git('config','user.name','Test Fixture');git('config','user.email','fixture@example.invalid');git('add','.');git('commit','-m','fixture baseline');git('remote','add','origin',str(remote));git('push','-u','origin','main');return git,remote
 def test_fixed_output_commit_and_fast_forward_push(self):
  self.fixtures();git,remote=self.git_fixture();r=self.run_writer();sha=writer.commit_and_push(self.root,r);self.assertEqual(git('rev-parse','HEAD').stdout.strip(),sha);self.assertEqual(git('rev-parse','origin/main').stdout.strip(),sha);self.assertEqual(git('status','--porcelain').stdout,'')
 def test_concurrent_main_change_is_not_overwritten(self):
  self.fixtures();git,remote=self.git_fixture();peer=Path(self.tmp.name)/'peer';subprocess.run(['git','clone','-b','main',str(remote),str(peer)],check=True,capture_output=True)
  for args in [('config','user.name','Peer Fixture'),('config','user.email','peer@example.invalid')]:subprocess.run(['git','-C',str(peer),*args],check=True,capture_output=True)
  (peer/'peer.txt').write_text('concurrent change')
  for args in [('add','peer.txt'),('commit','-m','peer change'),('push','origin','main')]:subprocess.run(['git','-C',str(peer),*args],check=True,capture_output=True)
  r=self.run_writer();self.assertRaises(writer.Rejected,writer.commit_and_push,self.root,r);self.assertNotEqual(git('rev-parse','HEAD').stdout,git('rev-parse','origin/main').stdout)
if __name__=='__main__':unittest.main()
