"""核验联合原榜、完整历史、实际日期及国别身份；不联网。"""
import json
import sys
import unittest
import uuid
from unittest.mock import patch
from datetime import datetime,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import appmagic_growth as am
import appmagic_automation as incremental


class AppMagicGrowth(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'tmp/appmagic_tests'/uuid.uuid4().hex
        (self.root/'data/raw').mkdir(parents=True)
        self.countries=['PK','IN','NG','ID','BD','PH','IQ','RU','SA']
        self.days=[(datetime(2026,9,28)+timedelta(days=i)).date().isoformat() for i in range(14)]
        self.catalog={'app.test.tool':{'package':'app.test.tool','name':'测试工具','subclass':'PDF工具','brief':'读取文档。'}}

    def charts(self):
        charts=[]
        for i,day in enumerate(self.days):
            pos=80 if i<7 else 30
            packages=[f'app.test.extra{r}' for r in range(1,100)]
            packages.insert(pos-1,'app.test.tool')
            charts.append({'date':day,'shown_date':day,'collected_at':'2026-10-13T00:00:00Z',
                'url':f'https://appmagic.rocks/top-charts/apps?store=1&tag=115&aggregation=day&date={day}&country='+','.join(self.countries),
                'rows':[{'rank':rank,'package':p,'store':'Google Play','name':'工具','appmagic_url':'https://appmagic.rocks/google-play/tool/'+p} for rank,p in enumerate(packages,1)]})
        return charts

    def save(self,charts):
        path=self.root/'data/raw/appmagic_top100_joint_20261013.json'
        path.write_text(json.dumps({'source':'AppMagic','region_kind':'joint','countries':self.countries,'charts':charts}),encoding='utf-8')

    def test_latest_actual_source_date_sets_two_seven_day_windows(self):
        self.save(self.charts());result=am.build(self.catalog,self.root)
        self.assertEqual(result['previous_days'],self.days[:7]);self.assertEqual(result['current_days'],self.days[7:])
        self.assertEqual(result['latest_day'],'2026-10-11')

    def test_joint_rank_stays_one_original_rank_not_nine_national_ranks(self):
        self.save(self.charts());result=am.build(self.catalog,self.root)
        app=result['scopes']['all']['rows'][0]
        self.assertEqual((app['previous'],app['current'],app['gain']),(80,30,50))
        self.assertEqual(len(app['countries']),9)
        self.assertEqual(app['points'][0]['joint_rank'],80)
        self.assertNotIn('country_ranks',app['points'][0])
        self.assertTrue(result['scopes']['all']['complete_window'])

    def test_missing_day_does_not_become_rank101(self):
        self.save(self.charts()[1:]);result=am.build(self.catalog,self.root)
        self.assertEqual(result['scopes']['all']['rows'],[])
        self.assertFalse(result['scopes']['all']['complete_window'])

    def test_visible_date_mismatch_is_rejected(self):
        chart=self.charts()[0];chart['shown_date']='2026-09-29'
        with self.assertRaises(ValueError):am.validate(chart,self.countries)

    def test_changed_country_group_is_rejected(self):
        chart=self.charts()[0]
        with self.assertRaises(ValueError):am.validate(chart,self.countries[:-1])

    def test_grossing_or_incomplete_chart_is_rejected(self):
        chart=self.charts()[0];chart['rows'][0]['store']='iPhone App Store'
        with self.assertRaises(ValueError):am.validate(chart,self.countries)
        chart=self.charts()[0];chart['rows']=chart['rows'][:25]
        with self.assertRaises(ValueError):am.validate(chart,self.countries)

    def test_incremental_plan_only_requests_new_day_in_confirmed_source_window(self):
        self.save(self.charts())
        plan=incremental.prepare('2026-10-12','2026-10-14',self.root)
        self.assertEqual([a['requested_date'] for a in plan['browser_jobs']],['2026-10-12'])
        self.assertEqual(len(plan['cached_dates']),13)
        self.assertEqual(plan['window_days'][0],'2026-09-29')

    def test_unfinished_source_day_cannot_be_planned(self):
        with self.assertRaises(ValueError):incremental.prepare('2026-10-14','2026-10-14',self.root)

    def test_import_keeps_history_and_duplicate_cannot_overwrite_success(self):
        import daily_automation as daily
        self.save(self.charts())
        original=self.root/'data/raw/appmagic_top100_joint_20261013.json'
        before=original.read_bytes()
        fresh=self.charts()[-1]
        fresh['date']=fresh['shown_date']='2026-10-12'
        fresh['url']=fresh['url'].replace('2026-10-11','2026-10-12')
        incoming=self.root/'actual_observation.json'
        incoming.write_text(json.dumps({'source':'AppMagic','region_kind':'joint','countries':self.countries,'charts':[fresh]}),encoding='utf-8')
        with patch.object(daily,'ROOT',self.root),patch.object(daily,'refresh_metadata',return_value={'new_or_retried':0,'verified':0}) as metadata:
            first=incremental.import_observation(incoming,'2026-10-14',self.root)
            target=self.root/'data/raw/appmagic_top100_joint_20261014.json'
            saved=target.read_bytes()
            fresh['rows'][0]['name']='重复观察不覆盖已保存数据'
            incoming.write_text(json.dumps({'source':'AppMagic','region_kind':'joint','countries':self.countries,'charts':[fresh]}),encoding='utf-8')
            second=incremental.import_observation(incoming,'2026-10-14',self.root)
        self.assertEqual(first['new_dates'],['2026-10-12'])
        self.assertEqual(first['new_rows'],100)
        self.assertEqual(second['status'],'cached')
        self.assertEqual(second['new_dates'],[])
        self.assertEqual(metadata.call_count,1)
        self.assertEqual(target.read_bytes(),saved)
        self.assertEqual(original.read_bytes(),before)
        self.assertTrue((self.root/first['run']/'appmagic_observation.json').exists())
        self.assertTrue((self.root/second['run']/'appmagic_observation.json').exists())

    def test_invalid_incoming_chart_leaves_successful_history_unchanged(self):
        self.save(self.charts())
        original=self.root/'data/raw/appmagic_top100_joint_20261013.json'
        before=original.read_bytes()
        incoming=self.root/'invalid_observation.json'
        chart=self.charts()[-1];chart['rows']=chart['rows'][:25]
        incoming.write_text(json.dumps({'source':'AppMagic','region_kind':'joint','countries':self.countries,'charts':[chart]}),encoding='utf-8')
        with self.assertRaises(ValueError):incremental.import_observation(incoming,'2026-10-14',self.root)
        self.assertEqual(original.read_bytes(),before)


if __name__=='__main__':unittest.main()
