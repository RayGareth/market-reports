// No screenshots, external requests, trace, values or exception text in output.
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright':'playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict');
const roots=process.argv.slice(2);let active=roots[0],browser;
const server=http.createServer((req,res)=>{
 const file=path.resolve(active,'.'+decodeURIComponent(req.url.split('?')[0]));
 if(file!==active&&!file.startsWith(active+path.sep)){res.writeHead(403);return res.end();}
 const p=req.url.split('?')[0].endsWith('/')?path.join(file,'index.html'):file;
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex, nofollow');
 res.setHeader('Content-Type',p.endsWith('.js')?'application/javascript':p.endsWith('.json')?'application/json':p.endsWith('.css')?'text/css':'text/html');
 try{res.end(fs.readFileSync(p));}catch{res.writeHead(404);res.end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox','--disable-dev-shm-usage']});
 const results=[];
 for(const width of [320,360,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:844}});
  await context.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
  const page=await context.newPage();await page.clock.install();let errors=0;page.on('pageerror',()=>errors++);
  let first=true;
  for(const root of roots){
   active=root;const data=JSON.parse(fs.readFileSync(path.join(root,'data/public-market.json')));
   if(first){await page.goto(base);first=false;}else{await page.clock.fastForward(60000);}
   await page.waitForFunction(()=>document.querySelectorAll('#market-metrics strong').length===4);
   // A new checkedAt proves that the timer fetched the next snapshot without
   // navigating or manually reloading the dashboard.
   await page.waitForFunction(stamp=>document.querySelector('#market-date-summary').textContent.includes(new Date(stamp).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})),data.checkedAt);
   assert.equal(await page.locator('#usage-notice').count(),1);
   assert((await page.locator('body').innerText()).includes('비공개 연결 검증'));
   for(const [i,id] of ['kospi','kosdaq','sp500','nasdaq'].entries()){
    const row=data.indices.find(r=>r.id===id),card=page.locator('#market-metrics .metric').nth(i);
    assert.equal(await card.locator('strong').innerText(),row?row.close.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'자료 확인 대기');
    if(row){assert((await card.innerText()).includes(row.asOf));assert((await card.innerText()).includes(row.changePct.toFixed(2)+'%'));assert.equal(await card.locator('a').count(),row.verificationSource?2:1);assert((await card.innerText()).includes(row.verified?'교차 검증 완료':'단일 출처 검증 · 교차 검증 대기'));}
   }
   const latest=JSON.parse(fs.readFileSync(path.join(root,'reports/index.json')))[0];
   await page.waitForFunction(u=>document.querySelector('.quick-access-action').getAttribute('href')==='reports/'+u,latest.url);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   // Retain the live dashboard while opening a dated snapshot in another tab.
   const detail=await context.newPage();await detail.goto(base+'/reports/'+latest.url);assert.equal(await detail.locator('.report-article>section').count(),4);
   assert.equal(await detail.locator('#usage-notice').count(),1);
   const rows=detail.locator('.market-close-table tbody tr');assert.equal(await rows.count(),data.indices.length);
   for(const row of data.indices){const tableRow=rows.filter({hasText:row.name});assert((await tableRow.innerText()).includes(row.close.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})));assert((await tableRow.innerText()).includes(row.changePct.toFixed(2)+'%'));assert((await tableRow.innerText()).includes(row.asOf));}
   const form=detail.locator('#market-quiz');await form.locator('input').first().check();await form.locator('button[type=submit]').click();assert(await detail.locator('#quiz-feedback').isVisible());
   assert(await detail.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await detail.getByRole('link',{name:'← 아카이브로 돌아가기'}).click();await detail.locator('.report-row').first().waitFor();await detail.locator('.report-row').first().click();assert(detail.url().endsWith(latest.url));await detail.close();
  }
  assert.equal(errors,0);results.push({width,rounds:roots.length,automaticRefreshWithoutReload:roots.length>1,displayedRows:roots.map(r=>JSON.parse(fs.readFileSync(path.join(r,'data/public-market.json'))).indices.map(i=>({id:i.id,crossVerified:i.verified}))),notice:true,links:true,quiz:true,noOverflow:true});
  await context.close();
 }
 console.log(JSON.stringify({status:'passed',viewports:results}));
})().catch(()=>{console.log('{"status":"failed_redacted"}');process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.close();});
