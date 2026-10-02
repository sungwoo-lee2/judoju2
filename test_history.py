import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import krx_history as h
class HistoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(h,'DB',Path(self.tmp.name)/'test.db');self.p.start()
 def tearDown(self): self.p.stop();self.tmp.cleanup()
 def test_cache_and_validation(self):
  r={'BAS_DD':'20260901','ISU_CD':'A'}
  with patch('krx_api.fetch',return_value=[r]) as f:
   h.cached_fetch('KOSPI','20260901');h.cached_fetch('KOSPI','20260901');self.assertEqual(f.call_count,1)
  with patch('krx_api.fetch',return_value=[r]):
   with self.assertRaises(RuntimeError):h.cached_fetch('KOSPI','20260902')
 def test_ma_and_prior_turnover(self):
  with h.connect() as c:
   for i in range(1,22):
    r={'ISU_CD':'A','TDD_CLSPRC':str(i),'ACC_TRDVAL':str(200 if i==21 else 100)}
    c.execute('INSERT INTO days VALUES(?,?,?)',('KOSPI',f'202609{i:02}',json.dumps([r])))
  x=h.indicators('KOSPI','A','20260921',h.build_index('20260921'))
  self.assertEqual(x['ma10'],16.5);self.assertEqual(x['ma20'],11.5);self.assertEqual(x['amount_ratio'],2);self.assertTrue(x['ma20_rising'])
  self.assertNotIn('ma10',h.indicators('KOSPI','missing','20260921'))
 def test_range_validation(self):
  with self.assertRaises(ValueError):list(h.dates('2009-01-01','2010-01-05'))
  self.assertEqual(list(h.dates('2026-09-04','2026-09-07')),['20260907','20260904'])
 def test_auto_range_covers_52_week_indicator(self):
  a,b=h.auto_range()
  self.assertEqual((h.date.fromisoformat(b)-h.date.fromisoformat(a)).days,400)
if __name__=='__main__':unittest.main()
