"""标准化实际Sensor Tower免费榜；严格核对国家代码与同日来源。"""
import json
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from metadata import get_meta
from app_functions import function_for,DISPLAY_NAMES,OTHER_FUNCTIONS
ROOT=Path(__file__).resolve().parent
def source():
    path=sorted((ROOT/'data'/'raw').glob('sensortower_observed_*.json'))[-1];data=json.loads(path.read_text(encoding='utf-8'))
    for c in data['charts']:
        params=parse_qs(urlparse(c['url']).query)
        if params.get('country')!=[c['country']] or params.get('os')!=['android'] or params.get('category')!=['tools'] or params.get('date')!=[data['date']]:raise ValueError('国家、分类、平台或日期不一致')
        c['date']=data['date'];c['rows']=[{'name':r[0],'package':r[1],'rank':i+1,'source_url':c['url'],'downloads':None} for i,r in enumerate(c['rows'])]
    return path,data
def acquire_metadata():
    _,data=source();packages=list(dict.fromkeys(a['package'] for c in data['charts'] for a in c['rows']))
    with ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(get_meta,packages))
    pd.DataFrame(rows).to_csv(ROOT/'sensortower_metadata.csv',index=False,encoding='utf-8-sig');print(json.dumps({'sensor_apps':len(rows),'verified':sum(r['metadata_status']=='verified' for r in rows)},ensure_ascii=False))
def build(magic):
    path,data=source();meta=pd.read_csv(ROOT/'sensortower_metadata.csv').set_index('package');rows=[]
    for c in data['charts']:
        if len(c['rows'])!=10:raise ValueError('榜单前10不完整')
        for a in c['rows']:
            m=meta.loc[a['package']].to_dict() if a['package'] in meta.index else {};a['source_name']=a['name'];a['name']=DISPLAY_NAMES.get(a['package'],m.get('name',a['name']))
            info=OTHER_FUNCTIONS.get(a['package']) or function_for(a['package'],m.get('name',a['name']),m.get('summary',''),m.get('official_category',''))
            if not info:raise ValueError('需要补充来源中APP的用途：'+a['package'])
            a['subclass'],a['brief']=info;a['function_source']=m.get('verification_url',a['source_url']);a['actual_official_category']=m.get('official_category');a['tool_function']=function_for(a['package'],m.get('name',a['name']),m.get('summary',''),m.get('official_category','')) is not None
            rows.append({**a,'country':c['country'],'date':c['date'],'chart_url':c['url'],'collected_at':c['collected_at']})
    pd.DataFrame(rows).to_csv(ROOT/'gp_sensortower_top10.csv',index=False,encoding='utf-8-sig');data['observation_date']=data['charts'][0]['collected_at'][:10];data['snapshot']=str(path.relative_to(ROOT));data['statuses']=[{'country':c['country'],'status':'complete_top10','url':c['url']} for c in data['charts']]+data['missing_countries']
    from comparison_report import COUNTRIES
    country_rows=[];common=[]
    for country in COUNTRIES:
        am=next((c for c in magic['charts'] if c['country']==country),None);st=next((c for c in data['charts'] if c['country']==country),None);comparable=bool(am and st and am['date']==st['date']);a={r['package']:r for r in am['rows']} if am else {};b={r['package']:r for r in st['rows']} if st else {};intersection=set(a)&set(b) if comparable else set()
        country_rows.append({'country':country,'date':magic['date'],'appmagic_count':len(a),'sensor_count':len(b),'comparable':comparable,'overlap_count':len(intersection) if comparable else None,'overlap_ratio':len(intersection)/10 if comparable else None,'common_packages':sorted(intersection)})
        for p in sorted(intersection):common.append({'country':country,'package':p,'name':a[p]['name'],'subclass':a[p]['subclass'],'brief':a[p]['brief'],'appmagic_rank':a[p]['rank'],'sensor_rank':b[p]['rank'],'sensor_minus_appmagic':b[p]['rank']-a[p]['rank']})
    pd.DataFrame([{k:v for k,v in r.items() if k!='common_packages'} for r in country_rows]).to_csv(ROOT/'gp_source_comparison.csv',index=False,encoding='utf-8-sig');pd.DataFrame(common).to_csv(ROOT/'gp_common_apps.csv',index=False,encoding='utf-8-sig')
    freq=[]
    for package in sorted(set(r['package'] for r in common)):
        rs=[r for r in common if r['package']==package];f=rs[0];freq.append({k:f[k] for k in ['package','name','subclass','brief']}|{'country_count':len(rs),'positions':{r['country']:r['appmagic_rank'] for r in rs},'comparisons':rs})
    freq.sort(key=lambda a:(-a['country_count'],a['name']));comparables=[r for r in country_rows if r['comparable']]
    covered={c['country'] for c in magic['charts']+data['charts']};missing=[COUNTRIES[c] for c in COUNTRIES if c not in covered]
    conclusion=f"GP榜单日期{magic['date']}：AppMagic取得{len(magic['charts'])}/13国，Sensor Tower取得{len(data['charts'])}/13国，合并覆盖{len(covered)}国；"+('、'.join(missing)+'仍缺数。' if missing else '13国均有至少一份榜单。')
    if comparables:
        best=max(comparables,key=lambda r:r['overlap_count']);least=min(comparables,key=lambda r:r['overlap_count'])
        conclusion+=f"{len(comparables)}个共同覆盖国家的Top10，共同APP平均{sum(r['overlap_count'] for r in comparables)/len(comparables):.2f}款；{COUNTRIES[best['country']]}最高{best['overlap_count']}款，{COUNTRIES[least['country']]}最低{least['overlap_count']}款。"
    else:conclusion+='没有取得同日双源榜单，不能计算重合度。'
    conclusion+='两榜不完全一致；分类及排序方法不同可能影响重合度，不能合并成下载量。'
    insights=[]
    if freq:insights.append('；'.join(a['name']+f"同时进入两源Top10共{a['country_count']}国" for a in freq[:2])+'，跨国热度得到两榜共同佐证。')
    russian=[c for c in magic['charts']+data['charts'] if c['country']=='RU']
    if len(russian)==2:
        network=[sum(a['subclass'].startswith(('VPN','代理','网络隧道')) for a in c['rows']) for c in russian];overlap=next(r['overlap_count'] for r in country_rows if r['country']=='RU')
        insights.append(f"俄罗斯AppMagic前10中有{network[0]}款、Sensor Tower前10中有{network[1]}款VPN、代理或网络隧道工具；两榜{overlap}款APP包名重合，网络连接用途较为集中。")
    india=[a for a in common if a['country']=='IN']
    if india:insights.append('印度两榜共同APP为'+'、'.join(a['name'] for a in india)+f"，共{len(india)}款；不能据此认定印度整体榜单一致。")
    comparison={'date':magic['date'],'countries':country_rows,'common_apps':common,'common_frequency':freq,'conclusion':conclusion,'insights':insights,'method':'同日、同国家、同平台，按包名对应；比较Top10交集及各自名次，不混合指标'}
    return data,comparison
if __name__=='__main__':acquire_metadata()
