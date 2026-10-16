// 离线验收真实周增长、数据图点、筛选、链接和当日日榜；不访问网络。
const fs=require('fs'),assert=require('assert'),{JSDOM}=require('../.deps-js/node_modules/jsdom');
const filename=process.argv[2],expected=process.argv[3];
assert(filename&&expected,'需指定HTML路径及报告日期');
const html=fs.readFileSync(filename,'utf8'),errors=[];
const dom=new JSDOM(html,{runScripts:'dangerously',beforeParse(w){w.addEventListener('error',e=>errors.push(e.message))}}),d=dom.window.document;
assert.deepEqual(errors,[],'页面脚本执行失败');
assert(!/__DATA__|__SCRIPT__|__REPORT_NAME__|__REPORT_DATE_DISPLAY__/.test(html));
const data=dom.window.eval('DATA'),w=data.weekly_growth;
assert.equal(data.report_date,expected);assert.strictEqual(w.simulated,false);
assert.equal(d.title,'工具类APP热度趋势日报'+expected.replaceAll('-',''));
assert.equal(w.previous_days.length,7);assert.equal(w.current_days.length,7);
const prior=new Date(expected+'T00:00:00Z');prior.setUTCDate(prior.getUTCDate()-1);
assert.equal(data.daily_tables.business_date,prior.toISOString().slice(0,10));
assert.equal(w.days.at(-1),prior.toISOString().slice(0,10));
assert.equal(d.querySelectorAll('#growth').length,1);
assert(!/模拟数据|示意数据|综合结论|<h[23][^>]*>[^<]*结论/.test(html));
assert.equal(d.querySelectorAll('svg text').length,0);
assert.equal(w.dsp.default_threshold,20);assert.equal(w.dsp.default_baseline_top_pct,20);
assert.equal(d.getElementById('growth-threshold').value,'20');assert.equal(d.getElementById('growth-baseline').value,'20');
function link(cell,a){const el=cell.querySelector('a.app-link');assert(el);const u=new URL(el.href);assert.equal(u.origin,'https://play.google.com');assert.equal(u.pathname,'/store/apps/details');assert.equal(u.searchParams.get('id'),a.package);assert.equal(el.textContent,a.name);assert.equal(el.target,'_blank');assert(el.rel.includes('noopener')&&el.rel.includes('noreferrer'));assert(cell.textContent.includes(a.brief));}
function points(cell,observations){const actual=observations.filter(p=>p.value!=null),circles=[...cell.querySelectorAll('circle')];assert.equal(circles.length,actual.length);circles.forEach((c,i)=>{assert.equal(c.dataset.date,actual[i].date);assert.equal(Number(c.dataset.value),actual[i].value)});assert.equal(cell.querySelectorAll('svg text').length,0);}
const click=selector=>d.querySelector(selector).click();
const change=(id,v)=>{d.getElementById(id).value=v;d.getElementById(id).dispatchEvent(new dom.window.Event('change'));};
for(const [tab,key] of [['downloads','downloads'],['cost','buying_cost_usd'],['price','unit_price_usd']]){
 click(`[data-metric="${tab}"]`);
 if(d.getElementById('dsp-more').textContent.startsWith('展开'))click('#dsp-more');
 const apps=data.daily_tables.tables[key].rows,rows=[...d.querySelectorAll('#dsp-body tr')];assert.equal(rows.length,apps.length);assert(rows.length<=20);
 rows.forEach((r,i)=>{const a=apps[i];link(r.children[1],a);assert(!r.children[3].textContent.includes('.'));assert(/\.\d{4}$/.test(r.children[4].textContent));assert.equal(r.children[5].textContent,a.top20_counts['14']+'次');if(key!=='downloads')assert(a.downloads>=300);points(r.children[6],a.points);});
}
for(const scope of Object.keys(data.gp20_analysis.scopes)){
 change('gp-country',scope);const a=data.gp20_analysis.scopes[scope].apps.slice(0,20),rows=[...d.querySelectorAll('#gp-body tr:not(.empty-row)')];assert.equal(rows.length,a.length);
 rows.forEach((r,i)=>{link(r.children[1],a[i]);assert.equal(r.children[3].textContent,a[i].top20_days+'次');assert(a[i].top20_days<=20);points(r.children[6],a[i].points.map(p=>({date:p.date,value:p.trend_rank})));});
}
let growthCount=0;
for(const source of ['dsp','gp','ps']){
 click(`[data-source="${source}"]`);if(source==='gp'&&w.gp_appmagic)change('growth-gp-source','sensortower');assert.equal(d.getElementById('growth-country-label').hidden,source==='dsp');
 for(const scope of source==='dsp'?['all']:Object.keys(w[source].scopes)){
  if(source!=='dsp')change('growth-country',scope);
  const original=source==='dsp'?w.dsp:w[source].scopes[scope],threshold=w[source].default_threshold;
  const minimum=source==='dsp'?w.dsp.baseline_pool.cutoffs['20'].minimum_previous_usd:null;
  const a=original.rows.filter(r=>(source==='dsp'?r.growth_pct:r.gain)+1e-9>=threshold&&(source!=='dsp'||minimum!=null&&r.previous+1e-12>=minimum)).slice(0,10),rows=[...d.querySelectorAll('#growth-body tr:not(.empty-row)')];
  assert.equal(rows.length,a.length);assert(rows.length<=10);growthCount+=rows.length;
  rows.forEach((r,i)=>{link(r.children[1],a[i]);assert.equal(a[i].previous_days,7);assert.equal(a[i].current_days,7);assert(a[i].countries.length>0);points(r.children[source==='dsp'?6:7],a[i].points);assert.equal(a[i].points.length,14);if(source==='dsp'){assert.equal(r.children[2].textContent,Number(a[i].display.previous).toLocaleString('zh-CN'));assert.equal(r.children[3].textContent,Number(a[i].display.current).toLocaleString('zh-CN'));assert.equal(a[i].previous<1,!!r.querySelector('.badge.amber'));}else{assert(Math.abs(a[i].gain-(a[i].previous-a[i].current))<1e-8);assert.equal(r.children[6].textContent,'7天 / 7天');}});
  if(source==='dsp'){
   change('growth-baseline','10');const strict=w.dsp.baseline_pool.cutoffs['10'].minimum_previous_usd;
   const eligible=original.rows.filter(r=>r.growth_pct+1e-9>=threshold&&strict!=null&&r.previous+1e-12>=strict).slice(0,10);
   assert.equal(d.querySelectorAll('#growth-body tr:not(.empty-row)').length,eligible.length);
   change('growth-baseline','20');
   change('growth-threshold','10');
   const explored=original.rows.filter(r=>r.growth_pct+1e-9>=10&&minimum!=null&&r.previous+1e-12>=minimum).slice(0,10);
   const observed=[...d.querySelectorAll('#growth-body tr:not(.empty-row)')];assert.equal(observed.length,explored.length);
   observed.forEach((r,i)=>{link(r.children[1],explored[i]);points(r.children[6],explored[i].points);assert(explored[i].previous>=minimum);});
   growthCount+=observed.length;change('growth-threshold',String(threshold));
  }
 }
 if(source==='ps'&&!w.ps.scopes.all.complete_country_count){change('growth-country','all');assert(d.getElementById('growth-body').textContent.includes('周增长留空'));}
}
if(w.gp_appmagic){
 click('[data-source="gp"]');change('growth-gp-source','appmagic');
 const am=w.gp_appmagic,apps=am.scopes.all.rows.filter(a=>a.gain+1e-9>=10).slice(0,10),rows=[...d.querySelectorAll('#growth-body tr:not(.empty-row)')];
 assert.equal(d.getElementById('growth-country-label').hidden,true);assert.equal(rows.length,apps.length);assert(rows.length<=10);
 assert.equal(d.getElementById('previous-range').textContent,am.previous_days[0]+' — '+am.previous_days.at(-1));
 assert.equal(d.getElementById('current-range').textContent,am.current_days[0]+' — '+am.current_days.at(-1));
 assert(d.getElementById('growth-head').textContent.includes('榜单国家范围'));
 rows.forEach((r,i)=>{const a=apps[i];link(r.children[1],a);points(r.children[7],a.points);assert.equal(a.points.length,14);assert(a.points.every(p=>p.joint_rank===p.value&&!p.country_ranks));assert.equal(r.children[5].textContent,String(am.scopes.all.countries.length));assert(Math.abs(a.gain-(a.previous-a.current))<1e-8);});
 growthCount+=rows.length;
}
assert.equal(d.querySelectorAll('.palm table').length,0);
const bars=[...d.querySelectorAll('#palm-body .palm-row')];assert.equal(bars.length,data.palmstore_view.rows.length);
bars.forEach((b,i)=>{const a=data.palmstore_view.rows[i];link(b,a);assert.equal(Number(b.dataset.count),a.hot_count);assert.equal(b.querySelectorAll('.on').length,a.hot_count);assert.equal(b.querySelectorAll('.palm-bar span').length,13);if(i)assert(Number(bars[i-1].dataset.count)>=a.hot_count);});
assert(!html.includes('<script src=')&&!html.includes('fetch('));assert.equal(errors.length,0);
console.log(JSON.stringify({status:'通过',report_date:expected,weekly_rows_checked:growthCount,checks:'真实两周数据、固定国家、日榜门槛及精度、全部实际图点、国家筛选、GP链接、PS历史留空和13国进度条'}));
