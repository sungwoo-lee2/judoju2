"""Resumable market-wide daily archive, raw unadjusted KRX prices."""
import os, sqlite3, json, threading, time
from pathlib import Path
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
DB = Path(os.getenv('KRX_HISTORY_DB', str(Path(__file__).parent/'data'/'krx_history.sqlite3')))
lock = threading.Lock()
job = {'running':False, 'done':0, 'total':0, 'error':None}

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(DB, timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS days (market TEXT, day TEXT, payload TEXT, PRIMARY KEY(market,day))')
    return c

def cached_fetch(market, day):
    import krx_api
    with connect() as c:
        row=c.execute('SELECT payload FROM days WHERE market=? AND day=?',(market,day)).fetchone()
    if row: return json.loads(row[0])
    rows=krx_api.fetch(market,day)
    if any(str(r.get('BAS_DD','')).replace('-','')!=day for r in rows):
        raise RuntimeError('KRX 과거 응답 기준일 불일치')
    # Recent empty responses may be delayed publication. Older empty weekdays are
    # holidays, so remember them and avoid requesting the same date every hour.
    requested=date(int(day[:4]),int(day[4:6]),int(day[6:8]))
    old_enough=requested < datetime.now(ZoneInfo('Asia/Seoul')).date()-timedelta(days=7)
    if rows or old_enough:
        with connect() as c: c.execute('INSERT OR REPLACE INTO days VALUES (?,?,?)',(market,day,json.dumps(rows,ensure_ascii=False)))
    return rows

def is_cached(market,day):
    with connect() as c:
        return c.execute('SELECT 1 FROM days WHERE market=? AND day=?',(market,day)).fetchone() is not None

def dates(start,end):
    a=date.fromisoformat(start); b=date.fromisoformat(end)
    latest=datetime.now(ZoneInfo('Asia/Seoul')).date()-timedelta(days=1)
    if a<date(2010,1,4) or b>latest or a>b: raise ValueError('기간은 2010-01-04부터 어제까지 지정하세요.')
    while b>=a:
        if b.weekday()<5: yield b.strftime('%Y%m%d')
        b-=timedelta(days=1)

def start_job(start,end):
    days=list(dates(start,end))
    with lock:
        if job['running']: return dict(job)
        job.update(running=True,done=0,total=len(days)*2,error=None,start=start,end=end,day=None)
    def run():
        try:
            for day in days:
                for market in ('KOSPI','KOSDAQ'):
                    already=is_cached(market,day)
                    cached_fetch(market,day)
                    with lock: job.update(done=job['done']+1,day=day,market=market)
                    if not already: time.sleep(.3)
            import krx_api
            krx_api.scan(int(os.getenv('UNIVERSE_SIZE','80')))
        except Exception as e:
            with lock: job['error']=str(e)
        finally:
            with lock: job['running']=False
    threading.Thread(target=run,daemon=True).start()
    return dict(job)

def status():
    with connect() as c:
        count,first,last=c.execute('SELECT COUNT(*),MIN(day),MAX(day) FROM days').fetchone()
    with lock: result=dict(job)
    return {**result,'cached_market_days':count,'first_day':first,'last_day':last,'price_basis':'KRX 원종가 (수정주가 아님)'}

def series(market,ticker,end,limit=252):
    with connect() as c:
        records=c.execute("SELECT day,payload FROM days WHERE market=? AND day<=? AND payload!='[]' ORDER BY day DESC LIMIT ?",(market,end,limit)).fetchall()
    result=[]
    for day,payload in reversed(records):
        r=next((r for r in json.loads(payload) if str(r.get('ISU_CD'))==ticker),None)
        result.append((day,r))
    return result

def build_index(end):
    index={}
    with connect() as c:
        for market in ('KOSPI','KOSDAQ'):
            records=c.execute("SELECT day,payload FROM days WHERE market=? AND day<=? AND payload!='[]' ORDER BY day DESC LIMIT 252",(market,end)).fetchall()
            index[market]=[(day,{str(r.get('ISU_CD')):r for r in json.loads(payload)}) for day,payload in reversed(records)]
    return index

def indicators(market,ticker,end,index=None):
    from krx_api import number
    records=series(market,ticker,end) if index is None else [(day,rows.get(ticker)) for day,rows in index.get(market,[])]
    out={'history_days':sum(r is not None for _,r in records),'price_basis':'원종가·기업행사 미조정'}
    for n in (5,10,20):
        tail=records[-n:]
        values=[number(r.get('TDD_CLSPRC')) if r else None for _,r in tail]
        if len(values)==n and all(v is not None and v>0 for v in values): out['ma'+str(n)]=round(sum(values)/n,4)
    prior=records[-21:-1]
    amounts=[number(r.get('ACC_TRDVAL')) if r else None for _,r in prior]
    if len(amounts)==20 and all(v is not None for v in amounts) and sum(amounts)>0:
        current=number(records[-1][1].get('ACC_TRDVAL')) if records[-1][1] else None
        if current is not None: out['amount_ratio']=round(current/(sum(amounts)/20),4)
    # Missing dates/rows never turn into zero or a fabricated moving average.
    if len(records)>=21 and all(r and number(r.get('TDD_CLSPRC')) for _,r in records[-21:]) and 'ma20' in out:
        prev=sum(number(r['TDD_CLSPRC']) for _,r in records[-21:-1])/20
        out['ma20_rising']=out['ma20']>prev
    if len(records)>=250 and all(r and number(r.get('TDD_HGPRC')) for _,r in records[-250:]):
        out['high52_price']=max(number(r['TDD_HGPRC']) for _,r in records[-250:])
    return out

# One coordinator per server process; network work stays off the startup thread.
auto_stop = threading.Event()
auto_thread = None

def auto_range():
    end = datetime.now(ZoneInfo('Asia/Seoul')).date() - timedelta(days=1)
    # 400 calendar days reliably covers at least 250 Korean trading sessions,
    # including public holidays, for a complete 52-week high calculation.
    return (end - timedelta(days=400)).isoformat(), end.isoformat()

def start_auto():
    global auto_thread
    if os.getenv('AUTO_HISTORY', '1') != '1':
        return
    if auto_thread and auto_thread.is_alive():
        return
    auto_stop.clear()
    def coordinate():
        while not auto_stop.is_set():
            if os.getenv('KRX_API_KEY', '').strip():
                try:
                    start_job(*auto_range())
                except Exception as exc:
                    with lock: job['error'] = str(exc)
            else:
                with lock: job['error'] = 'KRX_API_KEY 설정 후 서버를 재시작하면 자동 수집됩니다.'
            # Retry errors and delayed publications, and pick up a new calendar day.
            if auto_stop.wait(3600):
                break
    auto_thread = threading.Thread(target=coordinate, daemon=True)
    auto_thread.start()

def stop_auto():
    auto_stop.set()
