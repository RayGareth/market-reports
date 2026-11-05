// Presentation only: keep archived source text and all market observations intact.
(() => {
  function compactMarketSection() {
    const section=document.querySelector('article.report-article > section');
    if(!section||section.dataset.marketCompact)return;
    const statuses=[...section.querySelectorAll(':scope > p.report-status')];
    let notes=section.querySelector(':scope > details.market-source-notes');
    const ensureNotes=()=>{
      if(!notes){notes=document.createElement('details');notes.className='market-source-notes';
        const summary=document.createElement('summary');summary.textContent='출처·검증 정보';notes.append(summary);section.append(notes);}
      return notes;
    };
    const explanations=new Set();
    for(const p of statuses){
      const text=p.textContent.trim();
      if(text==='확정 종가·등락률: 공개 가능한 검증 자료가 아직 연결되지 않았습니다.'){
        explanations.add(text);p.textContent='자료 확인 대기';p.classList.add('market-region-pending');
      }else if(text==='코스피·코스닥 종목 분포: 공개 가능한 검증 자료가 있을 때 표시합니다.'){
        explanations.add(text);p.textContent='종목 분포 · 자료 확인 대기';
      }else if(/^(KOSPI|KOSDAQ|S&P 500|NASDAQ) · /.test(text)){
        ensureNotes().append(p); // Move the original date, cause and validation text without rewriting it.
      }
    }
    for(const text of explanations){const p=document.createElement('p');p.className='report-status';p.textContent=text;ensureNotes().append(p);}
    section.dataset.marketCompact='true';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',compactMarketSection,{once:true});
  else compactMarketSection();
})();
