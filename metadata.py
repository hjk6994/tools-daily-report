"""Google Play 公共资料核验；公开安装档位不视为每日下载。"""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'.deps'))
from google_play_scraper import app
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
from collect import ROOT,now
from concurrent.futures import ThreadPoolExecutor
def get_meta(package):
    path=ROOT/'data'/'raw'/f'gp_metadata_{package}.json'
    try:
        if path.exists(): data=json.loads(path.read_text(encoding='utf-8'))
        else:
            response=app(package,lang='en',country='us')
            fields=['appId','title','developer','genre','genreId','summary','description','installs','minInstalls','realInstalls','score','ratings','url','updated']
            data={k:response.get(k) for k in fields}
            data['collected_at']=now();data['requested_country']='us';data['country_status']='整体资料，不作为国家下载'
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return {'package':package,'name':data['title'],'developer':data['developer'],'official_category':data['genre'],'summary':data['summary'],'description':data['description'],'installs':data['installs'],'minInstalls':data['minInstalls'],'realInstalls':data['realInstalls'],'rating':data['score'],'ratingCount':data['ratings'],'verified_at':data['collected_at'],'verification_url':data['url'],'snapshot':str(path.relative_to(ROOT)),'metadata_status':'verified'}
    except Exception as e: return {'package':package,'metadata_status':'unknown','error_type':type(e).__name__}
def main():
    m=pd.read_csv(ROOT/'metrics.csv');d=pd.read_csv(ROOT/'dsp_daily.csv')
    qualified=m[m.numerical_qualified==True].package.tolist()
    latest=d[d.date==d.date.max()].groupby('package').downloads.sum().sort_values(ascending=False)
    # 额外资料用于绝对值展示，不用于提前截断 V3 候选。
    extras=latest[latest.index.str.contains('pdf|browser|clean|player|editor|launcher|storage|caller|share|file|cloud|scan|photo')].head(22).index.tolist()
    packages=list(dict.fromkeys(qualified+extras))
    with ThreadPoolExecutor(max_workers=3) as ex: rows=list(ex.map(get_meta,packages))
    for r in rows: print(json.dumps({k:r.get(k) for k in ['package','name','developer','official_category','summary','metadata_status']},ensure_ascii=False),flush=True)
    pd.DataFrame(rows).to_csv(ROOT/'app_metadata.csv',index=False,encoding='utf-8-sig')
if __name__=='__main__':main()
