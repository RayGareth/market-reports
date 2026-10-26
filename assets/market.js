(async () => {
  const target = document.getElementById('market-metrics');
  if (!target) return;
  const labels = {verification_unavailable:'비교 출처의 검증 자료가 없습니다',rights_pending:'공개 게시 근거 확인 대기',calendar_unavailable:'거래일 달력 확인 필요',missing:'최근 마감 자료 미반영',provider_error:'데이터 확인 실패',disagreement:'출처 간 수치 불일치',invalid:'수치 검증 보류'};
  const add = (name, item, state) => {
    const card = document.createElement('div'); card.className = 'panel metric';
    const label = document.createElement('small'); label.textContent = name;
    const strong = document.createElement('strong'); strong.textContent = item ? item.close.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : '자료 확인 대기';
    const foot = document.createElement('span'); foot.className = 'sub';
    foot.textContent = item ? `${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(2)}% · ${item.asOf} 확정 종가` : (labels[state?.status] || '공개 가능한 검증 자료 미연결');
    card.append(label, strong, foot);
    if (item) {
      const status=document.createElement('span');status.className='sub';status.textContent='확정 종가 · 교차 검증 완료'+(item.previousAsOf ? ' · '+item.previousAsOf+' 종가 대비' : '');card.append(status);
      const source = document.createElement('a'); source.className='sub';source.href=item.source;source.target='_blank';source.rel='noopener noreferrer';source.textContent='종가 출처 · '+(item.sourceName||'원문')+' ↗';card.append(source);
      if (/^https:\/\//.test(item.verificationSource || '')) {const check = source.cloneNode();check.href=item.verificationSource;check.textContent='교차 검증 출처 · '+(item.verificationSourceName||'원문')+' ↗';card.append(check);}
    }
    target.append(card);
  };
  target.replaceChildren();
  let indices=[], states=[], checkedAt='';
  try {
    const response=await fetch('data/public-market.json',{cache:'no-cache'});
    if(!response.ok)throw Error();
    const data=await response.json();checkedAt=data.checkedAt||'';
    states=Array.isArray(data.marketStatus)?data.marketStatus:[];
    indices=(Array.isArray(data.indices)?data.indices:[]).filter(x=>x.verified===true&&x.publication?.status==='approved_public'&&/^https:\/\//.test(x.publication?.evidence)&&/^https:\/\//.test(x.source)&&Number.isFinite(x.close)&&x.close>0&&Number.isFinite(x.changePct)&&/^20\d{2}-\d{2}-\d{2}$/.test(x.asOf));
  } catch { /* Never fabricate prices or silently relabel older data as today's close. */ }
  for(const name of ['KOSPI','KOSDAQ','S&P 500','NASDAQ'])add(name,indices.find(x=>x.name===name),states.find(x=>x.name===name));
  const regionDate=region=>[...new Set(indices.filter(x=>x.region===region).map(x=>x.asOf))].join(' · ')||'확인 대기';
  const summary=document.getElementById('market-date-summary');
  summary.textContent=`국내: ${regionDate('kr')} / 미국: ${regionDate('us')} · 지표별 확정 종가 기준 · 실시간 시세가 아닙니다.`;
  if(checkedAt){const n=document.createElement('div');n.className='sub';const date=new Date(checkedAt);if(!Number.isNaN(date.valueOf()))n.textContent='최근 수집 확인: '+date.toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})+' KST';summary.append(n);}
})();
