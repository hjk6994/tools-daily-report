"""仅标准化真实浏览器榜单；未覆盖国家保持缺数，不推断下载数。"""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from app_functions import function_for,KNOWN,DISPLAY_NAMES
from metadata import get_meta
ROOT=Path(__file__).resolve().parent

def source():
    path=sorted((ROOT/'data'/'raw').glob('appmagic_observed_*.json'))[-1]
    data=json.loads(path.read_text(encoding='utf-8'))
    for c in data['charts']:
        for field in ['date','category','store','chart']:c.setdefault(field,data.get(field))
        c['rows']=[{'name':a[0],'package':a[1],'rank':i+1,'source_url':c['url'],'visible_value':None} if isinstance(a,list) else a for i,a in enumerate(c['rows'])]
    return path,data

def acquire_metadata():
    _,data=source();packages=list(dict.fromkeys(a['package'] for c in data['charts'] for a in c['rows']))
    with ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(get_meta,packages))
    pd.DataFrame(rows).to_csv(ROOT/'appmagic_metadata.csv',index=False,encoding='utf-8-sig')
    print(json.dumps({'GP_apps':len(rows),'verified':sum(a['metadata_status']=='verified' for a in rows)},ensure_ascii=False))

def build():
    path,data=source();meta=pd.read_csv(ROOT/'appmagic_metadata.csv').set_index('package');all_rows=[]
    for chart in data['charts']:
        if len(chart['rows'])!=10 or chart['category']!='实用工具' or chart['store']!='Google Play':raise ValueError('GP实际筛选或Top10不完整')
        for a in chart['rows']:
            m=meta.loc[a['package']].to_dict() if a['package'] in meta.index else {}
            info=function_for(a['package'],m.get('name',a['name']),m.get('summary',''),m.get('official_category',''))
            if not info:raise ValueError('需要补充已核验用途：'+a['package'])
            a['source_name']=a['name'];a['name']=DISPLAY_NAMES.get(a['package'],m.get('name',a['name']))
            a['subclass'],a['brief']=info;a['downloads']=None
            a['function_source']=m.get('verification_url',a['source_url']);all_rows.append({**a,'country':chart['country'],'date':chart['date'],'collected_at':chart['collected_at'],'chart_url':chart['url'],'snapshot':str(path.relative_to(ROOT))})
    rows=pd.DataFrame(all_rows);rows.to_csv(ROOT/'gp_country_top10.csv',index=False,encoding='utf-8-sig');frequency=[]
    for package,g in rows.groupby('package'):
        first=g.iloc[0];positions=dict(zip(g.country,g['rank'].astype(int)))
        frequency.append({'package':package,'name':first['name'],'subclass':first['subclass'],'brief':first['brief'],'country_count':len(positions),'mean_rank':float(g['rank'].mean()),'positions':positions})
    frequency.sort(key=lambda a:(-a['country_count'],a['mean_rank'],a['name']))
    pd.DataFrame([{k:v for k,v in a.items() if k!='positions'} for a in frequency]).to_csv(ROOT/'gp_country_frequency.csv',index=False,encoding='utf-8-sig')
    data['frequency']=frequency;data['observation_date']=data['charts'][0]['collected_at'][:10];data['date']=data['charts'][0]['date']
    data['statuses']=[{'country':c['country'],'status':'complete_top10','url':c['url']} for c in data['charts']]+data['missing_countries']
    data['snapshot']=str(path.relative_to(ROOT));return data

if __name__=='__main__':acquire_metadata()
