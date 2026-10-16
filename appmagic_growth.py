"""AppMagic固定国别联合榜周对比；只读浏览器实际保存的原名次。"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
TARGET = ['PK','IN','NG','ID','BD','PH','CI','IQ','RU','SY','SA','CD','BF']


def validate(chart, countries):
    """联合榜身份及可见日期必须一致，锁定下载量不作为已取得数值。"""
    query=parse_qs(urlparse(chart['url']).query)
    if urlparse(chart['url']).hostname!='appmagic.rocks' or urlparse(chart['url']).path!='/top-charts/apps':
        raise ValueError('AppMagic榜单链接不匹配')
    if query.get('store')!=['1'] or query.get('tag')!=['115'] or query.get('aggregation')!=['day']:
        raise ValueError('AppMagic平台、分类或时间维度不匹配')
    selected=query.get('country',[''])[0].split(',')
    if len(selected)!=len(set(selected)) or set(selected)!=set(countries) or any(c not in TARGET for c in countries):
        raise ValueError('AppMagic联合国家范围不匹配')
    day=chart['date'];datetime.fromisoformat(day)
    if query.get('date')!=[day] or chart.get('shown_date')!=day:
        raise ValueError('AppMagic可见日期尚未正确加载')
    rows=chart['rows']
    if len(rows)<100 or [a['rank'] for a in rows]!=list(range(1,len(rows)+1)) or len({a['package'] for a in rows})!=len(rows):
        raise ValueError('AppMagic实际前100名不完整或重复')
    for row in rows:
        if row.get('store')!='Google Play' or not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+',row['package']):
            raise ValueError('AppMagic平台或包名不匹配')
        link=urlparse(row['appmagic_url'])
        if link.hostname!='appmagic.rocks' or not link.path.startswith('/google-play/') or link.path.split('/')[-1]!=row['package']:
            raise ValueError('AppMagic应用链接不匹配')
    return chart


def build(catalog, root=ROOT):
    """联合榜是固定国家范围的一个原榜，不能伪造为每个国家的名次。"""
    sources=[]
    for path in sorted((Path(root)/'data/raw').glob('appmagic_top100_joint_*.json')):
        obj=json.loads(path.read_text(encoding='utf-8'))
        if obj.get('source')!='AppMagic' or obj.get('region_kind')!='joint':
            continue
        countries=obj['countries']
        for chart in obj['charts']:
            sources.append((validate(chart,countries),tuple(sorted(countries)),str(path.relative_to(root)).replace('\\','/')))
    if not sources:return None
    latest= max(sources,key=lambda a:(a[0]['date'],a[0].get('collected_at','')))
    countries=list(latest[1]);end=latest[0]['date']
    days=[(datetime.fromisoformat(end)-timedelta(days=i)).date().isoformat() for i in reversed(range(14))]
    index={}
    for chart,cohort,path in sources:
        if cohort!=tuple(countries) or chart['date'] not in days:continue
        key=chart['date']
        if key not in index or (len(chart['rows']),chart.get('collected_at','')) >= (len(index[key]['rows']),index[key].get('collected_at','')):
            index[key]=dict(chart,snapshot=path)
    ranks={d:{a['package']:a['rank'] for a in c['rows']} for d,c in index.items()}
    rows=[]
    for package in set(catalog)&set().union(*(set(a) for a in ranks.values())):
        if not all(d in ranks and package in ranks[d] for d in days):continue
        points=[{'date':d,'value':ranks[d][package],'joint_rank':ranks[d][package]} for d in days]
        previous=sum(p['value'] for p in points[:7])/7;current=sum(p['value'] for p in points[7:])/7
        if previous-current<=1e-9:continue
        rows.append(catalog[package]|{'previous':previous,'current':current,'gain':previous-current,
                                     'countries':countries,'previous_days':7,'current_days':7,'points':points})
    rows.sort(key=lambda a:(-a['gain'],a['current'],a['package']))
    return {'source':'AppMagic','region_kind':'joint','category':'实用工具','days':days,
            'previous_days':days[:7],'current_days':days[7:],'latest_day':end,'default_threshold':10,
            'recorded_depths':sorted({len(a['rows']) for a in index.values()}),
            'source_files':sorted({a['snapshot'] for a in index.values()}),
            'unavailable_countries':[c for c in TARGET if c not in countries],
            'scopes':{'all':{'rows':rows,'countries':countries,'chart_count':len(index),'expected_chart_count':14,
                             'complete_window':all(d in index for d in days),'missing_days':[d for d in days if d not in index]}},
            'method':f'AppMagic对固定{len(countries)}个可选目标国家合计的实用工具免费下载估算排序；这是一个联合原榜。两周各7天每日联合原榜名次取均值，提升=上周均值−本周均值；只比较14天都有实际名次的APP。各国单榜名次及下载估算数值未取得，未知排名留空。'}
