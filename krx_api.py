"""Authenticated KRX daily market data; no sample or invented price fallback."""
import os, json, math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

BASE = 'https://data-dbg.krx.co.kr/svc/apis/sto/'
MARKETS = {'KOSPI': 'stk_bydd_trd', 'KOSDAQ': 'ksq_bydd_trd'}
CACHE = Path(__file__).parent / 'data' / 'krx_snapshot.json'

def key():
    value = os.getenv('KRX_API_KEY', '').strip()
    if not value:
        raise RuntimeError('Render Environment에 KRX_API_KEY를 설정하세요.')
    if not value.isascii() or any(c.isspace() for c in value):
        raise RuntimeError('KRX_API_KEY에 한글 또는 공백이 포함되어 있습니다.')
    return value

def fetch(market, day):
    request = Request(BASE + MARKETS[market] + '?' + urlencode({'basDd':day}), headers={'AUTH_KEY':key()})
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read()
    except HTTPError as e:
        raise RuntimeError(f'{market}: KRX HTTP {e.code} — 인증키와 해당 API 이용승인을 확인하세요.') from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError(f'{market}: KRX 연결 실패 또는 시간 초과') from None
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise RuntimeError(f'{market}: KRX가 JSON이 아닌 응답을 반환했습니다.') from None
    if not isinstance(body, dict) or not isinstance(body.get('OutBlock_1'), list):
        raise RuntimeError(f'{market}: OutBlock_1 응답 없음 — API 이용승인을 확인하세요.')
    return body['OutBlock_1']

def number(value):
    if value is None or str(value).strip() in ('', '-', '--'):
        return None
    n = float(str(value).replace(',', ''))
    return n if math.isfinite(n) else None

def collect():
    key()
    today = datetime.now(ZoneInfo('Asia/Seoul')).date()
    # Completed daily data only, bounded lookback for long holidays.
    for back in range(1, 15):
        day = (today-timedelta(days=back)).strftime('%Y%m%d')
        if (today-timedelta(days=back)).weekday() >= 5:
            continue
        from krx_history import cached_fetch
        frames = {m: cached_fetch(m, day) for m in MARKETS}
        if all(frames.values()):
            return day, frames
        if any(frames.values()):
            raise RuntimeError(f'{day}: 한 시장만 응답했습니다. 두 시장 데이터가 모두 준비된 후 다시 시도하세요.')
    raise RuntimeError('최근 14일 내 두 시장의 일별 데이터가 없습니다.')

def scan(universe_size=80):
    def guess_sector(name):
        return '미분류'
    day, frames = collect()
    rows=[]
    for market, records in frames.items():
        for r in records:
            if str(r.get('BAS_DD', '')).replace('-', '') != day:
                raise RuntimeError('KRX 응답 기준일이 요청일과 다릅니다.')
            close, amount, change = [number(r.get(k)) for k in ('TDD_CLSPRC','ACC_TRDVAL','FLUC_RT')]
            if close is None or amount is None or change is None or close <= 0 or amount <= 0:
                continue
            ticker=str(r.get('ISU_CD',''))
            name=str(r.get('ISU_NM', ticker))
            rows.append(dict(ticker=ticker, name=name, market=market, sector=guess_sector(name), close=close,
                amount=amount, change=change, volume=number(r.get('ACC_TRDVOL')), market_cap=number(r.get('MKTCAP')),
                as_of=day, flow_available=False, stage='일별 후보', parts={},
                reasons=['공식 일별 거래대금 순위 70% + 등락률 순위 30%', '수급·20일 추세·52주 고점은 미반영']))
    from krx_history import indicators, build_index
    history_index=build_index(day)
    for row in rows:
        row.update(indicators(row['market'], row['ticker'], day, history_index))
    if not rows:
        raise RuntimeError('KRX 응답에 유효한 가격·거래대금이 없습니다.')
    # Score across the full universe, then apply the requested high-turnover pool.
    for field, weight in [('amount',70), ('change',30)]:
        ordered=sorted(rows, key=lambda x:x[field])
        n=len(ordered)
        start=0
        while start<n:
            end=start+1
            while end<n and ordered[end][field]==ordered[start][field]: end+=1
            percentile=((start+end-1)/2)/(n-1) if n>1 else .5
            for x in ordered[start:end]: x['score']=x.get('score',0)+weight*percentile
            start=end
    rows=sorted(rows,key=lambda x:x['amount'],reverse=True)[:max(20,min(int(universe_size),1000))]
    rows.sort(key=lambda x:x['score'], reverse=True)
    for i,r in enumerate(rows): r.update(rank=i+1,score=round(r['score'],1))
    snap=dict(items=rows[:20], sectors=[], early_leaders=[dict(r,early_rank=i+1,early_score=r['score'],early_stage='가격·거래대금 후보') for i,r in enumerate([r for r in rows if r.get('amount_ratio',0)>=1.5 and r.get('ma20_rising') and r['close']>r.get('ma20',float('inf'))][:12])], pullbacks=[], lifecycle=[], rotations=[], performance={},
        changes={'entered':[],'exited':[]}, source=f'KRX 공식 API · 기준일 {day} · 일별 후보점수', as_of=day,
        flow_status='외국인·기관 수급 미제공 | 이동평균·거래대금 배수는 저장된 과거 데이터로 계산 (원종가) | 후보점수는 거래대금70%+등락률30%',
        updated_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'))
    CACHE.parent.mkdir(exist_ok=True)
    tmp=CACHE.with_suffix('.tmp'); tmp.write_text(json.dumps(snap,ensure_ascii=False),encoding='utf-8'); tmp.replace(CACHE)
    return snap

def snapshot():
    if CACHE.exists():
        try: return json.loads(CACHE.read_text(encoding='utf-8'))
        except (ValueError,OSError): pass
    return dict(items=[],sectors=[],early_leaders=[],source='KRX 데이터 조회 전',flow_status='데이터 새로고침을 누르세요.',updated_at=None)

def diagnostics():
    try:
        day,frames=collect()
        components={m:{'ok':True,'latest_day':day,'rows':len(rs)} for m,rs in frames.items()}
        return dict(overall=True,components=components,summary='KRX 공식 일별 API 연결 정상')
    except RuntimeError as e:
        return dict(overall=False,components={'price_turnover':{'ok':False,'error':str(e)}})
