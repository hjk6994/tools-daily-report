"""每日增量采集、不可丢失的运行归档与离线HTML生成；GP由获授权浏览器采集。"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import pandas as pd
from collect import safe_get, now, config
import gp20_analysis as gp20

TZ=timezone(timedelta(hours=8))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def dates(end,n):
    return [(datetime.fromisoformat(end)-timedelta(days=i)).date().isoformat() for i in reversed(range(n))]


def dsp_valid(obj,day):
    if obj.get('status')!=200 or not isinstance(obj.get('data'),list):return False
    if set(obj).intersection({'total','page','has_more','cursor','next','pagination'}):return False
    for row in obj['data']:
        if row.get('dt')!=day or not isinstance(row.get('app_id'),str):return False
        for key in ['resp','total_revenue']:
            value=row.get(key)
            if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:return False
    return True


def dsp_cached(day,root=None):
    path=Path(root or ROOT)/'data/raw'/f'dsp_{day}.json'
    try:return path.exists() and dsp_valid(load(path),day)
    except (ValueError,OSError):return False


def plan(report_date):
    end=(datetime.fromisoformat(report_date)-timedelta(days=1)).date().isoformat()
    observations=gp20.source_observations()
    observed={(x['country'],x['date']) for x in observations}
    task_file=ROOT/'data/automation/task.json'
    task=load(task_file) if task_file.exists() else {}
    # 逐国采集过程中，较新日期先成功也不能跳过此前尚未处理的新日期。
    last=max((x['date'] for x in observations if x['date']<=end),default=end)
    baseline=task.get('GP_incremental_start_date',(datetime.fromisoformat(last)+timedelta(days=1)).date().isoformat())
    start=max(baseline,dates(end,20)[0])
    pending_days=[d for d in dates(end,20) if d>=start] or [end]
    jobs=[]
    for day in pending_days:
        for country in gp20.COUNTRIES:
            if (country,day) in observed:continue
            prior=sorted((x for x in observations if x['country']==country),key=lambda x:x.get('collected_at',''))
            jobs.append({'country':country,'requested_date':day,'entry_url':prior[-1]['url'] if prior else None})
    return {'report_date':report_date,'business_date':end,'DSP_missing_dates':[d for d in dates(end,14) if not dsp_cached(d)],
            'GP_browser_jobs':jobs,'PalmStore_snapshot_date':report_date,'schedule_timezone':'Asia/Shanghai','schedule_time':'10:00'}


def new_run(report_date):
    stamp=datetime.now(TZ).strftime('%H%M%S_%f')
    directory=ROOT/'data/daily_runs'/report_date/stamp
    directory.mkdir(parents=True,exist_ok=False)
    save(directory/'run.json',{'report_date':report_date,'started_at':now(),'status':'started'})
    return directory


def collect_dsp(day,run):
    path=ROOT/'data/raw'/f'dsp_{day}.json'
    if dsp_cached(day):
        return {'date':day,'status':'cached','snapshot':str(path.relative_to(ROOT)),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    if not os.environ.get('DSP_API_TOKEN'):return {'date':day,'status':'missing_credential'}
    try:
        code,content=safe_get('https://click.aitoadv.com/rtb/revenue',{'token':os.environ['DSP_API_TOKEN'],'dt':day})
        (run/f'dsp_{day}.json').write_text(content,encoding='utf-8')
        obj=json.loads(content)
        if code!=200 or not dsp_valid(obj,day):return {'date':day,'status':'invalid_response'}
        if path.exists():shutil.copy2(path,run/f'dsp_{day}_before_retry.json')
        path.write_text(content,encoding='utf-8')
        audit={'source':'DSP','requested_date':day,'collected_at':now(),'status':'response_complete' if obj['data'] else 'success_empty',
               'records':len(obj['data']),'snapshot':str(path.relative_to(ROOT)),'scope':'unknown','day_finalization':'unknown'}
        save(path.with_suffix('.audit.json'),audit)
        return audit
    except Exception as err:return {'date':day,'status':'request_failure','error_type':type(err).__name__}


def update_dsp_csv():
    path=ROOT/'dsp_daily.csv'
    existing_dates=set()
    columns=None
    if path.exists():
        columns=pd.read_csv(path,nrows=0).columns.tolist()
        existing_dates=set(pd.read_csv(path,usecols=['date']).date.astype(str))
    for snapshot in sorted((ROOT/'data/raw').glob('dsp_????-??-??.json')):
        day=snapshot.stem[4:]
        if day in existing_dates:continue
        obj=load(snapshot)
        if not dsp_valid(obj,day) or not obj['data']:continue
        frame=pd.DataFrame(obj['data']).rename(columns={'dt':'date','app_id':'package','resp':'downloads','total_revenue':'raw_revenue'})
        frame['snapshot']=str(snapshot.relative_to(ROOT));frame['revenue_usd']=frame.raw_revenue/1000
        frame['unit_price_usd']=frame.revenue_usd/frame.downloads.where(frame.downloads>0)
        frame['record_status']=frame.downloads.map(lambda n:'explicit_zero' if n==0 else 'observed')
        frame['currency']='USD';frame['scope_status']='unknown'
        if columns:frame=frame.reindex(columns=columns)
        frame.to_csv(path,index=False,encoding='utf-8-sig',mode='a' if path.exists() else 'w',header=not path.exists())
        columns=frame.columns.tolist();existing_dates.add(day)


def refresh_metadata(packages):
    """仅请求未核验APP公开资料；失败对象不冒充已核验工具。"""
    from metadata import get_meta
    from app_functions import function_for
    from concurrent.futures import ThreadPoolExecutor
    path=ROOT/'comparison_metadata.csv'
    frame=pd.read_csv(path).fillna('')
    known=set(frame.loc[frame.metadata_status=='verified','package'])
    pending=sorted(p for p in set(packages)-known if re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+',p))
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(get_meta,pending))
    for row in results:
        info=function_for(row['package'],row.get('name',''),row.get('summary',''),row.get('official_category','')) if row.get('metadata_status')=='verified' else None
        row.update(business_subclass=info[0] if info else '',brief=info[1] if info else '',is_tool=bool(info),
                   classification_basis='公开资料与主用途核验' if info else '主要功能不属于工具用途或资料未核验')
        frame=frame[frame.package!=row['package']]
        frame=pd.concat([frame,pd.DataFrame([row])],ignore_index=True)
    if results:frame.to_csv(path,index=False,encoding='utf-8-sig')
    return {'new_or_retried':len(results),'verified':sum(r.get('metadata_status')=='verified' for r in results)}


def palm_payload(country,path,chart_id):
    obj=load(path);d=obj.get('data')
    rows=d.get('data') if isinstance(d,dict) else None
    if obj.get('code') not in [0,200,'0','200'] or not isinstance(rows,list) or len(rows)<20:
        raise ValueError('PalmStore前20不完整')
    if str(d.get('rankId'))!=str(chart_id) or d.get('countryCode') not in [None,'',country]:
        raise ValueError('PalmStore列表或国家不匹配')
    return d,rows


def collect_palm(report_date,run):
    from ps_public import collect_country
    links=load(sorted((ROOT/'data/raw').glob('ps_browser_links_*.json'))[-1]);linkmap={a['country']:a for a in links}
    observations=[];audits=[];packages=[]
    for country in config()['ps_countries']:
        source=ROOT/'data/raw'/f'ps_api_{country}_{report_date}.json'
        chart=linkmap[country]['chart_id']
        try:
            try:palm_payload(country,source,chart);cached=True
            except (ValueError,OSError):
                if report_date!=datetime.now(TZ).date().isoformat():raise ValueError('PalmStore只采集当前快照，不回填历史日期')
                if source.exists():shutil.copy2(source,run/f'ps_{country}_before_retry.json')
                fetched,_=collect_country(country);cached=False
                if fetched.get('status') not in ['complete_top20','top20_acquired_country_unconfirmed']:
                    save(run/f'ps_{country}_failure.audit.json',fetched)
                    if source.exists():shutil.copy2(source,run/f'ps_{country}_failure.json')
                    audits.append(fetched);continue
            d,rows=palm_payload(country,source,chart)
            if d.get('rankName')!=linkmap[country]['chart_name']:raise ValueError('PalmStore榜单名称不匹配')
            shutil.copy2(source,run/f'ps_{country}.json')
            audit={'requested_country':country,'actual_country':d.get('countryCode'),'chart_id':str(chart),'chart_name':d.get('rankName'),
                   'collected_at':datetime.fromtimestamp(source.stat().st_mtime,TZ).isoformat(),'snapshot':str(source.relative_to(ROOT)),
                   'depth':len(rows),'status':'complete_top20' if d.get('countryCode') else 'top20_acquired_country_unconfirmed','cache':cached,
                   'country_verification':'使用已核验路由及请求国家参数；本日响应地区字段为空' if not d.get('countryCode') else '响应国家匹配'}
            observations.append({'country':country,'rows':rows[:20],'chart_name':d['rankName']});audits.append(audit)
            packages.extend(r.get('packageName','') for r in rows[:20])
        except Exception as err:audits.append({'requested_country':country,'status':'failed','error_type':type(err).__name__})
    save(run/'palmstore.json',{'observation_date':report_date,'charts':observations,'audits':audits})
    return observations,audits,packages


def palm_view(observations):
    from app_functions import function_for
    from comparison_report import PS_TOOLS
    frequency={}
    for chart in observations:
        for rank,row in enumerate(chart['rows'],1):
            package=row.get('packageName')
            if not package:continue
            meta=gp20.cached_metadata(package)
            info=function_for(package,meta.get('name',''),meta.get('summary',''),meta.get('official_category','')) if meta.get('metadata_status')=='verified' or package in PS_TOOLS else None
            if not info:continue
            name=PS_TOOLS[package][0] if package in PS_TOOLS else meta.get('name') or row.get('name',package)
            a=frequency.setdefault(package,{'package':package,'name':name,'subclass':info[0],'brief':info[1],'positions':{},'top_charts_count':0,'editor_count':0})
            a['positions'][chart['country']]=rank
            a['editor_count' if chart['chart_name']=="Editor's Choice" else 'top_charts_count']+=1
    result=list(frequency.values())
    for a in result:
        a['country_count']=len(a['positions']);a['mean_position']=sum(a['positions'].values())/a['country_count']
        hot=[rank for c,rank in a['positions'].items() if c not in ['IN','RU']]
        editors=[rank for c,rank in a['positions'].items() if c in ['IN','RU']]
        a.update(mean_top_charts_rank=sum(hot)/len(hot) if hot else None,mean_editor_position=sum(editors)/len(editors) if editors else None,
                 best_top_charts_rank=min(hot) if hot else None)
    return sorted(result,key=lambda a:(-a['country_count'],a['package']))


def collect(report_date):
    request=plan(report_date);run=new_run(report_date)
    dsp=[collect_dsp(d,run) for d in dates(request['business_date'],14)]
    update_dsp_csv()
    observations,audits,packages=collect_palm(report_date,run)
    snapshot=ROOT/'data/raw'/f'dsp_{request["business_date"]}.json'
    if dsp_cached(request['business_date']):packages.extend(r['app_id'] for r in load(snapshot)['data'])
    meta=refresh_metadata(packages)
    complete=dsp_cached(request['business_date']) and len(observations)==len(config()['ps_countries'])
    state={'report_date':report_date,'run':str(run.relative_to(ROOT)),'DSP':dsp,'PalmStore':audits,'metadata':meta,
           'status':'collected' if complete else 'partial','PalmStore_complete_countries':len(observations)}
    save(run/'run.json',state);save(ROOT/'data/automation'/f'collection_{report_date}.json',state)
    return state


def import_gp(path,report_date):
    end=(datetime.fromisoformat(report_date)-timedelta(days=1)).date().isoformat()
    incoming=load(path)
    rows=[gp20.validate_observation(a) for a in incoming['charts']]
    if any(a['date'] not in dates(end,20) for a in rows):raise ValueError('GP观察日期不在本次20日窗口中')
    run=new_run(report_date);save(run/'gp_observation.json',incoming)
    target=ROOT/'data/raw'/f'sensortower_top20_daily_observed_{report_date.replace("-","")}.json'
    previous=load(target) if target.exists() else {'source':'Sensor Tower','platform':'Google Play','category':'工具','charts':[]}
    merged={(a['country'],a['date']):a for a in previous['charts']}
    for a in rows:
        key=a['country'],a['date']
        if key in merged and not merged[key].get('no_chart') and a.get('no_chart'):continue
        if key in merged and len(merged[key]['rows'])>len(a['rows']):continue
        merged[key]=a
    previous['charts']=list(merged.values());save(target,previous)
    meta=refresh_metadata([r['package'] for a in rows for r in a['rows']])
    return {'imported_observations':len(rows),'snapshot':str(target.relative_to(ROOT)),'metadata':meta}


def render_html(data,path):
    if data.get('weekly_growth'):
        from weekly_report import render_html as render_weekly
        return render_weekly(data,path)
    name='工具类APP热度趋势日报'+data['report_date'].replace('-','')
    template=(ROOT/'period_template.html').read_text(encoding='utf-8')
    text=template.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</',r'<\/')).replace('__SCRIPT__',(ROOT/'period_script.js').read_text(encoding='utf-8'))
    text=text.replace('__REPORT_NAME__',name).replace('__PS_DATE__',str(data['ps_observation_date']))
    Path(path).write_text(text,encoding='utf-8')


def build(report_date):
    """历史缓存整合生成当日HTML；DSP前一天无可用记录时停止发布。"""
    end=(datetime.fromisoformat(report_date)-timedelta(days=1)).date().isoformat()
    if not dsp_cached(end) or not load(ROOT/'data/raw'/f'dsp_{end}.json')['data']:
        raise ValueError('前一天DSP未取得有效应用记录，暂停发布日报')
    update_dsp_csv();run=new_run(report_date)
    source=ROOT/'data/comparison_report_data.json';data=load(source)
    shutil.copy2(source,run/'before_report_data.json')
    data['report_date']=report_date;data['dsp_end']=end
    collection=ROOT/'data/automation'/f'collection_{report_date}.json'
    if collection.exists():
        state=load(collection);palm=load(ROOT/state['run']/'palmstore.json')
        if len(palm['charts'])==len(config()['ps_countries']):
            data['ps_frequency']=palm_view(palm['charts']);data['ps_observation_date']=report_date;data['ps_audit']=palm['audits']
    from period_analysis import build as period
    from daily_tables import build as daily
    from palmstore_view import build as palmstore
    data['period_analysis']=period(data);data['daily_tables']=daily(data)
    data['palmstore_view']=palmstore(data);data['gp20_analysis']=gp20.build(data)
    data['app_functions']=list({a['package']:a for a in data['app_functions']+[{
        k:a[k] for k in ['package','name','subclass','brief']} for a in data['ps_frequency']]}.values())
    if report_date>='2026-10-13':
        from weekly_growth import build as weekly
        data['weekly_growth']=weekly(data)
        data['report_schema']='weekly_growth_v1'
    else:
        data.pop('weekly_growth',None)
    data['automation']={'report_date':report_date,'business_date':end,'generated_at':now(),'mode':'incremental','retention':'原始快照及每日运行全部保留'}
    name='工具类APP热度趋势日报'+report_date.replace('-','');output=ROOT/'output';output.mkdir(exist_ok=True)
    target=output/(name+'.html')
    if target.exists():shutil.copy2(target,run/'before_report.html')
    render_html(data,target);save(source,data);save(run/'report_data.json',data);shutil.copy2(target,run/target.name)
    (output/'latest.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='+name+'.html"><a href="'+name+'.html">'+name+'</a>',encoding='utf-8')
    result={'status':'generated','report_date':report_date,'html':str(target.relative_to(ROOT)),
            'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'run':str(run.relative_to(ROOT)),
            'GP_current_date_charts':sum((c,end) in gp20.source_charts() for c in gp20.COUNTRIES),'GP_countries_requested':len(gp20.COUNTRIES),
            'PalmStore_snapshot_date':data['ps_observation_date']}
    save(run/'run.json',result);save(ROOT/'data/automation'/f'report_{report_date}.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description='增量日报：规划、采集、导入浏览器GP日榜、生成HTML')
    parser.add_argument('action',choices=['prepare','collect','import-gp','build','send'])
    parser.add_argument('--date',default=datetime.now(TZ).date().isoformat())
    parser.add_argument('--input');parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args();datetime.fromisoformat(args.date)
    if args.action=='prepare':result=plan(args.date)
    elif args.action=='collect':result=plan(args.date) if args.dry_run else collect(args.date)
    elif args.action=='import-gp':result=import_gp(args.input,args.date)
    elif args.action=='build':result=build(args.date)
    else:
        from feishu_delivery import send_html
        result=send_html(ROOT/'output'/('工具类APP热度趋势日报'+args.date.replace('-','')+'.html'),args.date,dry_run=args.dry_run)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:main()
    except Exception as err:
        print(json.dumps({'status':'failed','error_type':type(err).__name__,
                          'reason':str(err) if isinstance(err,ValueError) else '请查看阶段运行记录；未输出凭证'},ensure_ascii=False));sys.exit(1)
