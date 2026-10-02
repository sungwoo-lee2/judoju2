import os, unittest, tempfile
from pathlib import Path
from unittest.mock import patch, Mock
import krx_api as k
class TestKRX(unittest.TestCase):
    def test_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError): k.key()
    def test_header_and_query(self):
        response=Mock(); response.read.return_value=b'{"OutBlock_1":[]}'
        response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        with patch.dict(os.environ, {'KRX_API_KEY':'test'}), patch.object(k,'urlopen',return_value=response) as get:
            self.assertEqual(k.fetch('KOSPI','20261001'),[])
            request=get.call_args.args[0]
            self.assertEqual(request.get_header('Auth_key'),'test')
            self.assertIn('basDd=20261001',request.full_url)
    def test_auth_failure(self):
        with patch.dict(os.environ, {'KRX_API_KEY':'test'}), patch.object(k,'urlopen',side_effect=k.HTTPError('url',403,'Forbidden',{},None)):
            with self.assertRaisesRegex(RuntimeError,'403'): k.fetch('KOSDAQ','20261001')
    def test_actual_numbers_and_no_fake_flow(self):
        r={'BAS_DD':'20261001','ISU_CD':'005930','ISU_NM':'삼성전자','TDD_CLSPRC':'70,000','ACC_TRDVAL':'100000000','FLUC_RT':'1.20','ACC_TRDVOL':'100'}
        with tempfile.TemporaryDirectory() as d, patch.object(k,'CACHE',Path(d)/'snap.json'), patch.object(k,'collect',return_value=('20261001',{'KOSPI':[r],'KOSDAQ':[]})):
            snap=k.scan(); x=snap['items'][0]
            self.assertEqual(x['close'],70000); self.assertEqual(x['amount'],100000000)
            self.assertFalse(x['flow_available']); self.assertNotIn('foreign_net_5d',x)
            self.assertEqual(k.snapshot()['as_of'],'20261001')
if __name__=='__main__': unittest.main()
