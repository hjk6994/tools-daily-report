"""采集入口；日志不输出凭证或带凭证 URL。"""
import json, os, sys, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import yaml
def config():
    return yaml.safe_load((ROOT/'config.yaml').read_text(encoding='utf-8'))
def load_env():
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1)
                if key.strip() in ['DSP_API_TOKEN','APPBRAIN_API_KEY']:
                    os.environ.setdefault(key.strip(),value.strip().strip('\"').strip("'"))
load_env()
RAW=ROOT/'data'/'raw'
RAW.mkdir(parents=True,exist_ok=True)
TZ=timezone(timedelta(hours=8))
def now(): return datetime.now(TZ).isoformat()
def safe_get(url,params):
    with urlopen(Request(url+'?'+urlencode(params),headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/html'}),timeout=55) as r:
        content=r.read().decode('utf-8')
        for key in ['DSP_API_TOKEN','APPBRAIN_API_KEY']:
            if os.environ.get(key): content=content.replace(os.environ[key],'[已脱敏]')
        return r.status,content
def dsp_day(day):
    path=RAW/f'dsp_{day}.json'
    audit={'source':'DSP','requested_date':day,'collected_at':now(),'parser_version':'1.0','mapping_version':'user-20261009','snapshot':str(path.relative_to(ROOT))}
    try:
        if path.exists():
            content=path.read_text(encoding='utf-8'); code=200
            audit['collected_at']=datetime.fromtimestamp(path.stat().st_mtime,TZ).isoformat()
            audit['cache']=True
        else:
            if not os.environ.get('DSP_API_TOKEN'): return {**audit,'status':'missing_credential'}
            code,content=safe_get('https://click.aitoadv.com/rtb/revenue',{'token':os.environ['DSP_API_TOKEN'],'dt':day})
            path.write_text(content,encoding='utf-8')
        data=json.loads(content)
        rows=data.get('data') if isinstance(data,dict) else None
        audit.update(http_status=code,business_status=data.get('status'),root_type=type(data).__name__,root_keys=list(data),array_path='data',records=len(rows) if isinstance(rows,list) else None)
        if code!=200 or data.get('status')!=200 or not isinstance(rows,list): audit['status']='business_failure'
        elif not rows: audit['status']='success_empty'
        elif any(x.get('dt')!=day for x in rows): audit['status']='date_mismatch'
        elif set(data).intersection({'total','page','has_more','cursor','next','pagination'}):
            audit.update(status='pagination_unverified',pagination='响应包含分页相关字段，适配器尚未核验，暂停正式使用')
        else:
            audit.update(status='response_complete',pagination='无分页或总条数字段',day_finalization='unknown',scope='unknown',fields={k:type(v).__name__ for k,v in rows[0].items()})
        path.with_suffix('.audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as e:
        audit.update(status='request_failure',error_type=type(e).__name__)
        path.with_suffix('.audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'date':day,'status':audit['status'],'records':audit.get('records')},ensure_ascii=False),flush=True)
    return audit
def dsp():
    cfg=config();end=cfg.get('dsp_end_date','yesterday')
    day=datetime.now(TZ).date()-timedelta(days=1) if end=='yesterday' else datetime.fromisoformat(end).date()
    days=[(day-timedelta(days=i)).isoformat() for i in reversed(range(cfg.get('dsp_history_days',14)))]
    with ThreadPoolExecutor(max_workers=3) as ex: audits=list(ex.map(dsp_day,days))
    (ROOT/'data'/'dsp_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
def ps():
    from ps_public import main
    return main()
if __name__=='__main__':
    {'dsp':dsp,'ps':ps}[sys.argv[1]]()
