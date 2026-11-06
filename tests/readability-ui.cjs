// Public pending state and synthetic quotes only. No provider calls or private data.
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright':'playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),baseline=process.env.MARKET_BASELINE_DIR;
const out=process.env.MARKET_SCREENSHOT_DIR;let active=root;
const server=http.createServer((req,res)=>{
 const url=decodeURIComponent(req.url.split('?')[0]);
 const file=url.startsWith('/__fonts__/')&&process.env.MARKET_FONT_DIR?path.join(process.env.MARKET_FONT_DIR,url.slice(11)):path.join(active,url.endsWith('/')?url+'index.html':url);
 try{res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.json')?'application/json':file.endsWith('.css')?'text/css':file.endsWith('.woff2')?'font/woff2':'text/html');res.end(fs.readFileSync(file));}catch{res.statusCode=404;res.end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox','--disable-dev-shm-usage']});
 const entries=JSON.parse(fs.readFileSync(path.join(root,'reports/index.json'))),snapshot=JSON.parse(fs.readFileSync(path.join(root,'data/public-market.json')));
 const fontCSS=process.env.MARKET_FONT_DIR?[400,700,800].map(w=>fs.readFileSync(path.join(process.env.MARKET_FONT_DIR,'..',w+'.css'),'utf8').replaceAll('./files/','/__fonts__/')).join('\n'):'';
 if(out)fs.mkdirSync(out,{recursive:true});const results=[];
 for(const width of [320,360,390,768,1280]){
  const c=await browser.newContext({viewport:{width,height:844}});await c.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
  const p=await c.newPage();let errors=[];p.on('pageerror',e=>errors.push(e.message));await p.clock.install();
  async function visit(url){await p.goto(base+url);if(fontCSS){await p.addStyleTag({content:fontCSS});await p.evaluate(()=>document.fonts.ready);}}
  async function capture(name,selector){if(out&&width===390)await p.locator(selector).screenshot({path:path.join(out,name+'.png')});}
  if(baseline&&out&&width===390){active=baseline;await visit('/');await p.locator('.metric-pending').first().waitFor();await capture('dashboard-before','section[aria-labelledby=temperature]');await visit('/reports/'+entries[0].url);await capture('section-before','article.report-article > section:first-child');active=root;}
  await visit('/');await p.waitForFunction(()=>document.querySelectorAll('#market-metrics .metric-pending').length===4);
  assert.equal(await p.locator('#market-metrics .metric-change,#market-metrics .metric-date').count(),0);
  assert.deepEqual(await p.locator('#market-metrics strong').allTextContents(),Array(4).fill('자료 확인 대기'));
  assert.equal(await p.locator('#market-metrics .market-source-pending').count(),4);
  for(const s of snapshot.marketStatus)assert((await p.locator('#market-metrics').textContent()).includes(s.message));
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await capture('dashboard-after','section[aria-labelledby=temperature]');
  await p.locator('#market-metrics summary').first().click();assert(await p.locator('#market-metrics details').first().evaluate(n=>n.open));
  assert((await p.locator('#market-metrics summary').first().boundingBox()).height>=44);
  await p.clock.fastForward(60000);await p.waitForTimeout(100);assert(await p.locator('#market-metrics details').first().evaluate(n=>n.open));assert.equal(await p.locator('#market-metrics .market-source-pending').count(),4);
  await visit('/reports/'+entries[0].url);await p.waitForFunction(()=>document.querySelector('article.report-article > section').dataset.marketCompact==='true');
  const section=p.locator('article.report-article > section').first();assert.equal(await section.locator('h3').count(),2);assert.equal(await section.locator('.market-region-pending').count(),2);
  assert.equal(await section.locator('details').count(),1);assert.equal(await section.locator('details').evaluate(n=>n.open),false);
  for(const s of snapshot.marketStatus){assert((await section.locator('details').textContent()).includes(s.name));}
  await capture('section-after','article.report-article > section:first-child');assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  // A mixed response keeps causes separate and never turns expected dates into quotes.
  const mixed=structuredClone(snapshot);mixed.indices=[{id:'nasdaq',name:'NASDAQ',region:'us',asOf:'2026-10-29',close:123456.78,changePct:-12.34,closeAt:'2026-10-29T20:00:00Z',verifiedAt:'2026-10-30T00:00:00Z',source:'https://example.invalid/synthetic',verificationSource:'https://example.invalid/check',verified:true,publication:{status:'approved_public',evidence:'https://example.invalid/fixture'}}];
  mixed.marketStatus=mixed.marketStatus.map((s,i)=>({...s,status:['missing','provider_error','disagreement','missing'][i],message:['최근 자료 지연','수집 응답 오류','출처 간 수치 불일치','최신 거래일 자료 미도착'][i]}));
  mixed.marketStatus[3].expectedAsOf='2026-10-30';
  await p.route('**/data/public-market.json',r=>r.fulfill({json:mixed}));await visit('/');await p.waitForFunction(()=>document.querySelectorAll('#market-metrics .metric-change').length===1);
  const card=p.locator('#market-metrics .metric').last();assert.match(await card.innerText(),/123,456\.78[\s\S]*마감 10\.30 05:00 KST[\s\S]*−12\.34%[\s\S]*최신 거래일 검증 대기/);
  await card.locator('summary').click();
  assert.match(await card.locator('details').innerText(),/2026-10-29 \(ET\)/);
  assert.match(await card.locator('details').innerText(),/검증 완료 10\.30 09:00 KST/);
  assert.match(await card.locator('details').innerText(),/최신 거래일 자료 미도착/);
  const sizes=await card.evaluate(n=>['strong','.metric-change','.metric-date'].map(s=>parseFloat(getComputedStyle(n.querySelector(s)).fontSize)));assert(sizes[0]>sizes[1]&&sizes[1]>sizes[2]);assert(await card.locator('strong').evaluate(n=>n.scrollWidth<=n.clientWidth));
  assert.equal(await p.locator('#market-metrics .metric-pending').count(),3);assert.equal(await p.locator('#market-metrics .market-source-row').count(),4);
  for(const message of ['최근 자료 지연','수집 응답 오류','출처 간 수치 불일치'])assert((await p.locator('#market-metrics').textContent()).includes(message));
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);results.push({width,pendingCards:true,causesPreserved:true,disclosureRefresh:true,mixedQuoteFits:true,section01:true,noOverflow:true});await c.close();
 }
 await browser.close();server.close();console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);server.close();process.exit(1)});
