const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let snapshot = window.INITIAL || {items:[],sectors:[]};

function money(v){ return Math.round((v||0)/1e8).toLocaleString()+'억'; }
function sign(v){ return `${v>=0?'+':''}${Number(v).toFixed(2)}%`; }
function toast(t){ const el=$('#toast'); el.textContent=t; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),2600); }

function render(data){
  snapshot=data; $('#source').textContent=data.source||'-'; $('#updated').textContent='업데이트 '+(data.updated_at||'-'); const fs=$('#flowStatus'); if(fs) fs.textContent=data.flow_status||'수급 상태 확인 중';
  const rows=(data.items||[]).map((r,i)=>{
    const mv=r.rank_change?`<small class="rankmove">${r.rank_change>0?'▲':'▼'}${Math.abs(r.rank_change)}</small>`:'';
    const ne=r.new_entry?' <small class="newbadge">NEW</small>':'';
    const fc=(r.flow_score_change===null||r.flow_score_change===undefined)?'':`<small class="flowmove">수급 ${r.flow_score_change>=0?'+':''}${r.flow_score_change}</small>`;
    return `<button class="tr stock-row" data-ticker="${r.ticker}" data-name="${r.name}"><span class="rank">#${r.rank||i+1} ${mv}${ne}</span><span><b>${r.name}</b><small>${r.ticker} · ${r.market||'KRX'}</small>${fc}</span><span>${r.sector||'기타'}</span><span class="chg ${r.change>0?'up':r.change<0?'down':''}">${sign(r.change)}</span><span>${money(r.amount)}</span><span class="score">${r.score}</span><span><em class="stage">${r.stage}</em></span></button>`;
  }).join('');
  $('#leadersTable').innerHTML='<div class="tr head"><span>순위</span><span>종목</span><span>섹터</span><span>등락</span><span>거래대금</span><span>점수</span><span>단계</span></div>'+rows;
  const ch=data.changes||{entered:[],exited:[]};
  $('#enteredList').innerHTML=(ch.entered||[]).length?(ch.entered||[]).map(x=>`<div class="change-item"><b>#${x.rank} ${x.name}</b><span>${x.ticker}</span></div>`).join(''):'<p class="empty">신규진입 없음</p>';
  $('#exitedList').innerHTML=(ch.exited||[]).length?(ch.exited||[]).map(x=>`<div class="change-item"><b>${x.name}</b><span>직전 #${x.old_rank||'-'} · ${x.ticker}</span></div>`).join(''):'<p class="empty">탈락 없음</p>';
  $('#sectorGrid').innerHTML=(data.sectors||[]).map((s,i)=>`<article class="sector-card"><div><span class="sector-rank">${i+1}</span><b>${s.sector}</b><strong>${s.score}</strong></div><div class="bar"><i style="width:${s.score}%"></i></div><p>${(s.leaders||[]).join(' · ')}</p></article>`).join('');
  const eg=$('#earlyGrid'); if(eg) eg.innerHTML=(data.early_leaders||[]).map((r,i)=>`<button class="early-card early-row" data-ticker="${r.ticker}"><div class="early-top"><span class="early-rank">#${r.early_rank||i+1}</span><span class="early-label">${r.early_label||'초기 후보'}</span></div><h4>${r.name}</h4><p>${r.ticker} · ${r.sector||'기타'}</p><div class="early-score"><strong>${r.early_score}</strong><span>/100</span></div><div class="early-signals">${(r.early_signals||[]).slice(0,3).map(x=>`<span>${x}</span>`).join('')}</div></button>`).join('');
  const pg=$('#pullbackGrid'); if(pg) pg.innerHTML=(data.pullbacks||[]).length?(data.pullbacks||[]).map((r,i)=>`<button class="early-card stock-row" data-ticker="${r.ticker}"><div class="early-top"><span class="early-rank">#${r.pullback_rank||i+1}</span><span class="early-label">눌림 ${r.pullback_score}</span></div><h4>${r.name}</h4><p>${r.ticker} · ${r.sector||'기타'}</p><div class="early-score"><strong>${r.pullback_score}</strong><span>/100</span></div><div class="early-signals">${(r.pullback_reasons||[]).slice(0,3).map(x=>`<span>${x}</span>`).join('')}</div></button>`).join(''):'<div class="emptybox">현재 조건에 맞는 눌림목 후보가 없습니다.</div>';
  const lg=$('#lifeGrid'); if(lg) lg.innerHTML=(data.lifecycle||[]).length?(data.lifecycle||[]).map(r=>`<button class="life-card stock-row" data-ticker="${r.ticker}"><div class="life-head"><h4>${r.name}</h4><span>${r.lifecycle_status}</span></div><p>${r.ticker} · ${r.sector||'기타'} · 현재 ${r.stage||'-'} · 최고점수 ${Number(r.peak_score||0).toFixed(1)}</p><div class="timeline">${(r.stages||[]).slice(-6).map(x=>`<i>${x.date.slice(5)} ${x.stage}</i>`).join('')}</div></button>`).join(''):'<div class="emptybox">첫 포착 기록이 쌓이면 생애주기가 표시됩니다.</div>';
  const rl=$('#rotationList'); if(rl) rl.innerHTML=(data.rotations||[]).length?(data.rotations||[]).map(r=>`<div class="rotation-item"><span><b>${r.sector}</b><small>대장 교체</small></span><div><b>${r.from_name}</b><small>${r.from_ticker}</small></div><span class="arrow">→</span><div><b>${r.to_name}</b><small>${r.to_ticker} · ${r.to_score}점</small></div></div>`).join(''):'<div class="emptybox">이번 스냅샷에서는 감지된 대장 교체가 없습니다.</div>';
  const perf=data.performance||{}; const pk=$('#perfKpis'); if(pk) pk.innerHTML=[['누적 포착',perf.total??0,'건'],['3회+ 관측',perf.mature??0,'건'],['플러스 비율',perf.positive_rate??'-','%'],['+3% 도달률',perf.hit_3pct_rate??'-','%']].map(x=>`<div class="kpi"><span>${x[0]}</span><b>${x[1]}${x[2]}</b></div>`).join('');
  const pl=$('#perfList'); if(pl) pl.innerHTML=(perf.detections||[]).length?(perf.detections||[]).slice(0,20).map(r=>`<div class="perf-row"><span><b>${r.name}</b><small>${r.date} · ${r.kind} · ${r.obs_days}회 관측</small></span><span class="${r.current_return>=0?'pos':'neg'}">현재 ${r.current_return>=0?'+':''}${r.current_return}%</span><span class="pos">최대 +${r.max_return}%</span><span class="neg">최저 ${r.max_drawdown}%</span><span>${r.entry.toLocaleString()}원</span></div>`).join(''):'<div class="emptybox">포착 후 새로고침 기록이 쌓이면 성과가 표시됩니다.</div>';
  bindRows();
}

function openDetail(ticker){
  const pools=[snapshot.items||[],snapshot.early_leaders||[],snapshot.pullbacks||[],snapshot.lifecycle||[]]; const r=pools.flat().find(x=>x.ticker===ticker); if(!r)return;
  const max={거래대금:25,수급:20,추세:20,섹터:15,돌파:10,모멘텀:10};
  const bars=Object.entries(r.parts||{}).map(([k,v])=>`<div class="metric"><div><span>${k}</span><b>${v} / ${max[k]}</b></div><div class="bar"><i style="width:${Math.min(100,v/max[k]*100)}%"></i></div></div>`).join('');
  const flow = r.flow_available ? `<h3>실제 수급</h3><div class="flow-grid"><div><span>외국인 5일</span><b>${money(r.foreign_net_5d)}</b></div><div><span>기관 5일</span><b>${money(r.institution_net_5d)}</b></div><div><span>외국인 연속</span><b>${r.foreign_streak||0}일</b></div><div><span>기관 연속</span><b>${r.institution_streak||0}일</b></div><div><span>최근 3일 수급</span><b>${money(r.recent3_flow)}</b></div><div><span>수급 급증</span><b>${r.flow_surge?'감지':'-'}</b></div></div><div class="flow-change">수급점수 전회 대비 <b>${r.flow_score_change===null||r.flow_score_change===undefined?'비교없음':(r.flow_score_change>=0?'+':'')+r.flow_score_change}</b></div>` : `<p class="flow-note">선택한 일별 API에 수급이 없어 점수에 반영하지 않습니다.</p>`; const pb=r.pullback_score?`<h3>눌림목 점수 ${r.pullback_score}</h3><ul class="reasons">${(r.pullback_reasons||[]).map(x=>`<li>${x}</li>`).join('')}</ul>`:''; const ep=r.early_parts?`<h3>EARLY LEADER ${r.early_score}점</h3><div class="early-parts">${Object.entries(r.early_parts).map(([k,v])=>`<div><span>${k}</span><b class="${k==='과열감점'&&v>0?'penalty':''}">${k==='과열감점'?'-':''}${v}</b></div>`).join('')}</div><ul class="reasons">${(r.early_signals||[]).map(x=>`<li>${x}</li>`).join('')}</ul>`:''; $('#detail').innerHTML=`<div class="detail-head"><div><div class="eyebrow">${r.ticker} · ${r.market||'KRX'} · ${r.sector}</div><h2>${r.name}</h2><p class="${r.change>=0?'up':'down'}">${sign(r.change)} · ${Number(r.close||0).toLocaleString()}원</p></div><div class="score-ring"><strong>${r.score||r.early_score}</strong><span>100점</span></div></div><h3>선정 이유</h3><ul class="reasons">${(r.reasons||r.early_signals||[]).map(x=>`<li>${x}</li>`).join('')}</ul>${ep}${pb}${flow}<h3>주도주 세부 점수</h3>${bars}<div class="detail-bottom"><span>현재 단계</span><em class="stage">${r.stage||r.early_label}</em></div>`;
  $('#modal').classList.add('show');
}
function bindRows(){ $$('.stock-row,.early-row').forEach(x=>x.onclick=()=>openDetail(x.dataset.ticker)); }

$$('.tab').forEach(b=>b.onclick=()=>{ $$('.tab').forEach(x=>x.classList.remove('active')); $$('.panel').forEach(x=>x.classList.remove('active')); b.classList.add('active'); $('#'+b.dataset.target).classList.add('active'); });
$('#closeModal').onclick=()=>$('#modal').classList.remove('show');
$('#modal').onclick=e=>{if(e.target.id==='modal')$('#modal').classList.remove('show')};
$('#search').oninput=e=>{ const q=e.target.value.trim().toLowerCase(); $$('.stock-row').forEach(r=>r.style.display=(r.dataset.name.toLowerCase().includes(q)||r.dataset.ticker.includes(q))?'':'none'); };
$('#refreshBtn').onclick=async()=>{ const b=$('#refreshBtn'); b.disabled=true; b.textContent='갱신 중…'; try{const res=await fetch('/api/refresh',{method:'POST'}); const data=await res.json(); render(data); toast(data.ok?'KRX 공식 일별 데이터로 갱신했습니다.':(data.error||'조회 실패: 기존 데이터 유지'));}catch(e){toast('갱신에 실패했습니다.');} finally{b.disabled=false;b.textContent='↻ 데이터 새로고침';}};
bindRows();

async function loadStorageStatus(){ try{ const r=await fetch('/api/storage-status'); const d=await r.json(); const el=document.querySelector('#storageStatus'); if(el) el.textContent=d.mode==='supabase'?'영구저장 · Supabase 연결':'로컬저장 · 재배포 시 초기화 가능'; }catch(e){} }
loadStorageStatus();


async function loadDiagnostics(){
  const summary=document.querySelector('#diagSummary'), box=document.querySelector('#diagItems');
  if(!summary||!box)return;
  try{
    const r=await fetch('/api/diagnostics'); const d=await r.json();
    summary.textContent=d.overall?'실데이터 연결 정상':'일부 연결 실패';
    const labels={price_turnover:'가격·거래대금',ticker_list:'종목목록',foreign_flow:'외국인 수급',institution_flow:'기관 수급'};
    box.innerHTML=Object.entries(d.components||{}).map(([k,v])=>`<div style="margin:4px 0"><b>${labels[k]||k}</b> : ${v.ok?'✅ 정상':'❌ 실패'} ${v.latest_day?'· '+v.latest_day:''}${v.rows!==undefined?' · '+v.rows+'건':''}${v.error?' · '+v.error:''}</div>`).join('');
  }catch(e){summary.textContent='진단 API 호출 실패';box.textContent=String(e);}
}
loadDiagnostics();

function fmtMaybe(v, suffix='') { return (v===null||v===undefined||v==='') ? '확인 안 됨' : Number(v).toLocaleString()+suffix; }
const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
async function loadMarketStatus(){
  const el=document.querySelector('#aiStatus'); if(!el)return;
  try { const r=await fetch('/api/market-status'); const d=await r.json();
    el.textContent=d.configured?'✅ 네이버 API 연결 준비됨 · KRX 데이터와 최신 기사 결합':'❌ NAVER_CLIENT_ID / NAVER_CLIENT_SECRET을 Render Environment에 추가하세요.';
  } catch(e){ el.textContent='네이버 상태 확인 실패: '+e; }
}
async function runMarketScan(){
  const btn=document.querySelector('#aiScanBtn'), st=document.querySelector('#aiStatus');
  btn.disabled=true; btn.textContent='네이버 기사 검색 중…'; st.textContent='KRX TOP12와 네이버 최신 기사를 결합하고 있습니다.';
  try{
    const r=await fetch('/api/market-scan',{method:'POST'}); const d=await r.json();
    if(!d.ok){ st.textContent='❌ '+(d.error||'시장탐색 실패'); return; }
    st.textContent=`✅ ${d.as_of||''} · ${d.source||'NAVER API HUB'} · ${d.method||''}`;
    const sm=document.querySelector('#aiSummary'); sm.style.display='block';
    sm.innerHTML=`<h3>시장 요약</h3><p>${esc(d.market_summary||'-')}</p><div class="early-signals">${(d.sectors||[]).map(x=>`<span>${esc(x.sector)} ${esc(x.strength??'-')} · ${esc(x.reason||'')}</span>`).join('')}</div>`;
    document.querySelector('#aiCandidates').innerHTML=(d.candidates||[]).map((x,i)=>`<article class="early-card"><div class="early-top"><span class="early-rank">#${i+1}</span><span class="early-label">신호 ${esc(x.signal_score??'-')}</span></div><h4>${esc(x.name||'-')}</h4><p>${esc(x.ticker||'-')} · ${esc(x.sector||'-')}</p><div class="early-signals"><span>${esc(x.reason||'')}</span><span>${esc(x.catalyst||'')}</span></div><p style="font-size:12px;opacity:.8">가격 ${fmtMaybe(x.price,'원')} · 등락 ${fmtMaybe(x.change_pct,'%')} · 거래대금 ${fmtMaybe(x.turnover_krw,'원')}</p><p style="font-size:12px">${esc(x.data_note||'')}</p></article>`).join('');
    document.querySelector('#aiSources').innerHTML=(d.source_urls||[]).length?`<div class="logic-card"><h3>네이버 검색 출처</h3>${d.source_urls.map(u=>`<p><a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a></p>`).join('')}</div>`:'';
  }catch(e){ st.textContent='❌ 시장탐색 호출 실패: '+e; }
  finally{btn.disabled=false;btn.textContent='네이버 최신시장 검색';}
}
const aiBtn=document.querySelector('#aiScanBtn'); if(aiBtn) aiBtn.onclick=runMarketScan; loadMarketStatus();
