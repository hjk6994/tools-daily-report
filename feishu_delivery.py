"""通过飞书应用机器人发送日报HTML；凭证只在进程内使用。"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import requests

ENV_KEYS=('FEISHU_APP_ID','FEISHU_APP_SECRET','FEISHU_CHAT_ID')
OPTIONAL_KEYS=('FEISHU_WEBHOOK',)
API='https://open.feishu.cn/open-apis'


class DeliveryError(RuntimeError):
    pass


def credentials(root=ROOT):
    values={key:os.environ.get(key,'') for key in ENV_KEYS+OPTIONAL_KEYS}
    path=Path(root)/'.env.feishu'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            key,value=line.split('=',1)
            if key.strip() in values and not values[key.strip()]:
                values[key.strip()]=value.strip().strip('"').strip("'")
    return values


def configured(root=ROOT):
    values=credentials(root)
    return all(values[key] for key in ENV_KEYS)


def api_json(response):
    if response.status_code>=500 or response.status_code==408:response.raise_for_status()
    obj=response.json()
    if obj.get('code')!=0:
        # 不将响应正文、请求头或凭证写进日志。
        raise DeliveryError('飞书接口失败，错误码：'+str(obj.get('code','未知')))
    response.raise_for_status()
    return obj


def find_chat(name,root=ROOT,session=None):
    """仅核对机器人已加入群的名称与ID，不读取群消息；唯一匹配才保存目标。"""
    secret=credentials(root)
    if not secret['FEISHU_APP_ID'] or not secret['FEISHU_APP_SECRET']:
        raise DeliveryError('请先配置应用凭证')
    client=session or requests.Session()
    auth=api_json(client.post(API+'/auth/v3/tenant_access_token/internal',json={
        'app_id':secret['FEISHU_APP_ID'],'app_secret':secret['FEISHU_APP_SECRET']},timeout=30))
    headers={'Authorization':'Bearer '+auth['tenant_access_token']}
    matches=[];page_token=''
    while True:
        params={'page_size':100}
        if page_token:params['page_token']=page_token
        data=api_json(client.get(API+'/im/v1/chats',headers=headers,params=params,timeout=30))['data']
        matches.extend(a for a in data.get('items',[]) if a.get('name')==name)
        if not data.get('has_more'):break
        token=data.get('page_token')
        if not token or token==page_token:raise DeliveryError('群列表分页未完成，暂停配置目标')
        page_token=token
    if len(matches)!=1:raise DeliveryError('目标群唯一匹配未通过，匹配数量：'+str(len(matches)))
    chat_id=matches[0].get('chat_id','')
    if not chat_id.startswith('oc_'):raise DeliveryError('群ID格式不正确')
    path=Path(root)/'.env.feishu'
    lines=path.read_text(encoding='utf-8-sig').splitlines() if path.exists() else []
    lines=[line for line in lines if not line.startswith('FEISHU_CHAT_ID=')]
    lines.append('FEISHU_CHAT_ID='+chat_id)
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {'status':'chat_configured','group':name,'unique_match':True}


def send_html(path, report_date, root=ROOT, dry_run=False, session=None):
    path=Path(path).resolve();root=Path(root).resolve()
    datetime.fromisoformat(report_date)
    if not path.is_relative_to(root/'output'):
        raise DeliveryError('只允许发送本项目output目录中的日报')
    if path.name!='工具类APP热度趋势日报'+report_date.replace('-','')+'.html':
        raise DeliveryError('日报文件名与报告日期不匹配')
    size=path.stat().st_size
    if not 0<size<=30_000_000:raise DeliveryError('附件必须非空，且不超过30MB')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    secret=credentials(root)
    content=path.read_text(encoding='utf-8')
    if any(value and value in content for value in secret.values()):
        raise DeliveryError('日报包含凭证内容，暂停发送')
    ready=all(secret[key] for key in ENV_KEYS)
    if dry_run or not ready:
        return {'status':'dry_run' if dry_run else 'configuration_missing','file':path.name,
                'bytes':size,'configured':ready,'webhook_configured':bool(secret['FEISHU_WEBHOOK']),'sent':False}
    if not secret['FEISHU_CHAT_ID'].startswith('oc_'):
        raise DeliveryError('请配置目标飞书群chat_id，格式以oc_开头')
    recipient=hashlib.sha256(secret['FEISHU_CHAT_ID'].encode()).hexdigest()
    directory=root/'data/automation';directory.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(directory/'feishu_delivery.sqlite',timeout=15)
    key=report_date+'|'+recipient
    request_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'tools-daily:'+key))
    def status(value,message_id=''):
        with db:
            db.execute('UPDATE deliveries SET status=?,message_id=? WHERE delivery_key=?',(value,message_id,key))
    try:
        db.execute('CREATE TABLE IF NOT EXISTS deliveries (delivery_key TEXT PRIMARY KEY, status TEXT NOT NULL, sha256 TEXT NOT NULL, message_id TEXT)')
        db.execute('BEGIN IMMEDIATE')
        previous=db.execute('SELECT status FROM deliveries WHERE delivery_key=?',(key,)).fetchone()
        if previous and previous[0]=='sent':
            db.commit();return {'status':'already_sent','file':path.name,'sent':False}
        if previous and previous[0] in ['pending','sending','uncertain']:
            db.rollback();raise DeliveryError('上次发送结果待核对，暂停再次发送以避免重复')
        db.execute('INSERT OR REPLACE INTO deliveries VALUES (?,?,?,?)',(key,'pending',digest,''));db.commit()
        client=session or requests.Session()
        phase='prepare'
        try:
            auth=api_json(client.post(API+'/auth/v3/tenant_access_token/internal',json={
                'app_id':secret['FEISHU_APP_ID'],'app_secret':secret['FEISHU_APP_SECRET']},timeout=30))
            headers={'Authorization':'Bearer '+auth['tenant_access_token']}
            with path.open('rb') as stream:
                uploaded=api_json(client.post(API+'/im/v1/files',headers=headers,
                    data={'file_type':'stream','file_name':path.name},
                    files={'file':(path.name,stream,'application/octet-stream')},timeout=45))
            file_key=uploaded['data']['file_key']
            status('sending');phase='send'
            message=api_json(client.post(API+'/im/v1/messages',params={'receive_id_type':'chat_id'},
                headers=headers,json={'receive_id':secret['FEISHU_CHAT_ID'],'msg_type':'file',
                'content':json.dumps({'file_key':file_key}), 'uuid':request_id},timeout=30))
            message_id=message['data']['message_id']
            status('sent',message_id)
            return {'status':'sent','file':path.name,'sent':True}
        except DeliveryError:
            status('failed');raise
        except Exception as err:
            status('uncertain' if phase=='send' else 'failed')
            raise DeliveryError('发送阶段结果待核对' if phase=='send' else '附件准备失败：'+type(err).__name__) from None
    finally:
        db.close()


def main():
    parser=argparse.ArgumentParser(description='发送日报HTML到已配置的飞书群')
    parser.add_argument('--date',default=datetime.now(timezone(timedelta(hours=8))).date().isoformat())
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--find-chat',help='核对已加入群并私密保存唯一匹配的群ID')
    args=parser.parse_args()
    path=ROOT/'output'/('工具类APP热度趋势日报'+args.date.replace('-','')+'.html')
    try:result=find_chat(args.find_chat) if args.find_chat else send_html(path,args.date,dry_run=args.dry_run)
    except DeliveryError as err:result={'status':'failed','reason':str(err),'sent':False}
    except Exception as err:result={'status':'failed','error_type':type(err).__name__,'sent':False}
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result['status']=='failed' else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.exit(main())
