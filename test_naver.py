import os,unittest
from unittest.mock import patch,Mock
import naver_service as n
class NaverTests(unittest.TestCase):
 def setUp(self):n._cache.clear()
 def test_news_parse_safety_dedup_date(self):
  r={'title':'<b>삼성전자</b> 실적 &amp; 수주','description':'영업이익','originallink':'https://example.com/a','pubDate':'Thu, 01 Oct 2026 10:00:00 +0900'}
  items=n.parse_news({'items':[r,r,{**r,'originallink':'javascript:alert(1)'}]},'삼성전자')
  self.assertEqual(len(items),1);self.assertEqual(items[0]['title'],'삼성전자 실적 & 수주');self.assertIn('실적',items[0]['tags'])
 def test_hub_headers_cache(self):
  response=Mock(status_code=200);response.json.return_value={'items':[]}
  with patch.dict(os.environ,{'NAVER_CLIENT_ID':'testid','NAVER_CLIENT_SECRET':'testsecret'}),patch.object(n.requests,'request',return_value=response) as request:
   n.news('삼성전자');n.news('삼성전자');self.assertEqual(request.call_count,1)
   args=request.call_args;self.assertIn('/search/v1/news',args.args[1]);self.assertEqual(args.kwargs['headers']['X-NCP-APIGW-API-KEY'],'testsecret')
 def test_auth_failure_no_secret_leak(self):
  response=Mock(status_code=401)
  with patch.dict(os.environ,{'NAVER_CLIENT_ID':'testid','NAVER_CLIENT_SECRET':'testsecret'}),patch.object(n.requests,'request',return_value=response):
   with self.assertRaisesRegex(RuntimeError,'401'):n.news('주식')
 def test_trend_validation_and_payload(self):
  with self.assertRaises(ValueError):n.trends(['a','b','c','d','e','f'])
  with patch.object(n,'call',return_value={'results':[]}) as call:
   n.trends(['삼성전자','삼성전자','SK하이닉스']);payload=call.call_args.kwargs['payload'];self.assertEqual(len(payload['keywordGroups']),2);self.assertEqual(payload['timeUnit'],'date')
 def test_partial_leaders(self):
  def fake(q,limit):
   if q=='B':raise RuntimeError('연결 실패')
   return {'items':[{'url':'https://example.com','timestamp':1,'title':'A'}]}
  with patch.object(n,'news',side_effect=fake):
   result=n.leader_news([{'name':'A'},{'name':'B'}]);self.assertEqual(len(result['items']),1);self.assertEqual(len(result['errors']),1)
 def test_market_scan_combines_krx_and_news(self):
  article={'stock':'A','title':'A 수주 계약','url':'https://example.com/a','tags':['수주·계약']}
  rows=[{'name':'A','ticker':'000001','sector':'방산','score':80,'close':1000,'change':2,'amount':100000000}]
  with patch.object(n,'leader_news',return_value={'items':[article],'errors':[]}):
   result=n.market_scan(rows)
  self.assertEqual(result['candidates'][0]['signal_score'],62)
  self.assertEqual(result['sectors'][0]['sector'],'방산')
  self.assertEqual(result['source'],'KRX 공식 일별 데이터 + NAVER API HUB 뉴스')
if __name__=='__main__':unittest.main()
