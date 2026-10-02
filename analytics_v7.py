from __future__ import annotations
from datetime import datetime
from storage import load_state, save_state


def _load():
    return load_state({'days': [], 'tracks': {}, 'detections': {}})


def _save(state):
    return save_state(state)


def _date_key():
    return datetime.now().strftime('%Y-%m-%d')


def build_pullbacks(rows):
    out=[]
    for x in rows:
        score=float(x.get('score',0) or 0)
        rs=float(x.get('rs20',1) or 1)
        ma5=float(x.get('ma5_ratio',1) or 1)
        ma10=float(x.get('ma10_ratio',1) or 1)
        change=float(x.get('change',0) or 0)
        amount=float(x.get('amount_ratio',1) or 1)
        if score < 58 or rs < 1.03 or change > 4.5:
            continue
        near5=max(0, 1-abs(ma5-1)/0.055)
        near10=max(0, 1-abs(ma10-1)/0.07)
        trend=min(1,max(0,(rs-1.02)/0.16))
        quiet=min(1,max(0,(5.0-abs(change))/5.0))
        turnover=min(1,max(0,(amount-0.8)/1.4))
        flow=min(1,max(0,float((x.get('parts') or {}).get('수급',10))/20))
        pb=round(30*max(near5,near10)+25*trend+15*quiet+15*turnover+15*flow,1)
        reasons=[]
        if abs(ma5-1)<=0.035: reasons.append(f'5일선 근접 ({(ma5-1)*100:+.1f}%)')
        if abs(ma10-1)<=0.05: reasons.append(f'10일선 근접 ({(ma10-1)*100:+.1f}%)')
        if rs>=1.08: reasons.append('20일 추세 우위 유지')
        if x.get('foreign_streak',0)>=2 or x.get('institution_streak',0)>=2: reasons.append('수급 연속성 유지')
        if amount>=1.2: reasons.append('거래대금 유지')
        y=dict(x); y['pullback_score']=pb; y['pullback_reasons']=reasons[:3] or ['강한 추세 내 조정 후보']
        out.append(y)
    out.sort(key=lambda z:(z['pullback_score'],z.get('score',0)), reverse=True)
    for i,x in enumerate(out[:12]): x['pullback_rank']=i+1
    return out[:12]


def update_history(all_rows, top, early):
    state=_load(); day=_date_key()
    day_list=state.setdefault('days',[])
    if day not in day_list: day_list.append(day)
    day_list[:] = day_list[-90:]
    tracks=state.setdefault('tracks',{})
    detections=state.setdefault('detections',{})
    current_by_ticker={x['ticker']:x for x in all_rows}
    observed=set()
    # lifecycle is driven by top20 + early leader detections
    for x in list(top)+list(early):
        t=x['ticker']; observed.add(t)
        tr=tracks.setdefault(t, {'ticker':t,'name':x['name'],'sector':x.get('sector','기타'),'first_seen':day,'last_seen':day,'seen_days':0,'consecutive_days':0,'peak_score':0,'stages':[]})
        if tr.get('last_seen') == day:
            pass
        else:
            prev_idx=day_list.index(tr['last_seen']) if tr.get('last_seen') in day_list else -99
            cur_idx=day_list.index(day)
            tr['consecutive_days'] = int(tr.get('consecutive_days',0))+1 if prev_idx==cur_idx-1 else 1
            tr['seen_days']=int(tr.get('seen_days',0))+1
            tr['last_seen']=day
        if tr.get('seen_days',0)==0: tr['seen_days']=1; tr['consecutive_days']=1
        tr['peak_score']=max(float(tr.get('peak_score',0)), float(x.get('score',0) or 0), float(x.get('early_score',0) or 0))
        stage=x.get('stage') or x.get('early_label') or '관찰'
        stages=tr.setdefault('stages',[])
        if not stages or stages[-1].get('date')!=day:
            stages.append({'date':day,'stage':stage,'score':x.get('score',x.get('early_score',0))})
        elif stages:
            stages[-1]={'date':day,'stage':stage,'score':x.get('score',x.get('early_score',0))}
        tr['stages']=stages[-20:]
    # performance tracking: each first detection becomes one cohort entry
    for x in list(top)+list(early):
        key=x['ticker']+'@'+day
        if key not in detections:
            detections[key]={'ticker':x['ticker'],'name':x['name'],'sector':x.get('sector','기타'),'date':day,'entry':float(x.get('close',0) or 0),'prices':[],'kind':'EARLY' if any(e.get('ticker')==x['ticker'] for e in early) else 'TOP20'}
    # update open detection prices with currently observed universe close
    for d in detections.values():
        x=current_by_ticker.get(d['ticker'])
        if not x or not d.get('entry'): continue
        prices=d.setdefault('prices',[])
        if not prices or prices[-1].get('date')!=day:
            prices.append({'date':day,'close':float(x.get('close',0) or 0)})
        else:
            prices[-1]['close']=float(x.get('close',0) or 0)
        d['prices']=prices[-30:]
    # trim detections to recent 180
    if len(detections)>180:
        for k in sorted(detections, key=lambda k:detections[k].get('date',''))[:-180]: detections.pop(k,None)
    _save(state)

    lifecycle=[]
    for t,tr in tracks.items():
        x=current_by_ticker.get(t)
        if not x: continue
        y={**x, **{k:tr.get(k) for k in ['first_seen','last_seen','seen_days','consecutive_days','peak_score','stages']}}
        days=int(tr.get('consecutive_days',1))
        if days<=1: status='오늘 첫 포착'
        elif days<=3: status=f'{days}일째 강화'
        elif days<=7: status=f'{days}일째 주도'
        else: status=f'{days}일째 장기주도'
        y['lifecycle_status']=status
        lifecycle.append(y)
    lifecycle.sort(key=lambda z:(z.get('consecutive_days',0),z.get('score',0)), reverse=True)

    # rotation: compare current sector champion to previous-day champion recorded in history snapshot within tracks' stages is insufficient.
    # Persist today's champions in state.
    champions={}
    for x in all_rows:
        sec=x.get('sector','기타')
        if sec=='기타': continue
        if sec not in champions or x.get('score',0)>champions[sec].get('score',0): champions[sec]=x
    prev_champs=state.get('last_champions',{})
    rotations=[]
    for sec,x in champions.items():
        p=prev_champs.get(sec)
        if p and p.get('ticker')!=x.get('ticker'):
            rotations.append({'sector':sec,'from_name':p.get('name'),'from_ticker':p.get('ticker'),'to_name':x.get('name'),'to_ticker':x.get('ticker'),'to_score':x.get('score'),'gap':round(float(x.get('score',0))-float(p.get('score',0)),1)})
    state['last_champions']={sec:{'ticker':x['ticker'],'name':x['name'],'score':x.get('score',0)} for sec,x in champions.items()}
    _save(state)

    # performance summary from tracked detections
    rows=[]
    for d in detections.values():
        entry=float(d.get('entry',0) or 0); prices=d.get('prices',[])
        if not entry or not prices: continue
        rets=[(float(p['close'])/entry-1)*100 for p in prices if p.get('close')]
        if not rets: continue
        rows.append({**d,'current_return':round(rets[-1],2),'max_return':round(max(rets),2),'max_drawdown':round(min(rets),2),'obs_days':len(prices)})
    rows.sort(key=lambda z:z.get('date',''), reverse=True)
    mature=[r for r in rows if r['obs_days']>=3]
    performance={
        'detections':rows[:40],
        'total':len(rows),
        'mature':len(mature),
        'positive_rate':round(sum(r['current_return']>0 for r in mature)/len(mature)*100,1) if mature else None,
        'hit_3pct_rate':round(sum(r['max_return']>=3 for r in mature)/len(mature)*100,1) if mature else None,
        'avg_current_return':round(sum(r['current_return'] for r in mature)/len(mature),2) if mature else None,
    }
    return lifecycle[:20], rotations[:10], performance
