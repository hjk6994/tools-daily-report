// 同日榜单按包名对应；界面保留两来源的独立名次。
const GP=DATA.gp_magic,SENSOR=DATA.gp_sensor,COMPARE=DATA.gp_comparison;
const missingGP=new Set(GP.statuses.filter(a=>a.status!=='complete_top10').map(a=>a.country));
const missingSensor=new Set(SENSOR.statuses.filter(a=>a.status!=='complete_top10').map(a=>a.country));
$('gp-summary').textContent=COMPARE.conclusion;
$('gp-insights').innerHTML='<ul>'+COMPARE.insights.map(a=>'<li>'+esc(a)+'</li>').join('')+'</ul>';
$('gp-compare-country').innerHTML=Object.entries(COUNTRY).map(([c,name])=>`<option value="${c}">${name}${missingGP.has(c)&&missingSensor.has(c)?'（两源缺数）':missingGP.has(c)?'（Sensor Tower可用）':''}</option>`).join('');
function sourceTable(chart){return chart?table(['名次','APP与用途','主用途'],chart.rows.map(a=>[a.rank,`<a href="${esc(a.source_url)}" target="_blank" rel="noreferrer">${esc(a.name)}</a><small class="purpose">${esc(a.brief)}</small>`,esc(a.subclass)])):'<div class="empty">来源未提供该国榜单。</div>'}
function renderGP(){let c=$('gp-compare-country').value,am=GP.charts.find(a=>a.country===c),st=SENSOR.charts.find(a=>a.country===c),check=COMPARE.countries.find(a=>a.country===c);
 $('gp-country-status').innerHTML=`${COUNTRY[c]} · ${GP.date} · Google Play · `+(check.comparable?`两来源Top10共同${check.overlap_count}款（${fmt(check.overlap_ratio*100)}%）；按包名对应。`:'当前未取得两份同日榜单，不能进行两源对比。')+(c==='CD'?' Sensor Tower仅提供刚果共和国CG，不替代刚果民主共和国CD。':'');
 $('gp-table').innerHTML=sourceTable(am);$('gp-sensor-table').innerHTML=sourceTable(st);
 $('gp-am-link').innerHTML=am?`<a href="${esc(am.url)}" target="_blank" rel="noreferrer">AppMagic原筛选页面</a>`:'AppMagic国家选择器未提供';
 let unavailable=SENSOR.missing_countries.find(a=>a.country===c);
 $('gp-st-link').innerHTML=st?`<a href="${esc(st.url)}" target="_blank" rel="noreferrer">Sensor Tower原筛选页面</a>`:unavailable?.url?`<a href="${esc(unavailable.url)}" target="_blank" rel="noreferrer">Sensor Tower同日筛选页面：无可显示的每日排行榜</a>`:'Sensor Tower未取得该国榜单';
 let common=COMPARE.common_apps.filter(a=>a.country===c);$('gp-common-table').innerHTML=check.comparable?table(['共同APP与用途','AppMagic名次','Sensor Tower名次','Sensor−AppMagic名次'],common.sort((a,b)=>a.appmagic_rank-b.appmagic_rank).map(a=>[appCell(a),a.appmagic_rank,a.sensor_rank,a.sensor_minus_appmagic])):'<p class="note">共同APP对照不可用。</p>';
}
renderGP();$('gp-compare-country').addEventListener('change',renderGP);
$('gp-bars').innerHTML=bars(GP.frequency.slice(0,10),GP.charts.length);
$('gp-common-bars').innerHTML=bars(COMPARE.common_frequency.slice(0,10),COMPARE.countries.filter(a=>a.comparable).length);
$('gp-heatmap').innerHTML=heatmap(GP.frequency,10,missingGP);
$('gp-overlap-table').innerHTML=table(['国家','AppMagic前10项数','Sensor Tower前10项数','共同APP数','共同占Top10'],COMPARE.countries.map(a=>[COUNTRY[a.country],a.appmagic_count,a.sensor_count,a.comparable?a.overlap_count:'不可比',a.comparable?fmt(a.overlap_ratio*100)+'%':'不可比']));
$('gp-status-table').innerHTML=table(['国家','AppMagic','Sensor Tower','榜单日期'],Object.entries(COUNTRY).map(([c,n])=>{let am=GP.charts.find(a=>a.country===c),st=SENSOR.charts.find(a=>a.country===c),missing=SENSOR.missing_countries.find(a=>a.country===c);return [n,am?`<a href="${esc(am.url)}" target="_blank" rel="noreferrer">已获取Top10</a>`:'国家选择器未提供',st?`<a href="${esc(st.url)}" target="_blank" rel="noreferrer">已获取Top10</a>`:missing?.url?`<a href="${esc(missing.url)}" target="_blank" rel="noreferrer">此筛选条件无榜单${c==='CD'?'；CG不替代CD':''}</a>`:'未取得榜单',GP.date]}));
