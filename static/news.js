(()=>{
const by=id=>document.getElementById(id);let articles=[],savedView=false;
const make=(tag,text)=>{let e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
const readSaved=()=>{try{return JSON.parse(localStorage.getItem('leaderNewsSaved')||'[]');}catch{return [];}};
const saveAll=xs=>localStorage.setItem('leaderNewsSaved',JSON.stringify(xs.slice(0,200)));
function shown(){let tag=by('newsTag').value;return articles.filter(x=>!tag||(x.tags||[]).includes(tag));}
function render(){const root=by('newsCards');root.replaceChildren();for(const x of shown()){
 let card=make('article');card.className='logic-card';let a=make('a',x.title);a.href=x.url;a.target='_blank';a.rel='noopener noreferrer';card.append(a);
 card.append(make('p',(x.stock?x.stock+' · ':'')+(x.source||'')+' · '+(x.published_at?new Date(x.published_at).toLocaleString('ko-KR'):'날짜 미확인')));
 card.append(make('p',x.description));card.append(make('small',(x.tags||[]).join(' · ')));
 let saved=readSaved().some(y=>y.url===x.url),button=make('button',saved?'저장 취소':'모임 기사로 저장');
 button.onclick=()=>{try{let list=readSaved().filter(y=>y.url!==x.url);if(!saved)list.unshift(x);saveAll(list);if(savedView)articles=list;render();}catch{by('newsMessage').textContent='브라우저 저장 공간을 사용할 수 없습니다.';}};card.append(button);root.append(card);
 }if(!shown().length)root.append(make('p','표시할 기사가 없습니다.'));}
async function load(url){by('newsMessage').textContent='기사 조회 중…';by('newsSearch').disabled=true;by('newsLeaders').disabled=true;try{
 let d=await(await fetch(url)).json();savedView=false;articles=d.items||[];render();
 by('newsMessage').textContent=d.ok?'조회 '+articles.length+'건'+(d.errors?.length?' · 일부 종목 조회 실패: '+d.errors.map(x=>x.stock+': '+x.error).join(' / '):''):(d.error||d.errors?.map(x=>x.error).join(' / ')||'조회 실패');
 }catch{by('newsMessage').textContent='기사 조회 요청이 실패했습니다.';}finally{by('newsSearch').disabled=false;by('newsLeaders').disabled=false;}}
by('newsSearch').onclick=()=>{let q=by('newsQuery').value.trim();if(q)load('/api/news/search?q='+encodeURIComponent(q));};
by('newsQuery').onkeydown=e=>{if(e.key==='Enter')by('newsSearch').click();};
by('newsLeaders').onclick=()=>load('/api/news/leaders');by('newsTag').onchange=render;
by('newsSaved').onclick=()=>{savedView=true;articles=readSaved();render();by('newsMessage').textContent='이 브라우저에 저장한 기사 '+articles.length+'건';};
by('newsExport').onclick=async()=>{try{await navigator.clipboard.writeText(shown().map((x,i)=>`${i+1}. ${x.title}\n${x.stock||x.query||''} | ${x.published_at||''}\n${x.url}`).join('\n\n'));by('newsMessage').textContent='기사 목록을 복사했습니다.';}catch{by('newsMessage').textContent='클립보드 복사를 사용할 수 없습니다.';}};
for(let sector of ['반도체','방산','조선','전력','로봇','바이오','2차전지','엔터']){let b=make('button',sector);b.onclick=()=>{by('newsQuery').value=sector+' 주식';by('newsSearch').click();};by('newsSectors').append(b);}
by('trendTop').onclick=()=>by('trendNames').value=(snapshot.items||[]).slice(0,5).map(x=>x.name).join(',');
by('trendCompare').onclick=async()=>{let button=by('trendCompare');button.disabled=true;by('trendMessage').textContent='검색 관심도 조회 중…';try{
 let names=by('trendNames').value.split(',').map(x=>x.trim()).filter(Boolean);let d=await(await fetch('/api/news/trends',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({names})})).json();
 by('trendChart').replaceChildren();if(!d.ok){by('trendMessage').textContent=d.error||'조회 실패';return;}
 by('trendMessage').textContent=d.start+' ~ '+d.end+' · '+d.note;
 for(let group of d.results||[]){let box=make('div');box.append(make('h4',group.title));let values=group.data||[];
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 600 120');svg.setAttribute('role','img');svg.setAttribute('aria-label',group.title+' 검색 관심도');svg.style.width='100%';
 let line=document.createElementNS(ns,'polyline');line.setAttribute('points',values.map((v,i)=>`${10+i*580/Math.max(1,values.length-1)},${110-Math.max(0,Math.min(100,Number(v.ratio)))} `).join(''));line.setAttribute('fill','none');line.setAttribute('stroke','#70baff');line.setAttribute('stroke-width','2');svg.append(line);box.append(svg);
 let details=make('details');details.append(make('summary','날짜별 관심도 보기'));let table=make('table');for(let v of values){let tr=make('tr');tr.append(make('td',v.period),make('td',String(v.ratio)));table.append(tr);}details.append(table);box.append(details);box.append(make('p','최근 제공일 지수: '+(values.at(-1)?.ratio??'자료 없음')));by('trendChart').append(box);}
 }catch{by('trendMessage').textContent='관심도 조회 실패';}finally{button.disabled=false;}};
fetch('/api/news/status').then(r=>r.json()).then(d=>{by('newsConnection').textContent=d.configured?'네이버 인증 설정 완료 · 최신 국내 증시 기사 조회 중':'Render에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET을 추가하세요.';if(d.configured)by('newsSearch').click();}).catch(()=>by('newsConnection').textContent='설정 상태 조회 실패');
})();
