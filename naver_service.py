"""NAVER API HUB news and DataLab; credentials remain server-side."""
import os,re,html,time,threading
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import requests
BASE='https://naverapihub.apigw.ntruss.com'
_cache={}; _lock=threading.Lock()

def status():
    return {'configured':bool(os.getenv('NAVER_CLIENT_ID','').strip() and os.getenv('NAVER_CLIENT_SECRET','').strip()),'provider':'NAVER API HUB','ai_required':False}

def headers():
    values=[os.getenv(k,'').strip() for k in ('NAVER_CLIENT_ID','NAVER_CLIENT_SECRET')]
    if not all(values): raise RuntimeError('Render Environment에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하세요.')
    if any(not v.isascii() or any(c.isspace() for c in v) for v in values): raise RuntimeError('네이버 인증값에 한글 또는 공백이 포함되어 있습니다.')
    return {'X-NCP-APIGW-API-KEY-ID':values[0],'X-NCP-APIGW-API-KEY':values[1]}

def call(path,params=None,payload=None):
    key=(path,str(params),str(payload))
    with _lock:
        cached=_cache.get(key)
        if cached and time.monotonic()-cached[0]<600:return cached[1]
    try:
        r=requests.request('POST' if payload is not None else 'GET',BASE+path,headers=headers(),params=params,json=payload,timeout=(5,15))
        if r.status_code!=200:
            hints={401:'Client ID/Secret을 확인하세요.',403:'해당 API의 이용 권한을 확인하세요.',429:'호출 한도를 초과했습니다. 잠시 후 다시 조회하세요.'}
            raise RuntimeError(f'네이버 API HTTP {r.status_code} · '+hints.get(r.status_code,'서비스 응답 오류입니다.'))
        data=r.json()
    except requests.RequestException:raise RuntimeError('네이버 API 연결 실패 또는 시간 초과') from None
    except ValueError:raise RuntimeError('네이버 API 응답을 해석할 수 없습니다.') from None
    with _lock:
        if len(_cache)>500:_cache.clear()
        _cache[key]=(time.monotonic(),data)
    return data

def clean(s):return html.unescape(re.sub(r'<[^>]*>','',str(s or '')))
def safe_link(s):
    u=urlparse(str(s or ''))
    return str(s) if u.scheme in ('https','http') and u.hostname and not u.username else ''
def parse_news(body,query):
    items=[];seen=set()
    for r in body.get('items',[]):
        title=clean(r.get('title'));link=safe_link(r.get('originallink')) or safe_link(r.get('link'))
        if not link or not title or link in seen:continue
        seen.add(link)
        try:dt=parsedate_to_datetime(r.get('pubDate','')).astimezone(ZoneInfo('Asia/Seoul')); stamp=dt.timestamp();date=dt.isoformat()
        except (ValueError,TypeError):stamp=0;date=''
        text=title+' '+clean(r.get('description'))
        tags=[label for label,words in [('수주·계약',['수주','계약']),('실적',['실적','영업이익','매출']),('투자·증설',['증설','투자','공장']),('리스크',['적자','횡령','유상증자','소송','하락'])] if any(w in text for w in words)]
        items.append({'title':title,'description':clean(r.get('description')),'url':link,'source':urlparse(link).hostname,'published_at':date,'timestamp':stamp,'query':query,'tags':tags,'tag_basis':'제목·검색 설명의 단어 일치'})
    return sorted(items,key=lambda x:x['timestamp'],reverse=True)

def news(query,limit=30):
    query=query.strip()
    if not query or len(query)>100:raise ValueError('검색어는 1~100자로 입력하세요.')
    body=call('/search/v1/news',params={'query':query,'display':min(100,max(1,limit)),'start':1,'sort':'date','format':'json'})
    return {'items':parse_news(body,query),'query':query,'total':body.get('total',0),'source':'NAVER API HUB','checked_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')}

def leader_news(rows):
    from concurrent.futures import ThreadPoolExecutor,as_completed
    items=[];errors=[]
    names=list(dict.fromkeys(x['name'] for x in rows if x.get('name')))[:20]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(news,name,5):name for name in names}
        for future in as_completed(futures):
            try:
                data=future.result()
                for article in data['items']: article={**article,'stock':futures[future]};items.append(article)
            except Exception as e:errors.append({'stock':futures[future],'error':str(e)})
    unique={}
    for article in sorted(items,key=lambda x:x['timestamp'],reverse=True):
        if article['url'] not in unique:unique[article['url']]=article
    return {'items':list(unique.values()),'errors':errors,'queried_stocks':names,'ok':bool(items) or not errors,'source':'KRX TOP20 종목명 → NAVER 뉴스 검색'}

def market_scan(rows):
    """Combine KRX leader scores with recent NAVER news signals; no LLM required."""
    rows=[r for r in rows if r.get('name')][:12]
    if not rows: raise ValueError('KRX 데이터 새로고침으로 주도주 후보를 먼저 조회하세요.')
    result=leader_news(rows)
    grouped={r['name']:[] for r in rows}
    for article in result.get('items',[]):
        if article.get('stock') in grouped: grouped[article['stock']].append(article)
    candidates=[]
    for r in rows:
        articles=grouped.get(r['name'],[])
        tags=list(dict.fromkeys(tag for a in articles for tag in a.get('tags',[])))
        krx_score=float(r.get('score') or 0)
        news_score=min(100,len(articles)*20)
        signal=round(krx_score*.7+news_score*.3,1)
        candidates.append({
            'name':r['name'],'ticker':r.get('ticker'),'sector':r.get('sector') or '기타',
            'signal_score':signal,'krx_score':krx_score,'news_count':len(articles),
            'reason':f"KRX 거래대금·등락률 후보점수 {krx_score:g}점, 최신 기사 {len(articles)}건 확인",
            'catalyst':articles[0]['title'] if articles else '최근 네이버 검색 기사 없음',
            'tags':tags,'articles':articles[:3],
            'price':r.get('close'),'change_pct':r.get('change'),'turnover_krw':r.get('amount'),
            'data_note':'가격·등락률·거래대금은 KRX, 기사 모멘텀은 NAVER 검색 결과 기준',
        })
    candidates.sort(key=lambda x:x['signal_score'],reverse=True)
    sectors={}
    for c in candidates:
        s=sectors.setdefault(c['sector'],{'sector':c['sector'],'scores':[],'leaders':[],'news_count':0})
        s['scores'].append(c['signal_score']);s['leaders'].append(c['name']);s['news_count']+=c['news_count']
    sector_rows=[]
    for s in sectors.values():
        sector_rows.append({'sector':s['sector'],'strength':round(sum(s['scores'])/len(s['scores']),1),
            'reason':f"후보 {len(s['leaders'])}개 · 기사 {s['news_count']}건 · 대표 {', '.join(s['leaders'][:3])}"})
    sector_rows.sort(key=lambda x:x['strength'],reverse=True)
    top=sector_rows[0]['sector'] if sector_rows else '확인 중'
    return {'as_of':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='minutes'),
        'market_summary':f"KRX 후보점수와 네이버 최신 기사량을 결합한 결과, {top} 섹터의 신호가 가장 높습니다.",
        'sectors':sector_rows[:8],'candidates':candidates,'source_urls':[a['url'] for a in result.get('items',[])[:30]],
        'errors':result.get('errors',[]),'source':'KRX 공식 일별 데이터 + NAVER API HUB 뉴스','method':'KRX 70% + 네이버 기사량 30%'}

def trends(names):
    names=list(dict.fromkeys(n.strip() for n in names if n.strip()))
    if not 1<=len(names)<=5 or any(len(n)>50 for n in names):raise ValueError('비교 종목은 1~5개, 각 50자 이내로 입력하세요.')
    end=datetime.now(ZoneInfo('Asia/Seoul')).date()-timedelta(days=1);start=end-timedelta(days=29)
    body=call('/search-trend/v1/search',payload={'startDate':start.isoformat(),'endDate':end.isoformat(),'timeUnit':'date','keywordGroups':[{'groupName':n,'keywords':[n]} for n in names]})
    return {'results':body.get('results',[]),'start':start.isoformat(),'end':end.isoformat(),'note':'동일 요청 내 상대 검색 관심도입니다. 실제 검색 횟수나 투자자 수급이 아닙니다.'}
