(() => {
  let refreshing = false;
  function fitMarketNumbers() {
    for (const card of document.querySelectorAll('#market-metrics .metric')) {
      const price=card.querySelector('strong:not(.metric-pending)'), change=card.querySelector('.metric-change');
      if(!price||!change)continue;
      price.style.fontSize='';change.style.fontSize='';
      if(price.scrollWidth>price.clientWidth&&price.clientWidth>0){
        const size=Math.floor(parseFloat(getComputedStyle(price).fontSize)*price.clientWidth/price.scrollWidth*10)/10;
        price.style.fontSize=size+'px';
        if(parseFloat(getComputedStyle(change).fontSize)>=size)change.style.fontSize=Math.max(12,size-3)+'px';
      }
    }
  }
  async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
  const target = document.getElementById('market-metrics');
  if (!target) return;
  const labels = {verification_unavailable:'비교 출처의 검증 자료가 없습니다',rights_pending:'공개 게시 근거 확인 대기',calendar_unavailable:'거래일 달력 확인 필요',missing:'최근 마감 자료 미반영',provider_error:'데이터 확인 실패',disagreement:'출처 간 수치 불일치',invalid:'수치 검증 보류'};
  const add = (name, item, state) => {
    const card = document.createElement('div'); card.className = 'panel metric';
    const label = document.createElement('small'); label.textContent = name;
    const strong = document.createElement('strong'); strong.textContent = item ? item.close.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : '자료 확인 대기';
    const change = document.createElement('span'); change.className = 'metric-change'+(item ? item.changePct>0?' market-up':item.changePct<0?' market-down':' market-flat' : ' metric-unavailable');
    change.textContent = item ? `${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(2)}%` : (labels[state?.status] || '검증 자료 미연결');
    const day = document.createElement('small'); day.className='metric-date';day.textContent=item ? item.asOf+' 기준' : state?.expectedAsOf||'';
    if(!item)strong.className='metric-pending';
    card.append(label, strong, change, day);
    target.append(card);
  };
  let indices=[], states=[], checkedAt='';
  try {
    const response=await fetch('data/public-market.json',{cache:'no-cache'});
    if(!response.ok)throw Error();
    const data=await response.json();checkedAt=data.checkedAt||'';
    states=Array.isArray(data.marketStatus)?data.marketStatus:[];
    indices=(Array.isArray(data.indices)?data.indices:[]).filter(x=>x.verified===true&&x.publication?.status==='approved_public'&&/^https:\/\//.test(x.publication?.evidence)&&/^https:\/\//.test(x.source)&&Number.isFinite(x.close)&&x.close>0&&Number.isFinite(x.changePct)&&/^20\d{2}-\d{2}-\d{2}$/.test(x.asOf));
  } catch { /* Never fabricate prices or silently relabel older data as today's close. */ }
  target.replaceChildren();
  for(const name of ['KOSPI','KOSDAQ','S&P 500','NASDAQ'])add(name,indices.find(x=>x.name===name),states.find(x=>x.name===name));
  let notes=document.getElementById('market-source-notes');
  const wasOpen=notes?.open||false;
  if(!notes){notes=document.createElement('details');notes.id='market-source-notes';notes.className='market-source-notes';target.after(notes);}
  notes.replaceChildren();notes.open=wasOpen;
  const heading=document.createElement('summary');heading.textContent='출처·검증 정보';notes.append(heading);
  const pending=indices.filter(x=>!x.verified).map(x=>x.name);
  let stateLine=document.getElementById('market-validation-summary');
  if(!stateLine){stateLine=document.createElement('p');stateLine.id='market-validation-summary';stateLine.className='market-validation-summary';notes.before(stateLine);}
  stateLine.textContent=pending.length?pending.join(' · ')+' · 단일 출처 검증 · 교차 검증 대기':indices.length?'표시된 지수 · 교차 검증 완료':'확인된 자료가 있을 때 표시합니다';
  const notices=new Set();
  for(const item of indices){
    const row=document.createElement('div');row.className='market-source-row';
    const title=document.createElement('b');title.textContent=item.name;
    const status=document.createElement('span');status.textContent=(item.verified?'교차 검증 완료':'단일 출처 · 비교 대기')+(item.previousAsOf?' · '+item.previousAsOf+' 종가 대비':'');row.append(title,status);
    for(const [url,label] of [[item.source,item.sourceName||'원문'],[item.verificationSource,item.verificationSourceName||'비교 출처']]){
      if(!/^https:\/\//.test(url||''))continue;
      const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=label+' ↗';row.append(link);
    }
    for(const key of ['copyrightNotice','verificationCopyrightNotice'])if(item[key])notices.add(item[key]);
    notes.append(row);
  }
  for(const text of notices){const n=document.createElement('p');n.className='market-source-copyright';n.textContent=text;notes.append(n);}
  const regionDate=region=>[...new Set(indices.filter(x=>x.region===region).map(x=>x.asOf))].join(' · ')||'확인 대기';
  const summary=document.getElementById('market-date-summary');
  summary.textContent=`국내: ${regionDate('kr')} / 미국: ${regionDate('us')} · 지표별 확정 종가 기준 · 실시간 시세가 아닙니다.`;
  if(checkedAt){const n=document.createElement('div');n.className='sub';const date=new Date(checkedAt);if(!Number.isNaN(date.valueOf()))n.textContent='최근 수집 확인: '+date.toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})+' KST';summary.append(n);}
  fitMarketNumbers();
  document.fonts?.ready.then(fitMarketNumbers);
  } finally { refreshing = false; }
  }
  refresh();
  setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('resize', () => requestAnimationFrame(fitMarketNumbers));
})();
