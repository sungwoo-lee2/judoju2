from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

from krx_api import snapshot as get_snapshot, scan as live_scan, diagnostics as diagnose_connections
from storage import storage_status
import naver_service

BASE = Path(__file__).resolve().parent
app = FastAPI(title='Leader Finder v18', version='18.0')
app.mount('/static', StaticFiles(directory=str(BASE/'static')), name='static')
templates = Jinja2Templates(directory=str(BASE/'templates'))

@app.on_event('startup')
def startup_refresh():
    from krx_history import start_auto
    start_auto()

@app.on_event('shutdown')
def shutdown_history():
    from krx_history import stop_auto
    stop_auto()

@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    snap = get_snapshot()
    return templates.TemplateResponse('index.html', {'request':request, 'snap':snap})


@app.get('/healthz')
def healthz():
    status = storage_status()
    snap = get_snapshot()
    return {
        'ok': True,
        'app': 'leader-finder-v15',
        'naver': naver_service.status(),
        'storage': status,
        'source': snap.get('source'),
        'leader_count': len(snap.get('items', [])),
        'early_leader_count': len(snap.get('early_leaders', [])),
    }


@app.get('/api/diagnostics')
def diagnostics():
    return diagnose_connections()


@app.get('/api/storage-status')
def get_storage_status():
    return storage_status()

@app.get('/api/snapshot')
def snapshot():
    return get_snapshot()

@app.post('/api/refresh')
def refresh():
    try:
        return {'ok':True, **live_scan(int(os.getenv('UNIVERSE_SIZE','80')))}
    except Exception as e:
        fallback = get_snapshot()
        return {'ok':False, 'error':str(e), **fallback}

@app.get('/api/leaders')
def leaders():
    s=get_snapshot(); return {'items':s.get('items',[]), 'source':s.get('source')}

@app.get('/api/sectors')
def sectors():
    s=get_snapshot()
    if 'sectors' in s: return {'items':s['sectors'], 'source':s.get('source')}
    # old snapshot compatibility
    return {'items':[], 'source':s.get('source')}


@app.get('/api/lifecycle')
def lifecycle():
    s=get_snapshot(); return {'items':s.get('lifecycle',[]), 'source':s.get('source')}

@app.get('/api/pullbacks')
def pullbacks():
    s=get_snapshot(); return {'items':s.get('pullbacks',[]), 'source':s.get('source')}

@app.get('/api/rotations')
def rotations():
    s=get_snapshot(); return {'items':s.get('rotations',[]), 'source':s.get('source')}

@app.get('/api/performance')
def performance():
    s=get_snapshot(); return s.get('performance',{})

@app.get('/api/early-leaders')
def early_leaders():
    s=get_snapshot(); return {'items':s.get('early_leaders',[]), 'source':s.get('source')}

@app.get('/api/stock/{ticker}')
def stock(ticker: str):
    s=get_snapshot()
    item=next((x for x in s.get('items',[]) if x['ticker']==ticker), None) or next((x for x in s.get('early_leaders',[]) if x['ticker']==ticker), None)
    return {'item':item}

from fastapi.responses import StreamingResponse
from krx_history import start_job, status as history_status, series
from pydantic import BaseModel
class HistoryRange(BaseModel):
    start: str
    end: str
@app.get('/api/history/status')
def history_progress(): return history_status()
@app.post('/api/history/load')
def load_history(period: HistoryRange):
    try: return {'ok':True, **start_job(period.start,period.end)}
    except (ValueError,RuntimeError) as e: return {'ok':False,'error':str(e)}
@app.get('/api/history/stock/{market}/{ticker}')
def stock_history(market: str,ticker: str):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    end=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
    return {'items':[r for _,r in series(market,ticker,end,10000) if r]}
@app.get('/api/history/export')
def export_history():
    import csv,io,json
    from krx_history import connect
    def stream():
        buf=io.StringIO(); writer=csv.writer(buf)
        yield '\ufeff'
        writer.writerow(['market','date','ticker','name','close','high','low','volume','turnover'])
        yield buf.getvalue(); buf.seek(0);buf.truncate(0)
        with connect() as c:
            for market,day,payload in c.execute('SELECT market,day,payload FROM days ORDER BY day,market'):
                for r in json.loads(payload):
                    writer.writerow([market,day]+[r.get(k,'') for k in ('ISU_CD','ISU_NM','TDD_CLSPRC','TDD_HGPRC','TDD_LWPRC','ACC_TRDVOL','ACC_TRDVAL')])
                yield buf.getvalue();buf.seek(0);buf.truncate(0)
    return StreamingResponse(stream(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=krx_history.csv'})

from fastapi import Query
@app.get('/api/news/status')
def news_status(): return naver_service.status()
@app.get('/api/market-status')
def market_status(): return naver_service.status()
@app.post('/api/market-scan')
def naver_market_scan():
    try:return {'ok':True,**naver_service.market_scan(get_snapshot().get('items',[]))}
    except (RuntimeError,ValueError) as e:return {'ok':False,'error':str(e),**naver_service.status()}
@app.get('/api/news/search')
def news_search(q: str=Query(min_length=1,max_length=100)):
    try: return {'ok':True, **naver_service.news(q)}
    except (RuntimeError,ValueError) as e:return {'ok':False,'error':str(e),'items':[]}
@app.get('/api/news/leaders')
def news_leaders():
    rows=get_snapshot().get('items',[])
    if not rows:return {'ok':False,'items':[],'error':'KRX 데이터 새로고침으로 TOP20을 먼저 조회하세요.'}
    if not naver_service.status()['configured']:return {'ok':False,'items':[],'error':'NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하세요.'}
    return naver_service.leader_news(rows)
class TrendNames(BaseModel):
    names: list[str]
@app.post('/api/news/trends')
def search_trends(body: TrendNames):
    try:return {'ok':True, **naver_service.trends(body.names)}
    except (RuntimeError,ValueError) as e:return {'ok':False,'error':str(e)}
