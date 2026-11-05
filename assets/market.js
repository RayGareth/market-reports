(() => {
  const names = ['KOSPI', 'KOSDAQ', 'S&P 500', 'NASDAQ'];
  const labels = {
    verification_unavailable: '비교 출처의 검증 자료가 없습니다',
    rights_pending: '공개 게시 근거 확인 대기',
    calendar_unavailable: '거래일 달력 확인 필요',
    missing: '최근 마감 자료 미반영',
    provider_error: '데이터 확인 실패',
    disagreement: '출처 간 수치 불일치',
    invalid: '수치 검증 보류',
  };
  const clock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
  const timestamp = value => {
    if (!value || !Number.isFinite(Date.parse(value))) return '';
    const parts = Object.fromEntries(clock.formatToParts(new Date(value)).map(({type,value}) => [type,value]));
    return `${parts.month}.${parts.day} ${parts.hour}:${parts.minute} KST`;
  };
  const element = (tag, text, className = '') => {
    const node = document.createElement(tag);
    node.textContent = text;
    node.className = className;
    return node;
  };
  let refreshing = false;

  function fitMarketNumbers() {
    for (const card of document.querySelectorAll('#market-metrics .metric')) {
      const price = card.querySelector('strong:not(.metric-pending)');
      const change = card.querySelector('.metric-change');
      if (!price || !change) continue;
      price.style.fontSize = '';
      change.style.fontSize = '';
      if (price.scrollWidth > price.clientWidth && price.clientWidth > 0) {
        const size = Math.floor(parseFloat(getComputedStyle(price).fontSize) * price.clientWidth / price.scrollWidth * 10) / 10;
        price.style.fontSize = size + 'px';
        if (parseFloat(getComputedStyle(change).fontSize) >= size) change.style.fontSize = Math.max(12, size - 3) + 'px';
      }
    }
  }

  function cardFor(name, item, state, wasOpen) {
    const card = element('div', '', 'panel metric');
    const price = item?.close.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    card.append(element('small', name), element('strong', price ?? '자료 확인 대기', item ? '' : 'metric-pending'));
    const older = Boolean(item && state?.expectedAsOf && item.asOf < state.expectedAsOf);
    if (item) {
      const close = timestamp(item.closeAt);
      const change = item.changePct;
      const direction = change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
      const formatted = (change > 0 ? '+' : change < 0 ? '−' : '') + Math.abs(change).toFixed(2) + '%';
      card.append(element('small', close ? '마감 ' + close : item.asOf + ' 기준', 'metric-date'));
      card.append(element('span', formatted, 'metric-change market-' + direction));
      if (older) card.append(element('small', '최신 거래일 검증 대기', 'metric-stale'));
    }

    const notes = element('details', '', 'market-source-notes');
    notes.dataset.market = name;
    notes.open = wasOpen;
    notes.append(element('summary', '출처·검증 정보'));
    const row = element('div', '', 'market-source-row' + (item ? '' : ' market-source-pending'));
    if (item) {
      const tradeZone = item.region === 'us' ? 'ET' : 'KST';
      const checkTime = timestamp(item.verifiedAt);
      const validation = item.verified ? '교차 검증 완료' : '단일 출처 · 비교 대기';
      row.append(element('span', `${validation} · 기준 거래일 ${item.asOf} (${tradeZone})`));
      if (timestamp(item.closeAt)) row.append(element('span', '마감 ' + timestamp(item.closeAt)));
      if (item.previousAsOf) row.append(element('span', `비교 기준 ${item.previousAsOf} 종가`));
      if (checkTime) row.append(element('span', '검증 완료 ' + checkTime));
      for (const [url, label] of [[item.source, item.sourceName || '원문'], [item.verificationSource, item.verificationSourceName || '비교 출처']]) {
        if (!/^https:\/\//.test(url || '')) continue;
        const link = element('a', label + ' ↗');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        row.append(link);
      }
      for (const notice of new Set([item.copyrightNotice, item.verificationCopyrightNotice].filter(Boolean))) {
        row.append(element('span', notice, 'market-source-copyright'));
      }
    }
    if (!item || older) {
      row.dataset.status = state?.status || 'unavailable';
      row.append(element('span', state?.message || labels[state?.status] || '검증 자료 미연결'));
      if (state?.expectedAsOf) {
        const zone = name === 'S&P 500' || name === 'NASDAQ' ? 'ET' : 'KST';
        row.append(element('span', `확인 대상 ${state.expectedAsOf} (${zone})`));
      }
    }
    notes.append(row);
    card.append(notes);
    return card;
  }

  async function refresh() {
    const target = document.getElementById('market-metrics');
    if (refreshing || !target) return;
    refreshing = true;
    try {
      let indices = [], states = [], checkedAt = '';
      try {
        const response = await fetch('data/public-market.json', {cache: 'no-cache'});
        if (!response.ok) throw Error();
        const data = await response.json();
        checkedAt = data.checkedAt;
        states = Array.isArray(data.marketStatus) ? data.marketStatus : [];
        indices = (Array.isArray(data.indices) ? data.indices : []).filter(x =>
          x.verified === true && x.publication?.status === 'approved_public' &&
          /^https:\/\//.test(x.publication?.evidence) && /^https:\/\//.test(x.source) &&
          Number.isFinite(x.close) && x.close > 0 && Number.isFinite(x.changePct) &&
          /^20\d{2}-\d{2}-\d{2}$/.test(x.asOf));
      } catch { /* Never show unverified data or invent a closing date. */ }
      const open = new Set([...target.querySelectorAll('details[open]')].map(details => details.dataset.market));
      const focused = document.activeElement?.closest('#market-metrics details')?.dataset.market;
      target.replaceChildren(...names.map(name => cardFor(name,
        indices.find(x => x.name === name), states.find(x => x.name === name), open.has(name))));
      if (focused) [...target.querySelectorAll('details')].find(details => details.dataset.market === focused)?.querySelector('summary').focus({preventScroll: true});
      const dates = region => [...new Set(indices.filter(x => x.region === region).map(x => x.asOf))].join(' · ') || '확인 대기';
      const summary = document.getElementById('market-date-summary');
      summary.textContent = `국내: ${dates('kr')} / 미국: ${dates('us')} · 지표별 확정 종가 기준 · 실시간 시세가 아닙니다.`;
      if (timestamp(checkedAt)) summary.append(element('div', '데이터 상태 갱신: ' + timestamp(checkedAt), 'sub'));
      fitMarketNumbers();
      document.fonts?.ready.then(fitMarketNumbers);
    } finally {
      refreshing = false;
    }
  }
  refresh();
  setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('resize', () => requestAnimationFrame(fitMarketNumbers));
})();
