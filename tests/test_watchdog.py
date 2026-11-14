import unittest,importlib.util
from pathlib import Path
from datetime import datetime,timezone,timedelta
p=Path(__file__).resolve().parents[1]/'api/publishing-watchdog.py';spec=importlib.util.spec_from_file_location('wd',p);wd=importlib.util.module_from_spec(spec);spec.loader.exec_module(wd)
class Watchdog(unittest.TestCase):
 def setUp(self):self.now=datetime(2026,11,14,2,20,tzinfo=timezone.utc)
 def runs(self,minutes=10,conclusion='success'):
  return {'workflow_runs':[{'id':1,'event':'schedule','created_at':(self.now-timedelta(minutes=minutes)).isoformat(),'status':'completed','conclusion':conclusion,'html_url':'https://github.com/SHTFTV/kongtractors.com/actions/runs/1','head_sha':'a'*40}]}
 def test_fresh_idle_execution_does_not_claim_new_article(self):
  r=wd.evaluate(self.runs(),{'published':[]},self.now);self.assertEqual(r['status'],'healthy');self.assertIsNone(r['latestVerifiedPublication']);self.assertFalse(r['automaticResearchAuthorConfigured']);self.assertFalse(r['ownerDeliveryVerified'])
 def test_schedule_gap_is_detected_independently(self):
  r=wd.evaluate(self.runs(108),{'published':[]},self.now);self.assertEqual(r['status'],'held');self.assertIn('native-schedule-stale',r['failures'])
 def test_a_failed_schedule_is_not_a_success(self):self.assertIn('native-schedule-failed',wd.evaluate(self.runs(conclusion='failure'),{},self.now)['failures'])
 def test_controlled_canary_cannot_be_mistaken_for_actual_incident(self):
  r=wd.evaluate(self.runs(),{},self.now,'stale-schedule');self.assertTrue(r['synthetic']);self.assertTrue(r['incident']['synthetic']);self.assertIn('controlled',r['incident']['id'])
 def test_missing_schedule_remains_missing(self):self.assertIn('native-schedule-never-observed',wd.evaluate({'workflow_runs':[]},{},self.now)['failures'])
 def test_pending_release_remains_pending(self):self.assertIn('publication-awaiting-live-verification',wd.evaluate(self.runs(),{'published':[{'status':'written-awaiting-live-verification'}]},self.now)['failures'])
if __name__=='__main__':unittest.main()
