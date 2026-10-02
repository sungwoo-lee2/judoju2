from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

from sample_data import SAMPLE
from scoring import score_stock, score_early_leader
from analytics_v7 import build_pullbacks, update_history

BASE = Path(__file__).resolve().parent
SNAPSHOT = BASE / 'data' / 'snapshot.json'
PREVIOUS = BASE / 'data' / 'previous_rank.json'

SECTOR_HINTS = {
    '반도체': ['삼성전자','SK하이닉스','DB하이텍','ISC','한미반도체','HPSP','리노공업','제주반도체'],
    '방산': ['한화에어로스페이스','현대로템','LIG넥스원','한화시스템','한국항공우주'],
    '조선': ['한화오션','삼성중공업','HD한국조선해양','HD현대중공업','HD현대미포'],
    '전력': ['HD현대일렉트릭','효성중공업','LS ELECTRIC','산일전기','제룡전기'],
    '2차전지': ['LG에너지솔루션','삼성SDI','에코프로비엠','에코프로','포스코퓨처엠'],
    '바이오': ['삼성바이오로직스','셀트리온','알테오젠','리가켐바이오','HLB'],
    '로봇': ['레인보우로보틱스','두산로보틱스','로보티즈','에스피지','로보스타'],
    '엔터': ['HYBE','하이브','JYP Ent.','에스엠','와이지엔터테인먼트'],
}


def guess_sector(name: str, listed_sector: str | None = None) -> str:
    if listed_sector and str(listed_sector).strip() and str(listed_sector).lower() != 'nan':
        return str(listed_sector).strip()
    for sector, names in SECTOR_HINTS.items():
        if any(k.lower() in name.lower() for k in names):
            return sector
    return '기타'


def _load_previous() -> dict:
    try:
        return json.loads(PREVIOUS.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _load_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT.read_text(encoding='utf-8')) if SNAPSHOT.exists() else {}
    except Exception:
        return {}


def _save_snapshot(items: list, source: str, sectors: list | None = None, flow_status: str = 'unknown', changes: dict | None = None, early_leaders: list | None = None, pullbacks: list | None = None, lifecycle: list | None = None, rotations: list | None = None, performance: dict | None = None):
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'updated_at': datetime.now().isoformat(timespec='seconds'), 'source': source,
        'flow_status': flow_status, 'items': items, 'sectors': sectors or [], 'changes': changes or {'entered':[], 'exited':[]}, 'early_leaders': early_leaders or [], 'pullbacks': pullbacks or [], 'lifecycle': lifecycle or [], 'rotations': rotations or [], 'performance': performance or {}
    }
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    PREVIOUS.write_text(json.dumps({x['ticker']: i+1 for i,x in enumerate(items)}, ensure_ascii=False), encoding='utf-8')


def _sector_strength(rows: list) -> dict:
    groups = {}
    for x in rows:
        s = x.get('sector','기타')
        if s == '기타':
            continue
        groups.setdefault(s, []).append(x)
    raw = {}
    for s, xs in groups.items():
        avg_change = sum(x.get('change',0) for x in xs)/len(xs)
        avg_ratio = sum(min(x.get('amount_ratio',1),3) for x in xs)/len(xs)
        raw[s] = avg_change*0.65 + (avg_ratio-1)*2.0
    if not raw:
        return {}
    lo, hi = min(raw.values()), max(raw.values())
    if hi == lo:
        return {k:0.5 for k in raw}
    return {k:(v-lo)/(hi-lo) for k,v in raw.items()}


def _percentile_scores(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional 0..1 percentile. Keeps negatives below positives naturally."""
    if not values:
        return {}
    s = pd.Series(values, dtype='float64')
    if len(s) == 1:
        return {str(s.index[0]): 0.5}
    ranks = s.rank(method='average', pct=True)
    return {str(k): float(v) for k, v in ranks.items()}


def _investor_table(fromdate: str, todate: str, market: str, investor: str) -> pd.DataFrame:
    from pykrx import stock
    # Current API name. Fall back to legacy alias for older pykrx versions.
    fn = getattr(stock, 'get_market_net_purchases_of_equities_by_ticker', None)
    if fn is None:
        fn = stock.get_market_net_purchases_of_equities
    df = fn(fromdate, todate, market, investor)
    if df is None or df.empty:
        return pd.DataFrame(columns=['순매수거래대금'])
    df.index = df.index.astype(str).str.zfill(6)
    return df


def enrich_investor_flow(rows: list) -> tuple[list, str]:
    """Attach 5-day-ish and 20-day-ish foreign/institution net purchases.

    Four market-wide calls are used, not one request per stock. This keeps refresh practical.
    If KRX/pykrx is unavailable, rows are returned with neutral flow scoring.
    """
    today = datetime.now()
    todate = today.strftime('%Y%m%d')
    from5 = (today - timedelta(days=9)).strftime('%Y%m%d')
    from20 = (today - timedelta(days=35)).strftime('%Y%m%d')

    try:
        frames = {}
        for market in ('KOSPI', 'KOSDAQ'):
            frames[(market,'외국인',5)] = _investor_table(from5, todate, market, '외국인')
            frames[(market,'기관합계',5)] = _investor_table(from5, todate, market, '기관합계')
            frames[(market,'외국인',20)] = _investor_table(from20, todate, market, '외국인')
            frames[(market,'기관합계',20)] = _investor_table(from20, todate, market, '기관합계')

        for x in rows:
            ticker = x['ticker']
            market = x.get('market','KOSPI')
            if market not in ('KOSPI','KOSDAQ'):
                market = 'KOSPI'
            for investor, key in [('외국인','foreign'), ('기관합계','institution')]:
                for days in (5,20):
                    df = frames[(market, investor, days)]
                    try:
                        value = float(df.loc[ticker, '순매수거래대금'])
                    except Exception:
                        value = 0.0
                    x[f'{key}_net_{days}d'] = round(value)
            # Normalize by current daily turnover to avoid automatically favoring mega-caps.
            denom = max(float(x.get('amount',0)), 1.0)
            x['foreign_flow_ratio'] = x['foreign_net_5d'] / (denom * 5.0)
            x['institution_flow_ratio'] = x['institution_net_5d'] / (denom * 5.0)
            x['flow_available'] = True

        f_scores = _percentile_scores({x['ticker']:x['foreign_flow_ratio'] for x in rows})
        i_scores = _percentile_scores({x['ticker']:x['institution_flow_ratio'] for x in rows})
        for x in rows:
            x['foreign_score'] = round(f_scores.get(x['ticker'],0.5), 4)
            x['institution_score'] = round(i_scores.get(x['ticker'],0.5), 4)
        return rows, 'pykrx/KRX 외국인·기관 수급 반영'
    except Exception as e:
        for x in rows:
            x['flow_available'] = False
            x['flow_error'] = str(e)[:180]
        return rows, '수급 조회 실패 → 중립점수 적용'




def _streak(values: list[float]) -> int:
    n = 0
    for v in reversed(values):
        if float(v) > 0:
            n += 1
        else:
            break
    return n


def _daily_flow_table(ticker: str, fromdate: str, todate: str) -> pd.DataFrame:
    """Investor trading value by date for one ticker. pykrx column names vary slightly by version."""
    from pykrx import stock
    fn = getattr(stock, 'get_market_trading_value_by_date', None)
    if fn is None:
        raise RuntimeError('pykrx daily investor-flow API unavailable')
    df = fn(fromdate, todate, ticker)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.sort_index()


def enrich_daily_flow_signals(rows: list, limit: int = 30) -> list:
    """Add daily streak and recent-flow acceleration only to the strongest candidates.

    This intentionally avoids a per-ticker call across the whole KRX universe.
    """
    if not rows or not any(x.get('flow_available') for x in rows):
        return rows
    today = datetime.now()
    fromdate = (today - timedelta(days=24)).strftime('%Y%m%d')
    todate = today.strftime('%Y%m%d')
    for x in rows[:limit]:
        try:
            df = _daily_flow_table(x['ticker'], fromdate, todate)
            if df.empty:
                continue
            foreign_col = next((c for c in ['외국인합계','외국인'] if c in df.columns), None)
            inst_col = next((c for c in ['기관합계','기관'] if c in df.columns), None)
            if not foreign_col or not inst_col:
                continue
            f = pd.to_numeric(df[foreign_col], errors='coerce').fillna(0).tolist()
            i = pd.to_numeric(df[inst_col], errors='coerce').fillna(0).tolist()
            x['foreign_streak'] = _streak(f)
            x['institution_streak'] = _streak(i)
            combined = [a+b for a,b in zip(f,i)]
            recent = sum(combined[-3:]) if len(combined) >= 3 else sum(combined)
            prior = sum(combined[-6:-3]) if len(combined) >= 6 else 0
            denom = max(float(x.get('amount',0))*3.0, 1.0)
            x['recent3_flow'] = round(recent)
            x['prior3_flow'] = round(prior)
            x['flow_acceleration_ratio'] = round((recent-prior)/denom, 4)
            x['flow_surge'] = bool(recent > 0 and (recent-prior)/denom >= 0.04)
        except Exception as e:
            x['daily_flow_error'] = str(e)[:120]
            x.setdefault('foreign_streak', 0)
            x.setdefault('institution_streak', 0)
            x.setdefault('flow_surge', False)
    return rows


def _rank(rows: list, source: str, flow_status: str = 'unknown') -> dict:
    sector_strength = _sector_strength(rows)
    prev_rank = _load_previous()
    prior_snapshot = _load_snapshot()
    prior_items = {x.get('ticker'): x for x in prior_snapshot.get('items', [])}

    scored = []
    for x in rows:
        x = {**x, 'sector_strength': sector_strength.get(x.get('sector','기타'), 0.45)}
        x.setdefault('flow_available', False)
        x.setdefault('ma5_ratio', max(0.94, min(1.06, 1 + (float(x.get('change',0) or 0)/100)*0.35)))
        x.setdefault('ma10_ratio', max(0.92, min(1.08, 1 + (float(x.get('rs20',1) or 1)-1)*0.30)))
        scored.append(score_stock(x))
    scored.sort(key=lambda z: (z['score'], z.get('amount',0)), reverse=True)

    # Only stronger candidates receive the slower per-ticker daily-flow call.
    scored = enrich_daily_flow_signals(scored, limit=min(30, len(scored)))
    rescored = [score_stock(x) for x in scored]
    rescored.sort(key=lambda z: (z['score'], z.get('amount',0)), reverse=True)

    for i, x in enumerate(rescored):
        rank = i+1
        old = prev_rank.get(x['ticker'])
        x['rank'] = rank
        x['rank_change'] = 0 if old is None else old-rank
        prev_item = prior_items.get(x['ticker'])
        prev_flow = ((prev_item or {}).get('parts') or {}).get('수급')
        current_flow = (x.get('parts') or {}).get('수급', 10.0)
        x['flow_score_change'] = None if prev_flow is None else round(current_flow-float(prev_flow),1)

    top = rescored[:20]
    old_top = set(prior_items.keys())
    new_top = {x['ticker'] for x in top}
    entered = []
    for x in top:
        x['new_entry'] = bool(old_top and x['ticker'] not in old_top)
        if x['new_entry']:
            entered.append({'ticker':x['ticker'],'name':x['name'],'rank':x['rank']})
    exited = []
    if old_top:
        for ticker in old_top-new_top:
            p = prior_items[ticker]
            exited.append({'ticker':ticker,'name':p.get('name',ticker),'old_rank':p.get('rank')})
        exited.sort(key=lambda z: z.get('old_rank') or 999)

    sectors = []
    for sec in sorted({x['sector'] for x in rescored if x['sector'] != '기타'}):
        xs = [x for x in rescored if x['sector']==sec]
        sectors.append({
            'sector': sec, 'score': round(sum(x['score'] for x in xs)/len(xs),1),
            'change': round(sum(x.get('change',0) for x in xs)/len(xs),2),
            'leaders': [x['name'] for x in xs[:3]], 'count': len(xs),
        })
    sectors.sort(key=lambda z:z['score'], reverse=True)
    sectors = sectors[:10]

    early_pool = [score_early_leader(x) for x in rescored]
    # Require some actual market activity so dormant names do not dominate the early list.
    early_pool = [x for x in early_pool if x.get('amount_ratio', 0) >= 1.05 or x.get('flow_surge') or x.get('high52', 0) >= 0.95]
    early_pool.sort(key=lambda z: (z.get('early_score',0), z.get('amount',0)), reverse=True)
    early_leaders = []
    for i, x in enumerate(early_pool[:12]):
        y = dict(x)
        y['early_rank'] = i + 1
        early_leaders.append(y)

    changes = {'entered':entered, 'exited':exited}
    pullbacks = build_pullbacks(rescored)
    lifecycle, rotations, performance = update_history(rescored, top, early_leaders)
    _save_snapshot(top, source, sectors, flow_status, changes, early_leaders, pullbacks, lifecycle, rotations, performance)
    return {'items':top, 'sectors':sectors, 'early_leaders':early_leaders, 'pullbacks':pullbacks, 'lifecycle':lifecycle, 'rotations':rotations, 'performance':performance, 'source':source, 'flow_status':flow_status, 'changes':changes, 'updated_at':datetime.now().isoformat(timespec='seconds')}


def sample_scan() -> dict:
    rows = [dict(x) for x in SAMPLE]
    # sample mode explicitly indicates no real investor flow
    for x in rows:
        x['flow_available'] = False
    return _rank(rows, 'sample-fallback', '샘플 모드 · 실제 수급 미반영')


def live_scan(universe_size: int = 100) -> dict:
    """Scan high-turnover KRX stocks using pykrx only, then enrich investor flows."""
    from pykrx import stock

    # KRX/pykrx can occasionally lag on holidays or immediately after market close.
    # Walk backward to find the latest trading day with usable OHLCV data.
    latest = None
    latest_day = None
    now = datetime.now()
    for back in range(0, 10):
        day = (now - timedelta(days=back)).strftime('%Y%m%d')
        frames = []
        for market in ('KOSPI', 'KOSDAQ'):
            try:
                d = stock.get_market_ohlcv_by_ticker(day, market=market)
                if d is not None and not d.empty:
                    d = d.copy()
                    d['market'] = market
                    frames.append(d)
            except Exception:
                pass
        if frames:
            latest = pd.concat(frames)
            latest_day = day
            break
    if latest is None or latest.empty:
        raise RuntimeError('KRX latest-day OHLCV unavailable')

    amount_col = '거래대금'
    if amount_col not in latest.columns:
        raise RuntimeError(f'Unexpected pykrx OHLCV columns: {list(latest.columns)}')
    latest[amount_col] = pd.to_numeric(latest[amount_col], errors='coerce').fillna(0)
    latest = latest.sort_values(amount_col, ascending=False).head(universe_size)

    start_day = (datetime.strptime(latest_day, '%Y%m%d') - timedelta(days=430)).strftime('%Y%m%d')
    rows = []
    for ticker, r in latest.iterrows():
        ticker = str(ticker).zfill(6)
        try:
            name = stock.get_market_ticker_name(ticker) or ticker
            h = stock.get_market_ohlcv_by_date(start_day, latest_day, ticker)
            if h is None or len(h) < 25 or '종가' not in h.columns:
                continue
            h = h.dropna(subset=['종가'])
            close = float(h['종가'].iloc[-1])
            prev_close = float(h['종가'].iloc[-2]) if len(h) >= 2 else close
            change = (close / prev_close - 1) * 100 if prev_close else 0
            if '거래대금' in h.columns:
                amount_series = pd.to_numeric(h['거래대금'], errors='coerce').fillna(0)
            else:
                amount_series = pd.to_numeric(h['종가'], errors='coerce').fillna(0) * pd.to_numeric(h['거래량'], errors='coerce').fillna(0)
            amount = float(amount_series.iloc[-1])
            prev20 = amount_series.iloc[-21:-1] if len(amount_series) >= 21 else amount_series.iloc[:-1]
            avg20_amount = float(prev20.mean()) if len(prev20) else amount
            amount_ratio = amount / avg20_amount if avg20_amount else 1.0
            close20 = float(h['종가'].iloc[-21]) if len(h) >= 21 else float(h['종가'].iloc[0])
            rs20 = close / close20 if close20 else 1.0
            high_col = '고가' if '고가' in h.columns else '종가'
            high52_abs = float(pd.to_numeric(h[high_col], errors='coerce').tail(250).max())
            high52 = close / high52_abs if high52_abs else 0.9
            ma5 = float(pd.to_numeric(h['종가'], errors='coerce').tail(5).mean())
            ma10 = float(pd.to_numeric(h['종가'], errors='coerce').tail(10).mean())
            rows.append({
                'ticker': ticker, 'name': name, 'market': str(r.get('market', 'KRX')),
                'sector': guess_sector(name, None), 'close': round(close), 'change': round(change, 2),
                'amount': round(amount), 'amount_ratio': round(amount_ratio, 2), 'rs20': round(rs20, 3),
                'high52': round(high52, 3),
                'ma5_ratio': round(close / ma5 if ma5 else 1.0, 4),
                'ma10_ratio': round(close / ma10 if ma10 else 1.0, 4),
            })
        except Exception:
            continue
    if len(rows) < 10:
        raise RuntimeError(f'Only {len(rows)} stocks were successfully enriched')

    rows, flow_status = enrich_investor_flow(rows)
    source = 'pykrx/KRX 가격·거래대금 + 투자자 수급' if any(x.get('flow_available') for x in rows) else 'pykrx/KRX 가격·거래대금'
    return _rank(rows, source, flow_status)


def get_snapshot() -> dict:
    try:
        if SNAPSHOT.exists():
            return json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    except Exception:
        pass
    return sample_scan()


def diagnose_connections() -> dict:
    """Run small, independent KRX checks so Render failures are visible instead of hidden by fallback."""
    result = {
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'overall': False,
        'components': {},
        'runtime': {'python_source': 'pykrx', 'render_safe': True},
    }
    try:
        import pykrx
        result['runtime']['pykrx_import'] = True
        result['runtime']['pykrx_version'] = getattr(pykrx, '__version__', 'unknown')
        from pykrx import stock
    except Exception as e:
        result['runtime']['pykrx_import'] = False
        result['runtime']['error'] = f'{type(e).__name__}: {e}'[:300]
        return result

    now = datetime.now()
    market_frame = None
    latest_day = None
    last_errors=[]
    for back in range(0, 10):
        day=(now-timedelta(days=back)).strftime('%Y%m%d')
        try:
            d=stock.get_market_ohlcv_by_ticker(day, market='KOSPI')
            if d is not None and not d.empty:
                market_frame=d; latest_day=day; break
        except Exception as e:
            last_errors.append(f'{day}: {type(e).__name__}: {e}')
    if market_frame is not None:
        result['components']['price_turnover']={'ok':True,'latest_day':latest_day,'rows':int(len(market_frame)),'columns':[str(x) for x in market_frame.columns]}
    else:
        result['components']['price_turnover']={'ok':False,'error':(' | '.join(last_errors[-3:]) or 'empty KRX response')[:600]}

    try:
        tickers=stock.get_market_ticker_list(latest_day or now.strftime('%Y%m%d'), market='KOSPI')
        result['components']['ticker_list']={'ok':bool(tickers),'count':len(tickers or [])}
    except Exception as e:
        result['components']['ticker_list']={'ok':False,'error':f'{type(e).__name__}: {e}'[:600]}

    fd=(now-timedelta(days=9)).strftime('%Y%m%d'); td=(latest_day or now.strftime('%Y%m%d'))
    for investor,key in [('외국인','foreign_flow'),('기관합계','institution_flow')]:
        try:
            d=_investor_table(fd,td,'KOSPI',investor)
            result['components'][key]={'ok':d is not None and not d.empty,'rows':int(len(d)) if d is not None else 0,'columns':[str(x) for x in d.columns] if d is not None else []}
        except Exception as e:
            result['components'][key]={'ok':False,'error':f'{type(e).__name__}: {e}'[:600]}

    checks=result['components']
    result['overall']=bool(checks) and all(v.get('ok') for v in checks.values())
    result['summary']='모든 핵심 KRX 연결 정상' if result['overall'] else '일부 KRX 연결 실패 — components의 error 확인'
    return result
