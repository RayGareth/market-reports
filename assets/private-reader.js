/* Private contents are fetched only after explicit connection, never persisted. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const api = 'https://api.github.com/repos/RayGareth/market-reports-private/contents/';
  let token = '', reports = [], controller, epoch = 0, selection = 0, returnFocus;
  const status = text => { $('connection-status').textContent = text; };
  const node = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  function closeDetail() {
    selection++;
    $('report-frame').removeAttribute('srcdoc');
    $('report-frame').hidden = true;
    $('detail-panel').hidden = true;
    $('detail-status').textContent = '';
    $('detail-title').textContent = '상세 리포트';
  }
  function disconnect(message = '연결이 해제되었습니다. 화면의 개인 리포트를 지웠습니다.') {
    epoch++;
    controller?.abort();
    token = ''; reports = [];
    $('reader-token').value = '';
    $('connect-form').hidden = false;
    $('disconnect').hidden = $('refresh').hidden = true;
    $('connect-button').disabled = false;
    $('results').replaceChildren();
    $('year').replaceChildren(new Option('전체 연도', 'all'));
    $('search').value = ''; $('month').value = $('market').value = 'all';
    $('result-count').textContent = '비공개 연결 후 목록을 표시합니다';
    $('no-results').hidden = true;
    closeDetail(); status(message);
  }
  async function read(path, signal) {
    // Never follow repository-provided URLs or forward the credential elsewhere.
    if (!/^(reports\/index\.json|reports\/daily\/20\d{2}-\d{2}-\d{2}\.html|assets\/(style\.css|quiz\.js))$/.test(path)) throw Error('허용되지 않은 경로입니다.');
    const response = await fetch(api + path + '?ref=main', {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
      cache: 'no-store', credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer', signal
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403 || response.status === 404) throw Error('토큰 만료 또는 저장소 읽기 권한을 확인해 주세요.');
      throw Error('GitHub에서 자료를 읽지 못했습니다. 잠시 후 다시 시도해 주세요.');
    }
    const data = await response.json();
    if (data.encoding !== 'base64' || typeof data.content !== 'string') throw Error('파일 형식을 확인할 수 없습니다.');
    return new TextDecoder().decode(Uint8Array.from(atob(data.content.replace(/\s/g, '')), c => c.charCodeAt(0)));
  }
  async function loadIndex(signal) {
    const data = JSON.parse(await read('reports/index.json', signal));
    if (!Array.isArray(data)) throw Error('아카이브 목록 형식이 올바르지 않습니다.');
    return data.filter(r => r.status === 'published' && /^20\d{2}-\d{2}-\d{2}$/.test(r.date) && r.url === 'daily/' + r.date + '.html')
      .map(r => ({ date: r.date, title: String(r.title || r.date), summary: String(r.summary || ''), tags: Array.isArray(r.tags) ? r.tags.map(String) : [], market: Array.isArray(r.market) ? r.market : [] }))
      .sort((a, b) => b.date.localeCompare(a.date));
  }
  function render() {
    const term = $('search').value.trim().toLocaleLowerCase('ko');
    const matched = reports.filter(r => ($('year').value === 'all' || r.date.startsWith($('year').value)) && ($('month').value === 'all' || r.date.slice(5, 7) === $('month').value) && ($('market').value === 'all' || r.market.includes($('market').value)) && [r.date, r.title, r.summary, ...r.tags].join(' ').toLocaleLowerCase('ko').includes(term));
    $('results').replaceChildren();
    for (const r of matched) {
      const row = node('button', '', 'report-row'); row.type = 'button';
      row.dataset.date = r.date;
      const left = node('div'), date = node('time', r.date.replaceAll('-', '.'));
      date.dateTime = r.date;
      left.append(date, node('h3', r.title), node('p', r.summary));
      const tags = node('div'); r.tags.forEach(t => tags.append(node('span', t, 'chip')));
      left.append(tags); row.append(left, node('span', '상세 열기 ↗', 'button-ghost'));
      row.addEventListener('click', () => { returnFocus = row; openReport(r); });
      $('results').append(row);
    }
    $('result-count').textContent = '총 ' + matched.length + '건의 리포트';
    $('no-results').hidden = matched.length > 0;
  }
  function isolatedReport(raw, css) {
    const doc = new DOMParser().parseFromString(raw, 'text/html');
    doc.querySelectorAll('script,link,meta,base,iframe,object,embed,svg,math,style').forEach(n => n.remove());
    for (const n of doc.querySelectorAll('*')) {
      for (const a of [...n.attributes]) {
        if (/^on/i.test(a.name) || ['src', 'srcset', 'action', 'formaction', 'ping', 'xlink:href', 'srcdoc'].includes(a.name.toLowerCase())) n.removeAttribute(a.name);
      }
      if (n.hasAttribute('href')) {
        try {
          const url = new URL(n.getAttribute('href'));
          if (url.protocol !== 'https:') throw Error();
          n.setAttribute('target', '_blank'); n.setAttribute('rel', 'noopener noreferrer');
        } catch { n.removeAttribute('href'); }
      }
    }
    // Local navigation belongs to the reader; sources remain explicit HTTPS links.
    doc.querySelector('.site-header')?.remove();
    const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2, '0')).join('');
    const policy = doc.createElement('meta'); policy.httpEquiv = 'Content-Security-Policy';
    policy.content = "default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-" + nonce + "'; base-uri 'none'; form-action 'none'";
    const referrer = doc.createElement('meta'); referrer.name = 'referrer'; referrer.content = 'no-referrer';
    const viewport = doc.createElement('meta'); viewport.name = 'viewport'; viewport.content = 'width=device-width,initial-scale=1';
    const style = doc.createElement('style'); style.textContent = css.replace(/@import[^;]+;/gi, '');
    const script = doc.createElement('script'); script.setAttribute('nonce', nonce); script.src = new URL('../assets/quiz.js', location.href).href;
    doc.head.prepend(policy, referrer, viewport); doc.head.append(style); doc.body.append(script);
    return '<!doctype html>' + doc.documentElement.outerHTML;
  }
  async function openReport(r) {
    closeDetail(); const request = ++selection, session = epoch;
    $('detail-panel').hidden = false; $('detail-title').textContent = r.date + ' 상세 리포트';
    $('detail-status').textContent = '상세 리포트를 불러오는 중…';
    $('detail-title').focus();
    document.querySelectorAll('[data-date]').forEach(n => n.setAttribute('aria-current', String(n.dataset.date === r.date)));
    try {
      const [html, css] = await Promise.all([read('reports/daily/' + r.date + '.html', controller.signal), read('assets/style.css', controller.signal)]);
      if (session !== epoch || request !== selection) return;
      $('report-frame').srcdoc = isolatedReport(html, css);
      $('report-frame').hidden = false; $('detail-status').textContent = '비공개 개인 열람 · ' + r.date;
    } catch (error) {
      if (session !== epoch || request !== selection) return;
      $('detail-status').textContent = error.message + ' 날짜를 다시 선택해 주세요.';
    }
  }
  $('connect-form').addEventListener('submit', async event => {
    event.preventDefault();
    const entered = $('reader-token').value.trim();
    disconnect('비공개 목록을 연결하는 중…');
    if (!entered) return;
    token = entered; controller = new AbortController(); const session = epoch;
    $('connect-button').disabled = true;
    // Allow cancellation even while the first request is still pending.
    $('disconnect').hidden = false;
    try {
      const list = await loadIndex(controller.signal);
      if (session !== epoch) return;
      reports = list;
      [...new Set(reports.map(r => r.date.slice(0, 4)))].forEach(y => $('year').add(new Option(y, y)));
      $('connect-form').hidden = true; $('refresh').hidden = false;
      status('비공개 연결됨 · 이 탭에서만 열람합니다.'); render();
      if (new URLSearchParams(location.search).get('open') === 'latest' && reports.length) openReport(reports[0]);
    } catch (error) {
      if (session === epoch) disconnect(error.message);
    } finally { if (session === epoch) $('connect-button').disabled = false; }
  });
  $('disconnect').addEventListener('click', () => { disconnect(); $('reader-token').focus(); });
  $('refresh').addEventListener('click', async () => {
    const session = epoch; $('refresh').disabled = true;
    try {
      const list = await loadIndex(controller.signal);
      if (session !== epoch) return;
      reports = list;
      const selectedYear = $('year').value;
      $('year').replaceChildren(new Option('전체 연도', 'all'));
      [...new Set(list.map(r => r.date.slice(0, 4)))].forEach(y => $('year').add(new Option(y, y)));
      $('year').value = [...$('year').options].some(o => o.value === selectedYear) ? selectedYear : 'all';
      render(); status('최신 발행 목록을 불러왔습니다.');
    } catch (error) { if (session === epoch) status(error.message); }
    finally { $('refresh').disabled = false; }
  });
  $('close-detail').addEventListener('click', () => { closeDetail(); returnFocus?.focus(); });
  for (let m = 1; m <= 12; m++) $('month').add(new Option(m + '월', String(m).padStart(2, '0')));
  for (const id of ['search', 'year', 'month', 'market']) $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { if (token) render(); });
  window.addEventListener('pagehide', () => disconnect());
})();
