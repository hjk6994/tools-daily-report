"""依据浏览器实际取得的每日工具免费榜，计算等权跨国热度与名次。"""
import json
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from metadata import get_meta
from app_functions import function_for,DISPLAY_NAMES,OTHER_FUNCTIONS

ROOT=Path(__file__).resolve().parent

def raw_history():
    raw=json.loads((ROOT/'data/raw/sensortower_history_20261010.json').read_text(encoding='utf-8'))
    charts={}
    snapshots=[raw]+[json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT/'data/raw').glob('sensortower_history_*_20261010.json'))]
    for snapshot in snapshots:
      apps=snapshot['registry']
      for item in snapshot['charts']:
        r=dict(item)
        if 'country' not in r:r.update(country=snapshot['country'],url=snapshot['url_template'].replace('{date}',r['date']))
        q=parse_qs(urlparse(r['url']).query)
        if any(q.get(k)!=[v] for k,v in {'country':r['country'],'date':r['date'],'category':'tools','os':'android'}.items()):
            raise ValueError('历史日榜国家、日期、分类或平台未匹配')
        if len(r['ids'])!=10 or len(set(r['ids']))!=10:raise ValueError('历史前10项不完整或重复')
        chart={k:r[k] for k in ['country','date','url','collected_at']}
        chart['rows']=[{'package':apps[i][0],'source_name':apps[i][1],'rank':rank+1} for rank,i in enumerate(r['ids'])]
        charts[(r['country'],r['date'])]=chart
    # 合并本项目之前已实际获取的同来源日榜，不复制到其他日期或国家。
    from sensortower_data import source
    source_path,saved=source()
    for c in saved['charts']:
        key=(c['country'],c['date'])
        if key not in charts:
            charts[key]={'country':c['country'],'date':c['date'],'url':c['url'],'collected_at':c['collected_at'],'saved_snapshot':str(source_path.relative_to(ROOT)),'rows':[{'package':a['package'],'source_name':a['name'],'rank':a['rank']} for a in c['rows']]}
    return raw,charts

def acquire_metadata():
    _,charts=raw_history();packages=sorted({a['package'] for c in charts.values() for a in c['rows']})
    with ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(get_meta,packages))
    pd.DataFrame(rows).to_csv(ROOT/'gp_history_metadata.csv',index=False,encoding='utf-8-sig')
    print(json.dumps({'apps':len(rows),'verified':sum(r['metadata_status']=='verified' for r in rows)},ensure_ascii=False))

def ranked(rows,scope,countries):
    """每国第1至10名分别计10至1分；名次同分时按出现国数、平均名次、包名排序。"""
    groups={}
    for a in rows:
        if not a['tool_function']:continue
        p=a['package']
        if p not in groups:groups[p]={k:a[k] for k in ['package','name','subclass','brief','function_source']}|{'score':0,'positions':{}}
        groups[p]['score']+=11-a['rank'];groups[p]['positions'][a['country']]=a['rank']
    apps=list(groups.values())
    for a in apps:
        a['country_count']=len(a['positions']);a['mean_appearing_rank']=sum(a['positions'].values())/a['country_count']
        a['heat_index']=100*a['score']/(10*len(countries));a['scope']=scope
    apps.sort(key=lambda a:(-a['score'],-a['country_count'],a['mean_appearing_rank'],a['package']))
    for i,a in enumerate(apps):a['heat_rank']=i+1
    return apps

def build():
    from comparison_report import COUNTRIES,COLORS
    raw,charts=raw_history();days=raw['days'];meta=pd.read_csv(ROOT/'gp_history_metadata.csv').fillna('').set_index('package');flat=[];catalog={}
    overrides={a['package']:a for a in json.loads((ROOT/'data/gp_history_function_overrides.json').read_text(encoding='utf-8'))}
    for c in charts.values():
        for a in c['rows']:
            m=meta.loc[a['package']].to_dict() if a['package'] in meta.index else {}
            override=overrides.get(a['package'],{})
            title=DISPLAY_NAMES.get(a['package'],override.get('name') or m.get('name') or a['source_name'])
            tool=function_for(a['package'],title,m.get('summary',''),m.get('official_category','')) if m.get('metadata_status')=='verified' else None
            if override:tool=(override['subclass'],override['brief'])
            info=OTHER_FUNCTIONS.get(a['package']) or tool
            if not info:raise ValueError('历史榜应用用途待核验：'+a['package'])
            a.update(name=title,subclass=info[0],brief=info[1],tool_function=bool(tool),function_source=override.get('function_source') or m.get('verification_url') or c['url'])
            a.update(country=c['country'],date=c['date'],source_url=c['url'],collected_at=c['collected_at'])
            flat.append(a);catalog[a['package']]={k:a[k] for k in ['package','name','subclass','brief','function_source']}
    pd.DataFrame(flat).to_csv(ROOT/'gp_daily_country_top10.csv',index=False,encoding='utf-8-sig')
    covered=[c for c in COUNTRIES if any((c,d) in charts for d in days)]
    latest=max(days,key=lambda d:(sum((c,d) in charts for c in covered),d))
    aggregate=ranked([a for a in flat if a['date']==latest],'all',covered)
    all_rows=[];series={};anchor_dates={};scope_countries={'all':covered}
    for c in COUNTRIES:scope_countries[c]=[c]
    daily_rankings={}
    for scope,countries in scope_countries.items():
        series[scope]={};daily_rankings[scope]={}
        for day in days:
            complete=bool(countries) and all((c,day) in charts for c in countries)
            rs=ranked([a for a in flat if a['date']==day and a['country'] in countries],scope,countries) if complete else []
            daily_rankings[scope][day]=rs
            for a in rs:all_rows.append({k:v for k,v in a.items() if k!='positions'}|{'date':day,'coverage_country_count':len(countries)})
        anchor_day=latest if scope=='all' else max((d for d in days if (scope,d) in charts),default=latest)
        anchor_dates[scope]=anchor_day
        anchors=daily_rankings[scope][anchor_day][:10]
        for ix,a in enumerate(anchors):
            a['color']=COLORS[ix];points=[]
            for day in days:
                complete=bool(countries) and all((c,day) in charts for c in countries)
                found=next((x for x in daily_rankings[scope][day] if x['package']==a['package']),None)
                points.append({'date':day,'heat_index':found['heat_index'] if found else (0 if complete else None),'score':found['score'] if found else (0 if complete else None),'heat_rank':found['heat_rank'] if found else None,'source_rank':found['positions'].get(scope) if found else None,'status':'observed' if found else ('outside_observed_top10' if complete else 'missing_country_chart')})
            series[scope][a['package']]=points
    aggregate=daily_rankings['all'][latest]
    pd.DataFrame(all_rows).to_csv(ROOT/'gp_daily_heat_rankings.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame([{k:v for k,v in a.items() if k!='positions'}|{'date':latest,'coverage_country_count':len(covered)} for a in aggregate]).to_csv(ROOT/'gp_all_country_heat_rankings.csv',index=False,encoding='utf-8-sig')
    coverage=[{'date':d,'country':c,'status':'complete_top10' if (c,d) in charts else 'missing_country_chart','url':charts[(c,d)]['url'] if (c,d) in charts else next((r['url'] for r in raw.get('missing',[]) if r['country']==c and r['date']==d),'')} for d in days for c in COUNTRIES]
    pd.DataFrame(coverage).to_csv(ROOT/'gp_daily_coverage.csv',index=False,encoding='utf-8-sig')
    missing=[c for c in COUNTRIES if c not in covered]
    return {'source':'Sensor Tower','platform':'Google Play','category':'工具','chart_type':'免费下载Top10','days':days,'date':latest,'countries':covered,'missing_countries':missing,'charts':list(charts.values()),'aggregate':aggregate,'rankings':daily_rankings,'series':series,'anchor_dates':anchor_dates,'coverage':coverage,'catalog':list(catalog.values()),'method':'每国原榜第1至10名分别计10至1分，工具APP按包名汇总，各国等权；热度指数=总分÷(10×完整覆盖国家数)×100。同分依次按出现国家数降序、出现平均名次升序、包名排序。工具总榜筛除来源工具榜中主要功能为影视、约会或礼品卡交易的APP，保留其原始名次。','trend_scope_note':'全部国家趋势固定使用最新日已完整取得榜单的国家。任一国家某日缺榜，则该日总榜热度和名次不可用；不缩减分母。某APP未进入任何已完整覆盖国家的前10时，其Top10热度指数为0，实际商店名次未知。','complete_chart_count':len(charts),'requested_chart_count':len(days)*len(COUNTRIES)}

if __name__=='__main__':acquire_metadata()
