"""真实20天原榜Top20复算：固定国家分母，原榜出现日期去重计数。"""
import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from app_functions import function_for, DISPLAY_NAMES, OTHER_FUNCTIONS

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'data/raw/sensortower_top20_20d_observed_20261010.json'
COUNTRIES = ['PK','IN','NG','ID','BD','PH','CI','IQ','RU','SY','SA','CD','BF']
FIXED = [c for c in COUNTRIES if c not in ['SY','CD']]


def cached_metadata(package):
    """报告生成只读已取得的公开资料，不自动联网刷新用途。"""
    path=ROOT/'data/raw'/f'gp_metadata_{package}.json'
    if not path.exists():return {'metadata_status':'unknown'}
    raw=json.loads(path.read_text(encoding='utf-8'))
    return {'name':raw.get('title'),'summary':raw.get('summary') or '',
            'official_category':raw.get('genre') or '',
            'metadata_status':'verified' if raw.get('title') and raw.get('genre') else 'unknown',
            'verification_url':raw.get('url')}


def snapshot_files():
    """历史快照与每日增量共同参与复算，失败观察不覆盖已成功的榜单。"""
    return sorted(set(([SOURCE] if SOURCE.exists() else [])+list((ROOT/'data/raw').glob('sensortower_top20_daily_observed_*.json'))))


def validate_observation(item):
    q=parse_qs(urlparse(item['url']).query)
    country,date=q['country'][0],q['date'][0]
    datetime.fromisoformat(date)
    if urlparse(item['url']).hostname!='app.sensortower.com' or country not in COUNTRIES or q.get('category')!=['tools'] or q.get('os')!=['android']:
        raise ValueError('GP原榜分类、国家或平台不匹配')
    if item.get('country',country)!=country or item.get('date',date)!=date:
        raise ValueError('GP原榜国家或日期不匹配')
    rows=item['rows']
    if item.get('no_chart'):
        if rows:raise ValueError('无榜状态不应包含席位')
    else:
        if len(rows)<20 or len({a['package'] for a in rows})!=len(rows) or [a['rank'] for a in rows]!=list(range(1,len(rows)+1)):
            raise ValueError('GP实际原榜前20不完整或排名记录重复')
        for a in rows:
            if not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+',a['package']):
                raise ValueError('GP原榜包名格式无效')
            pq=parse_qs(urlparse(a['publisher_url']).query)
            if urlparse(a['publisher_url']).hostname!='app.sensortower.com' or pq.get('country')!=[country] or pq.get('date')!=[date]:
                raise ValueError('GP榜单尚未完成对应日期加载')
    return dict(item,country=country,date=date)


def source_observations():
    observations=[]
    for path in snapshot_files():
        saved=json.loads(path.read_text(encoding='utf-8'))
        observations.extend(validate_observation(item) for item in saved['charts'])
    return observations


def source_charts():
    charts = {}
    for item in source_observations():
        if item.get('no_chart'):continue
        key=item['country'],item['date']
        # 更深的真实榜单优先，防止未登录的浅榜覆盖已取得的深榜。
        if key not in charts or (len(item['rows']),item.get('collected_at',''))>=(len(charts[key]['rows']),charts[key].get('collected_at','')):
            charts[key]=item
    return charts


def build(data, export=True):
    end = (datetime.fromisoformat(data['report_date'])-timedelta(days=1)).date()
    days = [(end-timedelta(days=i)).isoformat() for i in reversed(range(20))]
    charts = {k:v for k,v in source_charts().items() if k[1] in days}
    existing = {a['package']:a for a in data['app_functions']}
    overrides = {a['package']:a for a in json.loads((ROOT/'data/gp_history_function_overrides.json').read_text(encoding='utf-8'))}
    catalog, flat = {}, []
    for chart in charts.values():
        for raw in chart['rows']:
            package=raw['package']
            if package not in catalog:
                meta=cached_metadata(package)
                name=DISPLAY_NAMES.get(package,meta.get('name') or raw['name'])
                tool=function_for(package,name,meta.get('summary',''),meta.get('official_category','')) if meta.get('metadata_status')=='verified' else None
                if package in overrides:
                    tool=(overrides[package]['subclass'],overrides[package]['brief'])
                info=OTHER_FUNCTIONS.get(package) or tool
                if not info and package in existing:
                    info=(existing[package]['subclass'],existing[package]['brief'])
                if not info:
                    info=('用途待核验','公开资料不足，暂不计入已核验工具排行。')
                catalog[package]={'package':package,'name':name,'subclass':info[0],'brief':info[1],
                                  'tool_function':bool(tool),'function_source':overrides.get(package,{}).get('function_source') or meta.get('verification_url') or chart['url']}
            flat.append(dict(raw,**{k:v for k,v in catalog[package].items() if k!='package'},
                             country=chart['country'],date=chart['date'],source_url=chart['url']))
    scopes={}
    for scope in ['all']+COUNTRIES:
        countries=FIXED if scope=='all' else [scope]
        available=[d for d in days if all((c,d) in charts for c in countries)]
        daily={}
        positions={}
        for day in days:
            if day not in available:
                daily[day]=None
                continue
            groups={}
            for row in flat:
                if row['date']!=day or row['country'] not in countries or not row['tool_function'] or row['rank']>20:
                    continue
                p=row['package']
                groups.setdefault(p,{'package':p,'score':0,'positions':{}})
                groups[p]['score']+=21-row['rank']
                groups[p]['positions'][row['country']]=row['rank']
                positions.setdefault(p,[]).append((row['country'],row['rank']))
            daily[day]=sorted(groups.values(),key=lambda a:(-a['score'],-len(a['positions']),sum(a['positions'].values())/len(a['positions']),a['package']))
            for i,a in enumerate(daily[day],1):
                a['rank']=i
                a['heat_index']=a['score']/(20*len(countries))*100
        apps=[]
        for package,ps in positions.items():
            points=[]
            for day in days:
                match=next((a for a in daily[day] or [] if a['package']==package),None)
                rank_rows=[r for r in flat if r['date']==day and r['package']==package and r['country'] in countries]
                rank_positions={r['country']:r['rank'] for r in rank_rows}
                points.append({'date':day,'heat_index':match['heat_index'] if match else 0 if daily[day] is not None else None,
                               'rank':(match['rank'] if scope=='all' else match['positions'][scope]) if match and match['rank']<=20 else None,
                               'trend_rank':sum(rank_positions.values())/len(rank_positions) if rank_positions else None,
                               'country_ranks':rank_positions,
                               'appearing_country_count':len(rank_positions),
                               'available_country_count':len(countries) if daily[day] is not None else 0,
                               'status':'有实际原榜名次' if rank_positions else '缺榜' if daily[day] is None else '已取得榜单中无实际名次记录'})
            apps.append({k:catalog[package][k] for k in ['package','name','subclass','brief']} | {
                'mean_heat':sum(p['heat_index'] for p in points if p['heat_index'] is not None)/len(available),
                'top20_days':sum(p['rank'] is not None for p in points),
                'observed_days':len(available),'count_complete':len(available)==20,
                'country_count':len({c for c,r in ps}),'mean_appearing_rank':sum(r for c,r in ps)/len(ps),
                'country_days':len(ps),'points':points,
            })
        apps.sort(key=lambda a:(-a['mean_heat'],-a['country_days'],a['mean_appearing_rank'],a['package']))
        for rank,a in enumerate(apps,1):a['period_rank']=rank
        scopes[scope]={'apps':apps,'available_days':available,'missing_days':[d for d in days if d not in available],
                       'countries':countries,'complete':len(available)==20,
                       'trend_available_days':available,'trend_missing_days':[d for d in days if d not in available],
                       'daily_top20':{d:[a['package'] for a in daily[d][:20]] if daily[d] is not None else None for d in days}}
    # 总榜保留各国已取得的期间证据，先求各国日均积分，再按固定国家等权合成。
    # 出现次数取各国原Top20的日期并集，同一天跨国重复出现仍只计一次。
    national={c:{a['package']:a for a in scopes[c]['apps']} for c in FIXED}
    aggregate=[]
    if all(scopes[c]['available_days'] for c in FIXED):
        members=set().union(*(set(national[c]) for c in FIXED))
        for package in members:
            seen={p['date'] for c in FIXED if package in national[c] for p in national[c][package]['points'] if p['rank'] is not None}
            rank_records=[r for r in flat if r['package']==package and r['country'] in FIXED and r['tool_function']]
            positions=[r for r in rank_records if r['rank']<=20]
            points=[]
            for day in days:
                complete=day in scopes['all']['available_days']
                day_positions=[r for r in rank_records if r['date']==day]
                score=sum(21-r['rank'] for r in day_positions if r['rank']<=20)
                available_countries=[c for c in FIXED if (c,day) in charts]
                points.append({'date':day,'heat_index':score/(20*len(FIXED))*100 if complete else None,
                               'rank':None,
                               'trend_rank':sum(r['rank'] for r in day_positions)/len(day_positions) if day_positions else None,
                               'country_ranks':{r['country']:r['rank'] for r in day_positions},
                               'appearing_country_count':len(day_positions),
                               'available_country_count':len(available_countries),
                               'status':'当天有实际名次记录国家的原榜平均名次' if day_positions else
                                        '已取得的国榜中无该APP实际名次记录' if available_countries else '当日国榜未取得'})
            aggregate.append({k:catalog[package][k] for k in ['package','name','subclass','brief']} | {
                'mean_heat':sum(national[c].get(package,{}).get('mean_heat',0) for c in FIXED)/len(FIXED),
                'top20_days':len(seen),'observed_days':len(set().union(*(set(scopes[c]['available_days']) for c in FIXED))),
                'count_complete':len(seen)==20 or all(scopes[c]['complete'] for c in FIXED),
                'country_count':len({r['country'] for r in positions}),
                'mean_appearing_rank':sum(r['rank'] for r in positions)/len(positions),
                'country_days':len(positions),'points':points,
            })
        aggregate.sort(key=lambda a:(-a['mean_heat'],-a['country_days'],a['mean_appearing_rank'],a['package']))
        for rank,a in enumerate(aggregate,1):a['period_rank']=rank
    scopes['all']['apps']=aggregate
    scopes['all']['observed_country_days']=sum(len(scopes[c]['available_days']) for c in FIXED)
    scopes['all']['trend_available_days']=[d for d in days if any((c,d) in charts for c in FIXED)]
    scopes['all']['trend_missing_days']=[d for d in days if d not in scopes['all']['trend_available_days']]
    attempts={}
    for item in source_observations():
        attempts[item['country'],item['date']]=item
    coverage=[{'country':c,'date':d,'status':'已取得完整Top20' if (c,d) in charts else '页面未显示可用榜单，原因未确认' if attempts.get((c,d),{}).get('no_chart') else '未取得该日Top20',
               'url':charts[c,d]['url'] if (c,d) in charts else attempts.get((c,d),{}).get('url','')} for d in days for c in COUNTRIES]
    if export:
        for filename,rows in [('gp_20d_country_top20.csv',[r for r in flat if r['rank']<=20]),('gp_20d_coverage.csv',coverage)]:
            if not rows:continue
            with (ROOT/filename).open('w',newline='',encoding='utf-8-sig') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        summary=[]
        for scope,w in scopes.items():
            for a in w['apps'][:20]:summary.append({'范围':scope,'20天期间名次':a['period_rank'],'APP':a['name'],'用途':a['subclass'],'说明':a['brief'],'平均热度':a['mean_heat'],'20天原榜Top20出现次数':a['top20_days'],'次数完整':a['count_complete'],'已取得日榜天数':a['observed_days']})
        if summary:
            with (ROOT/'gp_20d_rankings.csv').open('w',newline='',encoding='utf-8-sig') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    data['app_functions']=list({a['package']:a for a in data['app_functions']+[{k:a[k] for k in ['package','name','subclass','brief']} for a in catalog.values()]}.values())
    return {'source':'Sensor Tower','platform':'Google Play','category':'工具','chart_type':'免费下载Top20',
            'days':days,'scopes':scopes,'fixed_countries':FIXED,'unavailable_countries':['SY','CD'],
            'chart_count':len(charts),'requested_chart_count':20*len(COUNTRIES),'coverage':coverage,'catalog':list(catalog.values()),
            'source_file':str(SOURCE.relative_to(ROOT)),'source_files':[str(p.relative_to(ROOT)) for p in snapshot_files()],
            'collection_note':'每日增量与历史真实榜单共同复算；页面无榜不据此认定该日不存在榜单。未取得的日榜不填零。',
            'rule':'20天内进入国家原工具Top20的日期次数；总榜取固定11国出现日期的并集，同一天跨国出现只计1次，单国每日期最多1次；不是出现次数与可用天数之比，也不是进入合成总榜Top20的次数。缺日次数是已观察下限。',
            'heat_rule':'原榜第1至20名计20至1分。单国以已取得日榜的积分日均值除以20得到热度；总榜先计算各国日均热度，再按固定11国等权平均。缺日时仅为基于已观察日期的临时期间排名，不冒充完整20日均值。榜单热度不是下载量。',
            'trend_rule':'小图绘每日所有实际取得的原榜名次，包括20名以后的记录；出现次数仍只统计进入原Top20的日期。总榜取APP当天有实际名次记录国家的原榜名次算术均值，单国取原榜名次，不要求所有国家同日全齐。名次越小越靠上；仅没有实际名次数据的日期留空并断线，不补零或推断名次。各日参与国家可能不同，悬停可查看国家、原名次和当日日榜覆盖。'}
