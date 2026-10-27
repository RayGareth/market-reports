// Synthetic end-to-end fixture: no live market values, credentials, or private data.
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright':'playwright');
const fs=require('fs'),os=require('os'),path=require('path'),http=require('http'),assert=require('assert/strict'),{execFileSync}=require('child_process');
const root=path.resolve(__dirname,'..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'market-ui-'));
for(const name of ['index.html','assets','reports/index.html'])fs.cpSync(path.join(root,name),path.join(temp,name),{recursive:true});
execFileSync('python3',['-c',`
import sys
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(sys.argv[2])/'scripts'))
import build_public_reports as app
root=Path(sys.argv[1]);app.build(root,date(2026,10,23));app.build(root,date(2026,10,26))
rows=[]
for i,(id,name,region) in enumerate([('kospi','KOSPI','kr'),('kosdaq','KOSDAQ','kr'),('sp500','S&P 500','us'),('nasdaq','NASDAQ','us')]):
 rows.append({'id':id,'name':name,'region':region,'asOf':'2026-10-26' if region=='kr' else '2026-10-23','previousAsOf':'2026-10-23' if region=='kr' else '2026-10-22','close':float((i+1)*100+1),'changePct':1.0,'verified':True,'source':'https://example.invalid/synthetic-primary','verificationSource':'https://example.invalid/synthetic-check','publication':{'status':'approved_public','evidence':'https://example.invalid/test-license'}})
app.build(root,date(2026,10,26),market={'indices':rows,'marketStatus':[],'checkedAt':'2026-10-26T09:00:00+00:00'})
`,temp,root],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
const server=http.createServer((req,res)=>{let p=path.join(temp,req.url.split('?')[0]);if(p.endsWith('/'))p+='index.html';try{res.setHeader('Content-Type',p.endsWith('.js')?'application/javascript':p.endsWith('.json')?'application/json':p.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(p));}catch{res.statusCode=404;res.end();}});
(async()=>{await new Promise(r=>server.listen(8766,'127.0.0.1',r));const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});const results=[];
for(const width of [320,360,390,768,1280]){
 const context=await browser.newContext({viewport:{width,height:844},isMobile:width<600});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('https://fonts.googleapis.com/**',r=>r.abort());
 await page.goto('http://127.0.0.1:8766/');await page.waitForFunction(()=>document.querySelector('#market-metrics strong')?.textContent==='101.00');assert.match(await page.locator('#market-date-summary').innerText(),/국내: 2026-10-26 \/ 미국: 2026-10-23/);assert.equal(await page.locator('#market-source-notes .market-source-row').count(),4);assert.equal(await page.locator('#market-source-notes .market-source-row a').count(),8);assert.equal(await page.locator('#market-metrics a').count(),0);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('.quick-access-action').click();assert(page.url().endsWith('2026-10-26-r001.html'));assert.equal(await page.locator('.report-article>section').count(),4);assert.equal(await page.locator('.market-close-table tbody tr').count(),4);assert.equal(await page.locator('.market-source-notes .market-source-row').count(),4);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.match(await page.locator('.market-close-table').first().innerText(),/2026-10-26/);assert.match(await page.locator('.market-close-table').last().innerText(),/2026-10-23/);
 if(process.env.MARKET_SCREENSHOT_DIR){fs.mkdirSync(process.env.MARKET_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.MARKET_SCREENSHOT_DIR,`synthetic-market-${width}.png`),fullPage:true});}
 await page.getByRole('link',{name:'← 아카이브로 돌아가기'}).click();await page.locator('.report-row').first().waitFor();assert.equal(await page.locator('.report-row').count(),2);await page.locator('.report-row').first().click();assert(page.url().endsWith('2026-10-26-r001.html'));
 // Initial edition remains directly accessible.
 assert.equal((await page.goto('http://127.0.0.1:8766/reports/daily/2026-10-26.html')).status(),200);
 await page.route('**/data/public-market.json',r=>r.fulfill({status:503,body:'unavailable'}));await page.goto('http://127.0.0.1:8766/');await page.waitForFunction(()=>document.querySelectorAll('#market-metrics strong').length===4);assert.deepEqual(await page.locator('#market-metrics strong').allTextContents(),Array(4).fill('자료 확인 대기'));assert.deepEqual(errors,[]);results.push({width,regions:true,sourceLinks:true,revisionArchive:true,originalPreserved:true,missingNotice:true,noOverflow:true});await context.close();
}
await browser.close();server.close();fs.rmSync(temp,{recursive:true,force:true});console.log(JSON.stringify(results));})().catch(e=>{console.error(e);server.close();process.exit(1)});
