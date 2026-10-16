# 安全说明：认证形态常量仅为单元测试固定模拟值，不来自真实配置。
# Webhook采用保留域名example.invalid；不得填入真实认证，网络交互使用模拟会话。
"""核验增量缓存、历史保留、失败保护及飞书附件防重发；不调用真实接口。"""
import hashlib
import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.deps'))
import requests
import daily_automation as job
import feishu_delivery as feishu
import gp20_analysis as gp


class DailyAutomation(unittest.TestCase):
    def setUp(self):
        # 项目禁止批量删除，测试文件保留在忽略的tmp目录。
        self.root=ROOT/'tmp/automation_tests'/uuid.uuid4().hex
        (self.root/'data/raw').mkdir(parents=True)
        (self.root/'output').mkdir()
        self.run=self.root/'run';self.run.mkdir()

    def dsp(self,day='2026-10-09',downloads=500):
        return {'status':200,'data':[{'dt':day,'app_id':'app.test.tool','country':'PK','resp':downloads,'total_revenue':2000}]}

    def snapshot(self,day='2026-10-09'):
        p=self.root/'data/raw'/f'dsp_{day}.json';p.write_text(json.dumps(self.dsp(day)),encoding='utf-8');return p

    def chart(self,no_chart=False):
        url='https://app.sensortower.com/top-charts?category=tools&country=PK&os=android&date=2026-10-09'
        return {'url':url,'country':'PK','date':'2026-10-09','collected_at':'2026-10-10T10:00:00+08:00','no_chart':no_chart,
                'rows':[] if no_chart else [{'rank':i,'name':'工具','package':f'app.test.tool{i}','publisher_url':url+'&package='+str(i)} for i in range(1,21)]}

    def test_existing_dsp_is_not_requested_or_overwritten(self):
        p=self.snapshot();before=hashlib.sha256(p.read_bytes()).hexdigest()
        with patch.object(job,'ROOT',self.root),patch.object(job,'safe_get') as network:
            result=job.collect_dsp('2026-10-09',self.run)
        self.assertEqual(result['status'],'cached');network.assert_not_called()
        self.assertEqual(before,hashlib.sha256(p.read_bytes()).hexdigest())

    def test_bad_response_is_preserved_but_never_becomes_success_cache(self):
        bad=json.dumps(self.dsp('2026-10-08'))
        with patch.object(job,'ROOT',self.root),patch.dict(os.environ,{'DSP_API_TOKEN':'测试令牌'}),patch.object(job,'safe_get',return_value=(200,bad)):
            result=job.collect_dsp('2026-10-09',self.run)
        self.assertEqual(result['status'],'invalid_response')
        self.assertTrue((self.run/'dsp_2026-10-09.json').exists())
        self.assertFalse((self.root/'data/raw/dsp_2026-10-09.json').exists())

    def test_csv_append_is_idempotent_and_keeps_history(self):
        self.snapshot('2026-10-08')
        with patch.object(job,'ROOT',self.root):job.update_dsp_csv()
        self.snapshot('2026-10-09')
        with patch.object(job,'ROOT',self.root):job.update_dsp_csv();job.update_dsp_csv()
        frame=job.pd.read_csv(self.root/'dsp_daily.csv')
        self.assertEqual(len(frame),2);self.assertEqual(set(frame.date),{'2026-10-08','2026-10-09'})
        self.assertEqual(frame.revenue_usd.tolist(),[2,2])

    def test_plan_only_fetches_new_dsp_day_after_history_exists(self):
        for d in job.dates('2026-10-09',14):self.snapshot(d)
        with patch.object(job,'ROOT',self.root),patch.object(gp,'source_observations',return_value=[self.chart()]):
            result=job.plan('2026-10-11')
        self.assertEqual(result['DSP_missing_dates'],['2026-10-10'])
        self.assertEqual({x['requested_date'] for x in result['GP_browser_jobs']},{'2026-10-10'})

    def test_later_failed_gp_observation_does_not_erase_success(self):
        one=self.root/'one.json';two=self.root/'two.json'
        one.write_text(json.dumps({'charts':[self.chart()]}),encoding='utf-8')
        failed=self.chart(True);failed['collected_at']='2026-10-10T11:00:00+08:00'
        two.write_text(json.dumps({'charts':[failed]}),encoding='utf-8')
        with patch.object(gp,'snapshot_files',return_value=[one,two]):charts=gp.source_charts()
        self.assertEqual(len(charts['PK','2026-10-09']['rows']),20)

    def test_gp_country_date_mismatch_is_rejected(self):
        chart=self.chart();chart['rows'][0]['publisher_url']=chart['rows'][0]['publisher_url'].replace('country=PK','country=IN')
        with self.assertRaises(ValueError):gp.validate_observation(chart)

    def test_newer_partial_gp_day_does_not_skip_previous_pending_day(self):
        (self.root/'data/automation').mkdir()
        (self.root/'data/automation/task.json').write_text(json.dumps({'GP_incremental_start_date':'2026-10-10'}),encoding='utf-8')
        observations=[dict(self.chart(),date='2026-10-11')]
        with patch.object(job,'ROOT',self.root),patch.object(gp,'source_observations',return_value=observations):
            result=job.plan('2026-10-12')
        jobs={(a['country'],a['requested_date']) for a in result['GP_browser_jobs']}
        self.assertIn(('PK','2026-10-10'),jobs)
        self.assertNotIn(('PK','2026-10-11'),jobs)
        self.assertIn(('IN','2026-10-11'),jobs)

    def test_missing_yesterday_blocks_report_publish(self):
        with patch.object(job,'dsp_cached',return_value=False):
            with self.assertRaisesRegex(ValueError,'暂停发布'):job.build('2026-10-12')


class FeishuDelivery(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'tmp/automation_tests'/uuid.uuid4().hex
        (self.root/'output').mkdir(parents=True)
        self.path=self.root/'output/工具类APP热度趋势日报20261010.html'
        self.path.write_text('<!doctype html><meta charset="utf-8"><p>日报</p>',encoding='utf-8')
        self.env={'FEISHU_APP_ID':'cli_test','FEISHU_APP_SECRET':'测试应用密钥','FEISHU_CHAT_ID':'oc_test'}

    def response(self,obj,status=200):
        r=Mock();r.status_code=status;r.json.return_value=obj;r.raise_for_status.return_value=None;return r

    def session(self,last=None):
        session=Mock()
        session.post.side_effect=[self.response({'code':0,'tenant_access_token':'测试访问令牌'}),
            self.response({'code':0,'data':{'file_key':'file_test'}}),
            last or self.response({'code':0,'data':{'message_id':'om_test'}})]
        return session

    def test_webhook_alone_is_not_file_attachment_configuration(self):
        with patch.dict(os.environ,{'FEISHU_WEBHOOK':'https://example.invalid/open-apis/bot/v2/hook/EXAMPLE_TEST_WEBHOOK'},clear=True):
            result=feishu.send_html(self.path,'2026-10-10',root=self.root,session=Mock())
        self.assertEqual(result['status'],'configuration_missing');self.assertFalse(result['sent'])

    def test_dry_run_never_sends_or_exposes_secret(self):
        client=Mock()
        with patch.dict(os.environ,self.env,clear=True):result=feishu.send_html(self.path,'2026-10-10',root=self.root,dry_run=True,session=client)
        client.post.assert_not_called();self.assertNotIn('测试应用密钥',str(result))

    def test_embedded_credential_blocks_upload(self):
        client=Mock()
        self.path.write_text('<html>'+self.env['FEISHU_CHAT_ID']+'</html>',encoding='utf-8')
        with patch.dict(os.environ,self.env,clear=True):
            with self.assertRaisesRegex(feishu.DeliveryError,'凭证'):
                feishu.send_html(self.path,'2026-10-10',root=self.root,session=client)
        client.post.assert_not_called()

    def test_group_id_is_only_saved_for_unique_exact_name(self):
        client=Mock();client.post.return_value=self.response({'code':0,'tenant_access_token':'测试访问令牌'})
        client.get.return_value=self.response({'code':0,'data':{'has_more':False,'items':[
            {'name':'日报发送测试群','chat_id':'oc_target_test'},{'name':'其他测试群','chat_id':'oc_other_test'}]}})
        with patch.dict(os.environ,self.env,clear=True):
            result=feishu.find_chat('日报发送测试群',root=self.root,session=client)
        self.assertEqual(result['status'],'chat_configured')
        self.assertIn('FEISHU_CHAT_ID=oc_target_test',(self.root/'.env.feishu').read_text(encoding='utf-8'))
        self.assertNotIn('oc_other_test',(self.root/'.env.feishu').read_text(encoding='utf-8'))

    def test_same_name_groups_block_destination_configuration(self):
        client=Mock();client.post.return_value=self.response({'code':0,'tenant_access_token':'测试访问令牌'})
        client.get.return_value=self.response({'code':0,'data':{'has_more':False,'items':[
            {'name':'目标群','chat_id':'oc_a'},{'name':'目标群','chat_id':'oc_b'}]}})
        with patch.dict(os.environ,self.env,clear=True):
            with self.assertRaisesRegex(feishu.DeliveryError,'唯一匹配'):
                feishu.find_chat('目标群',root=self.root,session=client)
        self.assertFalse((self.root/'.env.feishu').exists())

    def test_html_is_uploaded_as_stream_then_sent_as_file_once_per_day(self):
        client=self.session()
        with patch.dict(os.environ,self.env,clear=True):
            result=feishu.send_html(self.path,'2026-10-10',root=self.root,session=client)
            second=feishu.send_html(self.path,'2026-10-10',root=self.root,session=client)
        self.assertEqual(result['status'],'sent');self.assertEqual(second['status'],'already_sent')
        self.assertEqual(client.post.call_count,3)
        self.assertEqual(client.post.call_args_list[1].kwargs['data']['file_type'],'stream')
        message=client.post.call_args_list[2].kwargs['json']
        self.assertEqual(message['msg_type'],'file');self.assertEqual(json.loads(message['content']),{'file_key':'file_test'})
        stored=(self.root/'data/automation/feishu_delivery.sqlite').read_bytes()
        self.assertNotIn('测试应用密钥'.encode(),stored);self.assertNotIn('测试访问令牌'.encode(),stored)

    def test_message_timeout_blocks_unverified_resend(self):
        client=self.session(requests.Timeout('测试超时'))
        with patch.dict(os.environ,self.env,clear=True):
            with self.assertRaises(feishu.DeliveryError):feishu.send_html(self.path,'2026-10-10',root=self.root,session=client)
            with self.assertRaisesRegex(feishu.DeliveryError,'待核对'):feishu.send_html(self.path,'2026-10-10',root=self.root,session=client)
        self.assertEqual(client.post.call_count,3)


if __name__=='__main__':unittest.main()
