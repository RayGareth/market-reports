(() => {
  async function refreshLatest() {
  try {
    const response = await fetch('reports/index.json', {cache: 'no-cache'});
    if (!response.ok) throw Error('Archive unavailable');
    const entries = await response.json();
    const latest = entries.filter(r => r.status === 'published' && /^daily\/20\d{2}-\d{2}-\d{2}(?:-r\d{3})?\.html$/.test(r.url)).sort((a,b) => b.date.localeCompare(a.date))[0];
    if (!latest) return;
    for (const [id, value] of Object.entries({'latest-date': latest.date + ' / 공개 학습판', 'latest-title': latest.title, 'latest-summary': latest.summary})) {
      const n = document.getElementById(id); if (n) n.textContent = value;
    }
    for (const link of document.querySelectorAll('#latest-link,.quick-access-action')) link.href = 'reports/' + latest.url;
  } catch { /* reports/latest.html remains a working, prebuilt fallback. */ }
  }
  refreshLatest();
  setInterval(refreshLatest, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshLatest(); });
})();
