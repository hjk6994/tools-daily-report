// 三份DSP当日Top20独立排序；历史窗口只影响对应榜单出现次数与行内小图。
const P=DATA.period_analysis,D=DATA.daily_tables,G=DATA.gp20_analysis,$=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=(v,n=0)=>v==null?'数据不足':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:n,maximumFractionDigits:n}),COUNTRY={PK:'巴基斯坦',IN:'印度',NG:'尼日利亚',ID:'印度尼西亚',BD:'孟加拉国',PH:'菲律宾',CI:'科特迪瓦',IQ:'伊拉克',RU:'俄罗斯',SY:'叙利亚',SA:'沙特阿拉伯',CD:'刚果民主共和国',BF:'布基纳法索'};
const SPECS=[['downloads','日下载','次',0,'#1769aa'],['buying_cost_usd','日买量成本','美元',0,'#238b45'],['unit_price_usd','日单价','美元/下载',4,'#a84b9b']];
function table(head,rows,caption=''){return '<table class="rank-table">'+(caption?'<caption>'+esc(caption)+'</caption>':'')+'<thead><tr>'+head.map(v=>'<th>'+esc(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map((v,i)=>'<td'+(i===r.length-1&&String(v).startsWith('<svg')?' class="spark-cell"':'')+'>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function appName(a){
 const name=esc(a.name),packageId=String(a.package??'');
 if(!/^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$/.test(packageId))return name;
 return `<a class="app-link" data-package="${esc(packageId)}" href="https://play.google.com/store/apps/details?id=${encodeURIComponent(packageId)}" target="_blank" rel="noopener noreferrer">${name}</a>`;
}
function app(a){return '<b>'+appName(a)+'</b><span class="purpose">'+esc(a.subclass)+' · '+esc(a.brief)+'</span>'}
function conclusions(id,rows){$(id).innerHTML='<ul>'+rows.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ul>'}
function spark(a,points,field,label,unit,precision,color,rankScale=false){
 let values=points.map(p=>p[field]).filter(v=>v!=null),maximum=Math.max(0.000001,...values)*1.08,rankMax=Math.max(20,...values),W=180,H=64,L=7,R=7,T=8,B=8,X=i=>L+i*(W-L-R)/Math.max(1,points.length-1),Y=v=>rankScale?T+(v-1)/(rankMax-1)*(H-B-T):H-B-v/maximum*(H-B-T),segments=[],segment='';
 const accessible=`${a.name} · ${label} · ${points[0]?.date}至${points.at(-1)?.date} · ${unit} · ${values.length}/${points.length}天有值`;
 let s=`<svg class="spark" role="img" data-package="${esc(a.package)}" data-metric="${field}" data-rank-scale="${rankScale}" aria-label="${esc(accessible)}" viewBox="0 0 ${W} ${H}"><title>${esc(accessible)}；${rankScale?'名次越小越靠上；所有实际名次均绘点，没有名次记录的日期断线':'缺数断线，纵轴从零起按本APP数值自适应'}</title>`;
 if(!values.length)return s+`<text x="90" y="29" text-anchor="middle">数据不足</text></svg>`;
 points.forEach((p,i)=>{if(p[field]==null){if(segment)segments.push(segment);segment=''}else segment+=(segment?' L':'M')+X(i)+' '+Y(p[field])});if(segment)segments.push(segment);
 segments.forEach(d=>s+=`<path d="${d}" fill="none" stroke="${color}" stroke-width="1.8"/>`);
 points.forEach((p,i)=>{if(p[field]!=null){const detail=rankScale?' · '+Object.entries(p.country_ranks||{}).map(([c,r])=>(COUNTRY[c]||c)+'第'+r+'名').join('、')+' · 当日已取得'+p.available_country_count+'国日榜':'';s+=`<circle cx="${X(i)}" cy="${Y(p[field])}" r="2" fill="${color}" data-date="${p.date}" data-value="${p[field]}"><title>${p.date} · ${esc(label)} ${fmt(p[field],precision)} ${esc(unit)}${esc(detail)}${!rankScale&&p.rank!=null?' · 本榜第'+p.rank+'名':''}</title></circle>`}else s+=`<rect x="${X(i)-3}" y="${H-B-3}" width="6" height="6" fill="transparent" data-missing-date="${p.date}"><title>${p.date} · ${esc(p.status||'数据不足')}</title></rect>`});
 return s+'</svg>';
}
$('gp-country').innerHTML='<option value="all">全部国家总榜（固定11国；SY、CD缺榜）</option>'+Object.entries(COUNTRY).map(([c,n])=>`<option value="${c}">${n}${['SY','CD'].includes(c)?'（缺榜）':''}</option>`).join('');
function dspTables(n){
 const window=D.history_windows[n];$('dsp-definitions').textContent=`${D.business_date}当日数据，非日均、非累计。日下载=resp；日买量成本=原始金额÷1000美元；日单价=当日金额÷当日下载。三个榜分别排序；成本榜和单价榜先筛日下载≥300。金额四舍五入显示整数，单价四舍五入保留4位，计算和排序仍用原值；历史次数按各日进入本榜Top20计数。缺APP行的小图断线。`;
 $('dsp-tables').innerHTML=SPECS.map(([metric,label,unit,precision,color])=>{
  const rows=D.tables[metric].rows;
  return `<article id="${metric}-panel"><h3>${label} Top20</h3><div id="${metric}-table" class="scroll">`+(rows.length?table(['当日名次','APP与用途','日下载（次）','日买量成本（美元）','日单价（美元/下载）',`近${n}天进入本榜Top20次数`,'数据趋势'],rows.map(a=>[a.rank,app(a),fmt(a.downloads),fmt(a.display.buying_cost_usd,0),fmt(a.display.unit_price_usd,4),`${a.top20_counts[n]}次`,spark(a,a.points.filter(p=>window.days.includes(p.date)),'value',label,unit,precision,color)]),`${D.business_date} · 本榜按${label}降序${metric==='downloads'?'':'，日下载≥300'}；历史${window.days[0]}至${window.days.at(-1)}，已观测榜单${window.available_days.length}/${n}天${window.missing_days.length?'，缺日'+window.missing_days.join('、'):''}；行内小图为${label}每日实际值。`):'<p class="status">前一天榜单缺数，不用更早日期替代。</p>')+'</div></article>'
 }).join('');
}
function gpTable(){let scope=$('gp-country').value,w=G.scopes[scope],days=G.days;
 const coverage=`Sensor Tower · GP工具免费下载Top20 · ${days[0]}至${days.at(-1)}（20天） · ${scope==='all'?`已取得${w.observed_country_days}/220份国榜，11国全齐${w.available_days.length}/20天；逐国日均热度等权合成，次数为进入任一国家原Top20的日期数，同日跨国只计1次`:`已取得完整日榜${w.available_days.length}/20天，次数为进入该国原Top20的日期数`}${w.missing_days.length?'；数据不足，'+(scope==='all'?'11国未全齐日期':'缺该国日榜日期')+w.missing_days.join('、'):''}；展示${Math.min(20,w.apps.length)}款已核验工具。${w.complete?'20天数据完整':'次数为已观察下限，期间排序为临时排名'}；小图为${scope==='all'?'当天有名次记录国家的原榜平均名次，参与国家可变':'每日原榜名次'}，包括已取得的20名后记录；名次越小越靠上，仅无实际名次的日期断线，悬停查看日期及国家名次；排名积分不是下载量。`;
 $('gp-period-table').innerHTML=w.apps.length?table(['20天期间名次','APP与用途','平均榜单热度','20天原榜Top20出现次数','覆盖国家','出现平均原榜名次','数据趋势'],w.apps.slice(0,20).map(a=>[a.period_rank,app(a),fmt(a.mean_heat,2),`${a.top20_days}次`,a.country_count,fmt(a.mean_appearing_rank,2),spark(a,a.points,'trend_rank',scope==='all'?'每日有记录国家平均名次':'每日原榜名次','名',scope==='all'?2:0,'#1769aa',true)]),coverage):'<p class="status">'+esc(coverage)+'。该范围缺榜，期间热度和趋势不可用，不能视为零下载或未上榜。</p>';
}
function main(){let n=$('main-window').value,w=P.windows[n],dw=D.history_windows[n];
 $('date-note').textContent=`报告日期${DATA.report_date} · DSP当日榜：${D.business_date}（UTC业务日） · PalmStore快照：${DATA.ps_observation_date}`;
 $('coverage').textContent=`DSP历史近${n}天已观测榜单${dw.available_days.length}/${n}天；GP固定20天，已取得${G.scopes.all.observed_country_days}/220份11国日榜，排名记录覆盖${G.scopes.all.trend_available_days.length}/20天；小图按APP实际名次记录绘制，SY/CD缺榜${G.scopes.all.complete?'':'，20天数据不足'}；PalmStore只有1次观察，7/14天趋势不足。`;
 dspTables(n);gpTable();
}
$('main-window').addEventListener('change',main);$('gp-country').addEventListener('change',gpTable);
const ps=DATA.palmstore_view.rows;$('ps-bars').innerHTML=ps.map(a=>`<div class="bar" data-package="${esc(a.package)}" data-count="${a.hot_count}"><span>${app(a)}</span><div class="track" role="progressbar" aria-label="${esc(a.name)}热门次数" aria-valuemin="0" aria-valuemax="13" aria-valuenow="${a.hot_count}"><div class="fill" style="width:${a.hot_count/13*100}%"></div></div><b>${a.hot_count}/13</b></div>`).join('');$('functions').innerHTML=table(['APP','用途','简要说明'],DATA.app_functions.map(a=>[appName(a),esc(a.subclass),esc(a.brief)]));$('method').textContent=D.cost_mapping+' '+D.price_rule+' '+D.count_rule;main();
