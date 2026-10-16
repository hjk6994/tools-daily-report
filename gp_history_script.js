// 同一组实际国家日榜，分别展示热度指数和排名位置。
const HISTORY=DATA.gp_history,GP_STATES={heat:{count:10,days:7,selected:null,hidden:new Set()},rank:{count:10,days:7,selected:null,hidden:new Set()}};
$('gp-country').innerHTML='<option value="all">全部国家总榜（13国范围）</option>'+Object.entries(COUNTRY).map(([c,n])=>`<option value="${c}">${n}${HISTORY.missing_countries.includes(c)?'（缺榜）':''}</option>`).join('');
$('gp-history-method').textContent=HISTORY.method+' '+HISTORY.trend_scope_note;
for(const [metric,label] of [['heat','热度趋势'],['rank','排名位置变化']]){
 $('gp-history-panels').insertAdjacentHTML('beforeend',`<article class="metric-panel" id="gp-${metric}-panel"><h3>${label}</h3><div class="controls"><label>APP数量 <select id="gp-${metric}-count">${[5,6,7,8,9,10].map(n=>`<option value="${n}" ${n===10?'selected':''}>Top${n}</option>`).join('')}</select></label><label>日期 <select id="gp-${metric}-days"><option value="7">近7天</option><option value="14">近14天</option></select></label><button id="gp-${metric}-reset" class="reset">恢复所有曲线</button></div><p class="note">点击APP名称或曲线选中加粗；每张图可独立隐藏和恢复曲线。</p><div id="gp-${metric}-legend" class="legend"></div><div id="gp-${metric}-plot" class="chart"></div><p id="gp-${metric}-note" class="note"></p><details><summary>每日热度与排名数值</summary><div id="gp-${metric}-daily" class="scroll"></div></details></article>`);
}
function gpValue(p,metric,c){return metric==='heat'?p.heat_index:c==='all'?p.heat_rank:p.source_rank}
function gpPlot(metric,apps,points,days,c){
 const st=GP_STATES[metric],W=1200,H=355,L=90,R=28,T=27,B=55,rank=metric==='rank';
 const vals=points.flatMap((ps,i)=>st.hidden.has(apps[i].package)?[]:ps.map(p=>gpValue(p,metric,c)).filter(v=>v!=null));
 const maximum=rank?Math.max(10,...vals):Math.max(10,...vals)*1.08,X=i=>L+i*(W-L-R)/Math.max(days.length-1,1),Y=v=>rank?T+(v-1)/(maximum-1)*(H-T-B):H-B-v/maximum*(H-T-B);
 let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="GP${rank?'排名位置变化':'热度趋势'}"><text x="${L}" y="15">${rank?(c==='all'?'总榜名次（越小越靠前）':'原榜名次（越小越靠前）'):'Top10热度指数'}</text>`;
 const ticks=rank?[...new Set([0,1,2,3,4].map(j=>Math.round(1+(maximum-1)*j/4)))]:[0,1,2,3,4].map(j=>maximum*j/4);
 ticks.forEach(v=>svg+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#e1e8ee"/><text x="${L-12}" y="${Y(v)+4}" text-anchor="end">${fmt(v,rank?0:1)}</text>`);
 days.forEach((d,i)=>svg+=`<text x="${X(i)}" y="${H-27}" text-anchor="middle">${d.slice(5)}</text>`);
 apps.forEach((a,i)=>{if(st.hidden.has(a.package))return;let segments=[],segment='';points[i].forEach((p,j)=>{let v=gpValue(p,metric,c);if(v==null){if(segment)segments.push(segment);segment=''}else segment+=(segment?' L':'M')+X(j)+' '+Y(v)});if(segment)segments.push(segment);
  const chosen=st.selected===a.package;svg+=`<g class="gp-series ${chosen?'selected':''}" data-gp-select="${esc(a.package)}" opacity="${st.selected && !chosen ? 0.28 : 1}">`;
  segments.forEach(d=>svg+=`<path d="${d}" fill="none" stroke="${a.color}" stroke-width="${chosen?5:2.2}"/><path d="${d}" fill="none" stroke="transparent" stroke-width="15"/>`);
  points[i].forEach((p,j)=>{let v=gpValue(p,metric,c);if(v!=null)svg+=`<circle cx="${X(j)}" cy="${Y(v)}" r="${chosen?4.8:3}" fill="${a.color}" data-date="${p.date}" data-value="${v}"><title>${esc(a.name)} · ${esc(a.brief)} · ${p.date} · ${rank?'第'+v+'名':'热度指数'+fmt(v,2)} · ${p.status==='outside_observed_top10'?'未进入已取得Top10，实际商店名次未知':'积分'+fmt(p.score)}</title></circle>`});svg+='</g>';
 });return svg+`<text x="${W/2}" y="${H-4}" text-anchor="middle">已显示${apps.filter(a=>!st.hidden.has(a.package)).length}/${apps.length}款APP · 榜单日期</text></svg>`;
}
function renderGPTrend(metric){
 const c=$('gp-country').value,st=GP_STATES[metric],date=HISTORY.anchor_dates[c],apps=HISTORY.rankings[c][date].slice(0,st.count),days=HISTORY.days.slice(-st.days),points=apps.map(a=>HISTORY.series[c][a.package].filter(p=>days.includes(p.date)));
 $(`gp-${metric}-legend`).innerHTML=apps.map(a=>`<div class="legend-row ${st.selected===a.package?'chosen':''} ${st.hidden.has(a.package)?'hidden-app':''}"><span class="swatch" style="background:${a.color}"></span><button class="legend-name" data-gp-select="${esc(a.package)}" aria-pressed="${st.selected===a.package}">${c==='all'?a.heat_rank:a.positions[c]}. ${esc(a.name)}<small>${esc(a.subclass)} · ${esc(a.brief)}</small></button><button class="legend-hide" data-gp-hide="${esc(a.package)}">${st.hidden.has(a.package)?'显示':'隐藏'}</button></div>`).join('');
 $(`gp-${metric}-plot`).innerHTML=apps.length?gpPlot(metric,apps,points,days,c):'<div class="empty">未取得该国日榜，热度和排名趋势不可用。</div>';
 $(`gp-${metric}-note`).textContent=`固定展示${date}的工具Top${st.count}，实际${apps.length}款。`+(metric==='rank'?(c==='all'?'纵轴为同日跨国工具热度总榜名次，第1名在顶部。':'纵轴为来源工具免费榜原始名次，第1名在顶部。'):'每个点为该日Top10排名积分计算的热度指数，不是下载数量。')+' 缺榜日期留空；未进入已取得Top10时，Top10热度指数为0、实际商店名次未知。';
 $(`gp-${metric}-daily`).innerHTML=table(['日期','APP','热度指数','Top10积分',c==='all'?'总榜名次':'原榜名次','数据状态'],days.flatMap((d,j)=>apps.map((a,i)=>{let p=points[i][j];return [d,esc(a.name),fmt(p.heat_index,2),fmt(p.score),fmt(c==='all'?p.heat_rank:p.source_rank),p.status==='observed'?'已观测':p.status==='outside_observed_top10'?'未进入已取得Top10；实际名次未知':'缺榜']})));
}
function renderGPHistory(){
 const c=$('gp-country').value,date=HISTORY.anchor_dates[c],apps=HISTORY.rankings[c][date].slice(0,10),leader=apps[0];
 $('gp-history-summary').textContent=c==='all'?`${date} · 13国指定范围中，${HISTORY.countries.length}国完整覆盖14天，共${HISTORY.complete_chart_count}份原始Top10日榜。${HISTORY.missing_countries.map(c=>COUNTRY[c]).join('、')}未取得日榜，不计入热度分母。${leader.name}排名第1，热度指数${fmt(leader.heat_index,2)}，在${leader.country_count}国进入Top10，出现平均名次${fmt(leader.mean_appearing_rank,2)}。`:`${COUNTRY[c]} · ${date} · ${apps.length?'表内为已核验用途的工具APP，保留来源工具免费榜原始名次。':'未取得日榜，不能判断未上榜。'}`;
 $('gp-history-table').innerHTML=apps.length?table([c==='all'?'总榜名次':'原榜名次','APP与用途','热度指数','Top10积分','出现国家数','出现平均名次','国家与原榜名次'],apps.map(a=>[c==='all'?a.heat_rank:a.positions[c],appCell(a),fmt(a.heat_index,2),fmt(a.score),a.country_count,fmt(a.mean_appearing_rank,2),esc(Object.entries(a.positions).map(([c,r])=>COUNTRY[c]+' '+r+'名').join('；'))])):'<div class="empty">来源缺榜。</div>';
 for(const metric of ['heat','rank'])renderGPTrend(metric);
}
for(const metric of ['heat','rank']){
 for(const key of ['count','days'])$(`gp-${metric}-${key}`).addEventListener('change',e=>{GP_STATES[metric][key]=Number(e.target.value);renderGPTrend(metric)});
 $(`gp-${metric}-reset`).addEventListener('click',()=>{GP_STATES[metric].hidden.clear();GP_STATES[metric].selected=null;renderGPTrend(metric)});
 $(`gp-${metric}-panel`).addEventListener('click',e=>{const hide=e.target.closest('[data-gp-hide]'),pick=e.target.closest('[data-gp-select]'),st=GP_STATES[metric];if(hide){let p=hide.dataset.gpHide;st.hidden.has(p)?st.hidden.delete(p):st.hidden.add(p);if(st.selected===p)st.selected=null;renderGPTrend(metric)}else if(pick){let p=pick.dataset.gpSelect;st.hidden.delete(p);st.selected=st.selected===p?null:p;renderGPTrend(metric)}});
}
$('gp-country').addEventListener('change',()=>{for(const st of Object.values(GP_STATES)){st.selected=null;st.hidden.clear()}renderGPHistory()});renderGPHistory();
$('gp-history-coverage').innerHTML=table(['榜单日期',...Object.values(COUNTRY)],HISTORY.days.map(d=>[d,...Object.keys(COUNTRY).map(c=>{let row=HISTORY.coverage.find(a=>a.country===c&&a.date===d);return row.status==='complete_top10'?`<a href="${esc(row.url)}" target="_blank" rel="noreferrer">已取得Top10</a>`:'缺榜'})]));
