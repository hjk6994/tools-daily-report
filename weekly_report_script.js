// 周增长与日体量分开；所有绘点都来自嵌入的真实复算记录。
const W=DATA.weekly_growth,D=DATA.daily_tables,G=DATA.gp20_analysis,$=id=>document.getElementById(id);
const COUNTRY={PK:'巴基斯坦',IN:'印度',NG:'尼日利亚',ID:'印度尼西亚',BD:'孟加拉国',PH:'菲律宾',CI:'科特迪瓦',IQ:'伊拉克',RU:'俄罗斯',SY:'叙利亚',SA:'沙特阿拉伯',CD:'刚果民主共和国',BF:'布基纳法索'};
const state={source:'dsp',country:{gp:'all',ps:'all'},threshold:{dsp:W.dsp.default_threshold??20,gp:W.gp.default_threshold??10,ps:W.ps.default_threshold??5},gpProvider:W.gp_appmagic?.scopes.all.complete_window?'appmagic':'sensortower',baseline:W.dsp.default_baseline_top_pct??20,metric:'downloads',expanded:false,gpDetail:'all'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,n=0)=>v==null?'—':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:n,maximumFractionDigits:n});
function appLink(a){return `<a class="app-link" data-package="${esc(a.package)}" href="https://play.google.com/store/apps/details?id=${encodeURIComponent(a.package)}" target="_blank" rel="noopener noreferrer">${esc(a.name)}</a>`}
function appCell(a){return `<div class="app-cell">${appLink(a)}<span class="minor">${esc(a.subclass)} · ${esc(a.brief)}</span></div>`}
function weeklyCost(a,i){
 const money=k=>`<td class="num ${k==='current'?'bold':k==='gain'?'positive':''}" title="原始金额：${fmt(a[k],7)}美元">${k==='gain'?'+':''}${fmt(a.display[k])}${k==='gain'?`<span class="minor" title="${esc(a.countries.map(c=>COUNTRY[c]||c).join('、'))}">固定${a.countries.length}个可比国家</span>`:''}</td>`;
 return `<tr><td class="rank">${i+1}</td><td>${appCell(a)}</td>${money('previous')}${money('current')}<td class="num growth-emphasis">+${fmt(a.growth_pct,1)}%${a.previous<1?'<span class="badge amber minor">小基数：上周不足1美元</span>':''}</td>${money('gain')}<td>${spark(a,a.points,'日买量成本（美元）',false,'#087b62',4)}</td></tr>`;
}
function spark(a,points,label,rank=false,color='#087b62',precision=0){
 const valid=points.filter(p=>p.value!=null&&Number.isFinite(p.value));
 if(!valid.length)return '<span class="spark no-data">—</span>';
 let low=Math.min(...valid.map(p=>p.value)),high=Math.max(...valid.map(p=>p.value));
 if(high===low){const gap=Math.max(1,Math.abs(high)*.1);low-=gap;high+=gap}
 const width=134,height=36,pad=3,x=i=>pad+i*(width-2*pad)/Math.max(1,points.length-1),y=v=>rank?pad+(v-low)/(high-low)*(height-2*pad):height-pad-(v-low)/(high-low)*(height-2*pad);
 let path='',open=false,circles='';
 points.forEach((p,i)=>{
  if(p.value==null||!Number.isFinite(p.value)){open=false;return}
  path+=`${open?'L':'M'}${x(i)},${y(p.value)} `;open=true;
  const nations=Object.entries(p.country_ranks||{}).map(([c,r])=>`${COUNTRY[c]||c}第${r}名`).join('、');
  const tip=`${p.date} · ${label} ${fmt(p.value,precision)}${nations?' · '+nations:''}`;
  circles+=`<circle cx="${x(i)}" cy="${y(p.value)}" r="2.3" fill="${color}" data-date="${esc(p.date)}" data-value="${p.value}" data-tip="${esc(tip)}"><title>${esc(tip)}</title></circle>`;
 });
 return `<svg class="spark" data-package="${esc(a.package)}" data-observed="${valid.length}" data-rank-scale="${rank}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(a.name)} · ${esc(label)} · ${valid.length}个实际观测点"><path d="${path}" stroke="${color}"/>${circles}</svg>`;
}
function rankData(){return state.source==='gp'&&state.gpProvider==='appmagic'&&W.gp_appmagic?W.gp_appmagic:W[state.source]}
function growthScope(){const meta=rankData();return state.source==='dsp'?W.dsp:meta.scopes[meta.region_kind==='joint'?'all':state.country[state.source]]||{rows:[],coverage:[],chart_count:0,expected_chart_count:14,complete_country_count:0}}
function growthRows(){const scope=growthScope(),threshold=state.threshold[state.source],minimum=state.source==='dsp'?W.dsp.baseline_pool.cutoffs[state.baseline].minimum_previous_usd:null;return scope.rows.filter(a=>(state.source==='dsp'?a.growth_pct:a.gain)+1e-9>=threshold&&(state.source!=='dsp'||minimum!=null&&a.previous+1e-12>=minimum)).slice(0,10)}
function growthControls(){
 const src=state.source,rank=src!=='dsp',meta=rank?rankData():null,joint=meta?.region_kind==='joint',select=$('growth-country');
 $('growth-country-label').hidden=!rank||joint;
 $('growth-gp-source-label').hidden=src!=='gp'||!W.gp_appmagic;
 $('growth-gp-source').value=state.gpProvider;
 $('growth-baseline-label').hidden=rank;
 $('growth-baseline').value=state.baseline;
 select.innerHTML='<option value="all">全部可比国家</option>'+Object.entries(COUNTRY).map(([c,n])=>{
  const s=W[src]?.scopes?.[c],editor=src==='ps'&&['IN','RU'].includes(c),none=src==='gp'&&s&&s.chart_count===0;
  return `<option value="${c}" ${editor?'disabled':''}>${n}${editor?'（编辑推荐）':none?'（未取得榜单）':''}</option>`;
 }).join('');
 select.value=rank?state.country[src]:'all';
 const choices=src==='dsp'?[10,20,25,50,100,200]:src==='gp'?[5,10,20,30]:[3,5,8,10];
 $('growth-threshold').innerHTML=choices.map(v=>`<option value="${v}" ${v===state.threshold[src]?'selected':''}>${src==='dsp'?'买量增幅':'排名提升'} ≥ ${v}${src==='dsp'?'%':'位'}</option>`).join('');
}
function renderGrowth(){
 const src=state.source,rank=src!=='dsp',rows=growthRows(),scope=growthScope(),meta=rank?rankData():W.dsp,joint=meta.region_kind==='joint';
 const previous=meta.previous_days||W.previous_days,current=meta.current_days||W.current_days;
 $('previous-range').textContent=previous[0]+' — '+previous.at(-1);
 $('current-range').textContent=current[0]+' — '+current.at(-1);
 $('current-range-note').textContent=joint?'来源最新已取得的7天':'最近7天 · 截至报告前一天';
 $('growth-caption').textContent=src==='dsp'?'DSP · 买量大幅增加':src==='gp'?(joint?'GP · AppMagic联合榜排名上升':'GP · Sensor Tower排名上升'):'PalmStore · 排名迅速上升';
 const pending=rank&&(joint?!scope.complete_window:scope.complete_country_count===0);
 $('growth-count').textContent=pending?'两周完整国榜尚未取得':`按${rank?'提升位数':'买量增幅'}降序 · ${rows.length}款 / 最多10款`;
 $('growth-head').innerHTML=rank?`<tr><th>序号</th><th>APP / 用途</th><th>上周平均原榜排名</th><th>本周平均原榜排名</th><th>排名提升</th><th>${joint?'榜单国家范围':'可比国家数'}</th><th>上周 / 本周<br>有效观测天数</th><th>每日排名走势</th></tr>`:'<tr><th>序号</th><th>APP / 用途</th><th>上周累计买量成本<br>（美元）</th><th>本周累计买量成本<br>（美元）</th><th>买量增幅</th><th>增加金额<br>（美元）</th><th>每日买量成本走势</th></tr>';
 const empty=src==='ps'&&pending?'PS历史尚未积累完整，周增长留空。':pending?'该范围尚未取得两周完整日榜，周提升暂留空。':'当前没有符合筛选且两周实际记录完整的APP。';
 $('growth-body').innerHTML=rows.length?rows.map((a,i)=>rank?`<tr><td class="rank">${i+1}</td><td>${appCell(a)}</td><td class="num">${fmt(a.previous,1)}</td><td class="num bold">${fmt(a.current,1)}</td><td class="num growth-emphasis">↑ ${fmt(a.gain,1)}位</td><td class="num" title="${esc(a.countries.map(c=>COUNTRY[c]||c).join('、'))}">${a.countries.length}</td><td class="num">${a.previous_days}天 / ${a.current_days}天</td><td>${spark(a,a.points,joint?'AppMagic9国联合原榜排名':src==='gp'?'GP原榜排名':'PalmStore原榜排名',true,src==='gp'?'#386f9a':'#087b62',1)}</td></tr>`:weeklyCost(a,i)).join(''):`<tr class="empty-row"><td colspan="${rank?8:7}" class="empty">${empty}</td></tr>`;
 if(src==='dsp'){
  const pool=W.dsp.baseline_pool,cutoff=pool.cutoffs[state.baseline];
  $('growth-foot').textContent=`先筛上周买量成本前${state.baseline}%：有效可比工具样本${pool.size}款（含未增长APP），门槛约${fmt(cutoff.minimum_previous_usd)}美元（按未舍入金额判定）；边界同金额保留。再按本周增幅排序。每个APP合计两周每天均有记录的固定国家，金额取整、增幅按原值，缺行不补零。实际业务日${W.dsp.available_days.length}/14。`;
 }else if(joint){
  $('growth-foot').textContent=`AppMagic · Google Play · 实用工具 · 固定9国联合Top100。取得${scope.chart_count}/14日榜，最新可用日期${meta.latest_day}。国家范围：${scope.countries.map(c=>COUNTRY[c]||c).join('、')}；未包含：${meta.unavailable_countries.map(c=>COUNTRY[c]||c).join('、')}。每周按7个每日联合原榜名次取平均，APP须14天均有名次；联合榜按来源下载估算排序，仅使用页面实际名次。Sensor Tower逐国名次另选来源查看。`;
 }else{
  const coverage=`已取得${scope.chart_count}/${scope.expected_chart_count}份国日榜；${scope.complete_country_count}/${scope.countries?.length||1}国具备完整14日榜。`;
  const depth=W[src].recorded_depths.length?`实际保存的原榜深度${W[src].recorded_depths.join('、')}名。`:'';
  const extra=src==='ps'?`保存的快照日期：${W.ps.snapshot_dates.join('、')||'暂无'}。印度736、俄罗斯675推荐位不参与排名增长。`:'Sensor Tower同一工具免费榜按日期查询；已有20名后的名次也参与，不填101名。';
  $('growth-foot').textContent=coverage+' 每个APP只比较两周各7天名次完整的同一组国家；国家、包名与原榜均固定。'+depth+' '+extra;
 }
}
const METRIC={downloads:'日下载',buying_cost_usd:'日买量成本',unit_price_usd:'日单价'};
const TAB_METRIC={downloads:'downloads',cost:'buying_cost_usd',price:'unit_price_usd'};
function renderDSP(){
 const metric=state.metric,all=D.tables[metric].rows,rows=state.expanded?all:all.slice(0,6),n=14;
 $('dsp-title').textContent=`DSP · ${METRIC[metric]} Top20`;
 $('dsp-day-label').textContent=D.business_date;
 $('dsp-head').innerHTML='<tr><th>日排名</th><th>APP / 用途</th>'+Object.keys(METRIC).map(k=>`<th class="${metric===k?'selected-col':''}">${METRIC[k]}${k==='downloads'?'（次）':k==='buying_cost_usd'?'（美元）':'（美元/下载）'}</th>`).join('')+`<th>近${n}天本榜Top20<br>出现次数</th><th>本榜指标走势</th></tr>`;
 $('dsp-body').innerHTML=rows.map(a=>`<tr><td class="rank">${a.rank}</td><td>${appCell(a)}</td><td class="num ${metric==='downloads'?'selected-col':''}">${fmt(a.downloads)}</td><td class="num ${metric==='buying_cost_usd'?'selected-col':''}">${fmt(a.display.buying_cost_usd)}</td><td class="num ${metric==='unit_price_usd'?'selected-col':''}">${fmt(a.display.unit_price_usd,4)}</td><td class="num">${a.top20_counts[n]}次</td><td>${spark(a,a.points,METRIC[metric],false,metric==='unit_price_usd'?'#99659d':'#386f9a',metric==='unit_price_usd'?4:0)}</td></tr>`).join('');
 $('dsp-more').textContent=state.expanded?'收起为前6款':`展开全部${all.length}款`;
 $('dsp-more').hidden=all.length<=6;
 $('dsp-foot').textContent=`${D.business_date}当日合计，非日均或期间累计。三榜独立按原始数值排序；成本榜、单价榜当日日下载≥300。历史次数及小图使用近14天实际值，与周增长的固定国别样本分别计算。`;
}
function renderGP(){
 const s=G.scopes[state.gpDetail],rows=s.apps.slice(0,20);
 $('gp-scope').textContent=`${G.days[0]}—${G.days.at(-1)} · 20天 · ${state.gpDetail==='all'?'固定11国总榜':COUNTRY[state.gpDetail]} · 已取得${state.gpDetail==='all'?`${s.observed_country_days}/220份国日榜`:`${s.available_days.length}/20份日榜`}`;
 $('gp-body').innerHTML=rows.length?rows.map(a=>`<tr><td class="rank">${a.period_rank}</td><td>${appCell(a)}</td><td class="num">${fmt(a.mean_heat,2)}</td><td class="num">${a.top20_days}次</td><td class="num">${a.country_count}</td><td class="num">${fmt(a.mean_appearing_rank,2)}</td><td>${spark(a,a.points.map(p=>({date:p.date,value:p.trend_rank,country_ranks:p.country_ranks})),'每日原榜名次',true,'#386f9a',state.gpDetail==='all'?2:0)}</td></tr>`).join(''):'<tr class="empty-row"><td colspan="7" class="empty">该范围未取得可用榜单，保留空缺。</td></tr>';
}
function renderPalm(){
 $('ps-snapshot-date').textContent=DATA.ps_observation_date+'保存快照';
 $('palm-body').innerHTML=DATA.palmstore_view.rows.map(a=>`<div class="palm-row" data-package="${esc(a.package)}" data-count="${a.hot_count}"><div class="palm-head">${appLink(a)}<b class="num">${a.hot_count}/13</b></div><span class="minor">${esc(a.subclass)} · ${esc(a.brief)}</span><div class="palm-bar" role="progressbar" aria-label="${esc(a.name)}热门次数" aria-valuemin="0" aria-valuemax="13" aria-valuenow="${a.hot_count}">${Array.from({length:13},(_,i)=>`<span class="${i<a.hot_count?'on':''}"></span>`).join('')}</div></div>`).join('');
}
function init(){
 $('previous-range').textContent=W.previous_days[0]+' — '+W.previous_days.at(-1);
 $('current-range').textContent=W.current_days[0]+' — '+W.current_days.at(-1);
 $('period-line').textContent=`报告日期${DATA.report_date} · DSP当日榜${D.business_date}（UTC） · PalmStore快照${DATA.ps_observation_date}`;
 $('gp-country').innerHTML='<option value="all">全部国家总榜（固定11国）</option>'+Object.entries(COUNTRY).map(([c,n])=>`<option value="${c}">${n}</option>`).join('');
 growthControls();renderGrowth();renderDSP();renderGP();renderPalm();
}
$('growth-tabs').addEventListener('click',e=>{const b=e.target.closest('[data-source]');if(!b)return;state.source=b.dataset.source;for(const x of e.currentTarget.querySelectorAll('button'))x.setAttribute('aria-pressed',String(x===b));growthControls();renderGrowth()});
$('growth-country').addEventListener('change',e=>{state.country[state.source]=e.target.value;renderGrowth()});
$('growth-threshold').addEventListener('change',e=>{state.threshold[state.source]=Number(e.target.value);renderGrowth()});
$('growth-baseline').addEventListener('change',e=>{state.baseline=Number(e.target.value);renderGrowth()});
$('growth-gp-source').addEventListener('change',e=>{state.gpProvider=e.target.value;growthControls();renderGrowth()});
$('dsp-tabs').addEventListener('click',e=>{const b=e.target.closest('[data-metric]');if(!b)return;state.metric=TAB_METRIC[b.dataset.metric];for(const x of e.currentTarget.querySelectorAll('button'))x.setAttribute('aria-pressed',String(x===b));renderDSP()});
$('dsp-more').addEventListener('click',()=>{state.expanded=!state.expanded;renderDSP()});
$('gp-country').addEventListener('change',e=>{state.gpDetail=e.target.value;renderGP()});
const tip=$('tooltip');document.addEventListener('pointermove',e=>{const c=e.target.closest?.('[data-tip]');if(!c){tip.style.display='none';return}tip.textContent=c.dataset.tip;tip.style.display='block';tip.style.left=Math.min(e.clientX+12,window.innerWidth-258)+'px';tip.style.top=Math.max(6,e.clientY-51)+'px'});document.addEventListener('scroll',()=>tip.style.display='none',{capture:true});
init();
