(async () => {
  const target = document.getElementById('market-metrics');
  if (!target) return;
  const add = (name, value, detail) => {
    const card = document.createElement('div'); card.className = 'panel metric';
    const label = document.createElement('small'); label.textContent = name;
    const strong = document.createElement('strong'); strong.textContent = value;
    const foot = document.createElement('span'); foot.className = 'sub'; foot.textContent = detail;
    card.append(label, strong, foot); target.append(card);
  };
  target.replaceChildren();
  let indices = [], reportDate = '';
  try {
    const r = await fetch('data/public-market.json', {cache:'no-cache'});
    if (!r.ok) throw Error();
    const data = await r.json(); reportDate = data.reportDate;
    indices = data.indices.filter(x => x.verified === true && x.publication?.status === 'approved_public' && /^https:\/\//.test(x.publication?.evidence) && /^https:\/\//.test(x.source) && Number.isFinite(x.close) && Number.isFinite(x.changePct) && /^20\d{2}-\d{2}-\d{2}$/.test(x.asOf));
  } catch { /* Never substitute demo prices for missing market data. */ }
  for (const name of ['KOSPI','KOSDAQ','S&P 500','NASDAQ']) {
    const item = indices.find(x => x.name === name);
    if (item) add(name, item.close.toLocaleString('en-US',{minimumFractionDigits:2}), `${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(2)}% · ${item.asOf} 확정 종가`);
    else add(name, '자료 미연결', '공개 가능한 검증 자료를 기다리고 있어요');
  }
  document.getElementById('market-date-summary').textContent = (reportDate ? '최근 학습 리포트: ' + reportDate + ' · ' : '') + '지표별 기준일은 확정 종가와 함께 표시합니다. 실시간 시세가 아닙니다.';
})();
