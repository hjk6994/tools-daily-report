"""依据 PalmStore 官方页面公开脚本采集榜单；保留真实请求国家和来源路由。"""
import sys,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import requests,pandas as pd
from collect import config,now

def collect_country(country):
    # 域名与参数逐项来自已保存的官方前端脚本，不尝试未知接口。
    base={'IN':'https://ind-feature-api-dcdn.palmplaystore.com','RU':'https://ee1-feature-api-dcdn.palmplaystore.com'}.get(country,'https://feature-api-dcdn.palmplaystore.com')
    chart=str(config().get('ps_chart_ids',{}).get(country,config()['ps_chart_id']))
    params={'rankId':chart,'countryCode':country,'systemVerCode':'31','supportSubPkg':'true','cpu':'arm64-v8a,armeabi-v7a,armeabi','pageIndex':0,'pageSize':180}
    stamp=now();file=ROOT/'data'/'raw'/f'ps_api_{country}_{stamp[:10]}.json'
    audit={'requested_country':country,'collected_at':stamp,'source_url':f'https://www.palmplaystore.com/rank/{chart}?country={country}','endpoint':base+'/feature/singleRank','request_body':params,'snapshot':str(file.relative_to(ROOT)),'route_evidence':'data/raw/ps_public_bundle.js','params_evidence':'data/raw/ps_rank_bundle.js','top_k':20,'platform_refresh_time':None}
    rows=[]
    try:
        response=requests.post(base+'/feature/singleRank',json=params,timeout=20)
        file.write_text(response.text,encoding='utf-8')
        obj=response.json();d=obj.get('data');items=(d.get('data') or []) if isinstance(d,dict) else []
        audit.update(http_status=response.status_code,business_code=obj.get('code'),returned_country=d.get('countryCode') if isinstance(d,dict) else None,chart_name=d.get('rankName') if isinstance(d,dict) else None,chart_id=d.get('rankId') if isinstance(d,dict) else None,depth=len(items),data_mark=d.get('dataMark') if isinstance(d,dict) else None)
        if response.status_code!=200 or obj.get('code') not in [0,200,'0','200']:audit['status']='request_failure'
        elif not isinstance(d,dict) or not isinstance(items,list):audit['status']='parse_failure'
        elif d.get('countryCode') and d['countryCode']!=country:audit['status']='country_mismatch'
        elif len(items)<20:audit['status']='insufficient_top20' if items else 'success_empty'
        else:audit['status']='top20_acquired_country_unconfirmed' if not d.get('countryCode') else 'complete_top20'
        audit['country_verification']='响应未返回国家；需页面地区及多国内容比较核验' if not audit['returned_country'] else '响应国家匹配'
        for rank,item in enumerate(items,1):
            rows.append({'observation_date':stamp[:10],'collected_at':stamp,'requested_country':country,'actual_country':audit['returned_country'],'chart_id':d.get('rankId'),'chart_name':d.get('rankName'),'rank':rank,'package':item.get('packageName'),'platform_id':item.get('itemID'),'name':item.get('name'),'description':item.get('simpleDescription'),'icon_url':item.get('iconUrl'),'detail_url':f'https://www.palmplaystore.com/detail/{item.get("packageName")}?country={country}','snapshot':audit['snapshot'],'status':audit['status']})
    except Exception as err:audit.update(status='request_failure',error_type=type(err).__name__,depth=0)
    file.with_suffix('.audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:audit.get(k) for k in ['requested_country','status','depth','returned_country','chart_name','error_type']},ensure_ascii=False),flush=True)
    return audit,rows

def main():
    with ThreadPoolExecutor(max_workers=3) as executor:results=list(executor.map(collect_country,config()['ps_countries']))
    audits=[r[0] for r in results];rows=[x for _,rs in results for x in rs]
    (ROOT/'data'/'ps_multicountry_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
    pd.DataFrame(rows).to_csv(ROOT/'ps_multicountry_snapshots.csv',index=False,encoding='utf-8-sig')
    return audits,rows
if __name__=='__main__':main()
