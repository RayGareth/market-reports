// End-to-end checks use only public study files; no credentials or private fixtures.
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright' : 'playwright');
const fs=require('fs'), http=require('http'), path=require('path'), assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const server=http.createServer((req,res)=>{
  let file=path.join(root,decodeURIComponent(req.url.split('?')[0]));
  if(file.endsWith('/'))file+='index.html';
  try {res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.json')?'application/json':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));}
  catch{res.statusCode=404;res.end('Not found');}
});
(async()=>{
 await new Promise(r=>server.listen(8765,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
 const entries=JSON.parse(fs.readFileSync(path.join(root,'reports/index.json')));
 const results=[];
 for(const width of [320,360,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:844},isMobile:width<600});
  const page=await context.newPage();const errors=[],missing=[],privateRequests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()===404)missing.push(r.url())});
  page.on('request',r=>{if(/api.github.com|market-reports-private/.test(r.url()))privateRequests.push(r.url())});
  await page.route('https://fonts.googleapis.com/**',r=>r.abort());
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForFunction(()=>document.querySelector('.quick-access-action').getAttribute('href').startsWith('reports/daily/'));
  assert.equal(await page.locator('#market-metrics .metric').count(),4);
  assert.equal(await page.locator('input[type=password]').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'dashboard overflow '+width);
  await page.locator('.quick-access-action').click();
  assert(page.url().endsWith(entries[0].url));
  assert.equal(await page.locator('.report-article > section').count(),4);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'detail overflow '+width);
  const answer=await page.locator('#market-quiz').getAttribute('data-answer');
  await page.locator(`input[value="${answer}"]`).check();await page.getByRole('button',{name:'정답 확인'}).click();
  assert.match(await page.locator('#quiz-feedback').innerText(),/정답이야/);
  await page.getByRole('button',{name:'다시 풀기'}).click();assert(await page.locator('#quiz-feedback').isHidden());
  const wrong=String((Number(answer)+1)%3);await page.locator(`input[value="${wrong}"]`).check();await page.getByRole('button',{name:'정답 확인'}).click();
  assert.match(await page.locator('#quiz-feedback').innerText(),/정답은/);
  if(process.env.MARKET_SCREENSHOT_DIR){fs.mkdirSync(process.env.MARKET_SCREENSHOT_DIR,{recursive:true});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(process.env.MARKET_SCREENSHOT_DIR,`public-detail-${width}.png`),fullPage:true});}
  await page.getByRole('link',{name:'← 아카이브로 돌아가기'}).click();
  await page.locator('.report-row').first().waitFor();assert.equal(await page.locator('.report-row').count(),entries.length);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'archive overflow '+width);
  await page.locator('#search').fill(entries[1].date);assert.equal(await page.locator('.report-row').count(),1);
  await page.locator('.report-row').click();assert(page.url().endsWith(entries[1].url));
  await page.goBack();await page.locator('.report-row').first().waitFor();await page.locator('#search').fill('no-matching-note');assert(await page.locator('#no-results').isVisible());
  await page.locator('#search').fill('');await page.locator('#year').selectOption('2026');await page.locator('#month').selectOption('10');assert.equal(await page.locator('.report-row').count(),entries.length);
  await page.locator('#month').selectOption('01');assert.equal(await page.locator('.report-row').count(),0);assert(await page.locator('#no-results').isVisible());
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  assert.deepEqual(errors,[]);assert.deepEqual(missing,[]);assert.deepEqual(privateRequests,[]);
  results.push({width,rows:entries.length,sections:4,quiz:true,search:true,noOverflow:true,credentials:false});await context.close();
 }
 // All dates resolve, contain only four sections, and have working relative assets.
 const page=await browser.newPage();
 for(const entry of entries){const r=await page.goto('http://127.0.0.1:8765/reports/'+entry.url);assert.equal(r.status(),200);assert.equal(await page.locator('.report-article > section').count(),4);}
 const nojs=await browser.newContext({javaScriptEnabled:false});const fallback=await nojs.newPage();await fallback.goto('http://127.0.0.1:8765/');await fallback.locator('.quick-access-action').click();assert(fallback.url().endsWith('/reports/latest.html'));assert.equal(await fallback.locator('.report-article > section').count(),4);await fallback.getByRole('link',{name:'← 아카이브로 돌아가기'}).click();assert(fallback.url().endsWith('/reports/'));
 await nojs.close();await browser.close();server.close();console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);server.close();process.exit(1)});
