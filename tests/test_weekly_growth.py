"""周增长数值、固定样本、缺数和PS真实历史隔离检查；不联网。"""
import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import weekly_growth as w
import gp20_analysis as gp


class WeeklyGrowth(unittest.TestCase):
    def setUp(self):
        self.days=w.days_for('2026-10-13')
        self.catalog={'app.test.tool':{'package':'app.test.tool','name':'测试工具','subclass':'PDF工具','brief':'读取文档。'}}

    def dsp(self,country='PK',previous=1,current=2):
        return [{'date':d,'package':'app.test.tool','country':country,'revenue_usd':previous if i<7 else current,'downloads':500} for i,d in enumerate(self.days)]

    def ranks(self,country='PK',previous=80,current=30,identity='工具榜'):
        return [{'country':country,'date':d,'identity':identity,'rows':[{'package':'app.test.tool','rank':previous if i<7 else current}]} for i,d in enumerate(self.days)]

    def test_two_complete_seven_day_windows(self):
        self.assertEqual(self.days[0],'2026-09-29');self.assertEqual(self.days[6],'2026-10-05')
        self.assertEqual(self.days[7],'2026-10-06');self.assertEqual(self.days[-1],'2026-10-12')

    def test_growth_uses_cost_even_when_downloads_do_not_change(self):
        a=w.dsp_growth(self.dsp(),self.catalog,self.days,set(self.days))['rows'][0]
        self.assertEqual((a['previous'],a['current'],a['gain'],a['growth_pct']),(7,14,7,100))
        self.assertEqual(len(a['points']),14)

    def test_missing_country_is_not_added_as_zero(self):
        rows=self.dsp()+self.dsp('IN',100,1)[:-1]
        a=w.dsp_growth(rows,self.catalog,self.days,set(self.days))['rows'][0]
        self.assertEqual(a['countries'],['PK']);self.assertEqual(a['growth_pct'],100)

    def test_missing_day_and_zero_baseline_have_no_percentage(self):
        self.assertEqual(w.dsp_growth(self.dsp()[:-1],self.catalog,self.days,set(self.days))['rows'],[])
        self.assertEqual(w.dsp_growth(self.dsp(previous=0),self.catalog,self.days,set(self.days))['rows'],[])

    def test_decimal_money_is_summed_before_rounding(self):
        a=w.dsp_growth(self.dsp(previous=.1,current=.2),self.catalog,self.days,set(self.days))['rows'][0]
        self.assertEqual(a['previous'],.7);self.assertEqual(a['current'],1.4);self.assertEqual(a['growth_pct'],100)

    def test_baseline_percentile_includes_apps_without_growth(self):
        catalog,rows={},[]
        for i in range(1,11):
            package=f'app.test.tool{i}';catalog[package]=dict(self.catalog['app.test.tool'],package=package)
            for row in self.dsp(previous=i,current=i*2 if i in [1,9] else i):
                rows.append(dict(row,package=package))
        result=w.dsp_growth(rows,catalog,self.days,set(self.days))
        self.assertEqual(result['baseline_pool']['size'],10)
        self.assertEqual(result['baseline_pool']['cutoffs']['20']['minimum_previous_usd'],63)
        self.assertEqual(result['baseline_pool']['cutoffs']['10']['minimum_previous_usd'],70)
        minimum=result['baseline_pool']['cutoffs']['20']['minimum_previous_usd']
        eligible=[a['package'] for a in result['rows'] if a['previous']>=minimum]
        self.assertEqual(eligible,['app.test.tool9'])

    def test_baseline_boundary_ties_are_kept(self):
        catalog,rows={},[]
        for i,value in enumerate([10,9,9,8,7,6,5,4,3,2]):
            package=f'app.test.tool{i}';catalog[package]=dict(self.catalog['app.test.tool'],package=package)
            rows.extend(dict(row,package=package) for row in self.dsp(previous=value,current=value*2))
        pool=w.dsp_growth(rows,catalog,self.days,set(self.days))['baseline_pool']
        self.assertEqual(pool['cutoffs']['20']['rank_limit'],2)
        self.assertEqual(pool['cutoffs']['20']['qualified_count'],3)

    def test_rank_outside_top20_can_show_growth(self):
        a=w.rank_growth(self.ranks(),self.catalog,self.days,['PK'],'GP',10)['scopes']['all']['rows'][0]
        self.assertEqual((a['previous'],a['current'],a['gain']),(80,30,50))
        self.assertEqual(a['points'][0]['country_ranks'],{'PK':80})

    def test_rank_cohort_requires_same_complete_countries(self):
        charts=self.ranks()+self.ranks('IN',previous=10,current=90)[:-1]
        a=w.rank_growth(charts,self.catalog,self.days,['PK','IN'],'GP',10)['scopes']['all']['rows'][0]
        self.assertEqual(a['countries'],['PK']);self.assertEqual(a['gain'],50)

    def test_no_previous_rank_does_not_become_rank101(self):
        charts=self.ranks()[7:]
        result=w.rank_growth(charts,self.catalog,self.days,['PK'],'GP',10)
        self.assertEqual(result['scopes']['all']['rows'],[])

    def test_changing_chart_identity_is_not_comparable(self):
        charts=self.ranks();charts[-1]['identity']='另一榜单'
        self.assertEqual(w.rank_growth(charts,self.catalog,self.days,['PK'],'PS',5)['scopes']['all']['rows'],[])

    def test_palm_reader_keeps_only_real_dated_valid_snapshots(self):
        root=ROOT/'tmp/weekly_tests'/uuid.uuid4().hex;raw=root/'data/raw';raw.mkdir(parents=True)
        def snapshot(country,day,name):
            obj={'code':0,'data':{'rankId':'736' if country=='IN' else '1750','rankName':name,'countryCode':country,
                                 'data':[{'packageName':f'app.test.tool{i}','name':'工具'} for i in range(1,26)]}}
            (raw/f'ps_api_{country}_{day}.json').write_text(json.dumps(obj),encoding='utf-8')
        snapshot('PK','2026-10-12','Top Charts');snapshot('IN','2026-10-12',"Editor's Choice")
        (raw/'ps_api_PK_probe.json').write_text('{}',encoding='utf-8')
        charts,manifest=w.palm_history(root)
        self.assertEqual(len(manifest),2);self.assertEqual(len(charts),1);self.assertEqual(len(charts[0]['rows']),25)
        (raw/'ps_api_PK_2026-10-12.audit.json').write_text(json.dumps({'collected_at':'2026-10-13T00:00:00+08:00'}),encoding='utf-8')
        self.assertEqual(w.palm_history(root)[0],[])

    def test_shallow_gp_cannot_replace_deeper_history(self):
        root=ROOT/'tmp/weekly_tests'/uuid.uuid4().hex;root.mkdir(parents=True)
        url='https://app.sensortower.com/top-charts?category=tools&country=PK&os=android&date=2026-10-12'
        def record(depth,time):return {'country':'PK','date':'2026-10-12','url':url,'collected_at':time,
                                       'rows':[{'rank':i,'package':f'app.test.tool{i}','name':'工具','publisher_url':url} for i in range(1,depth+1)]}
        paths=[]
        for i,a in enumerate([record(100,'2026-10-13T01:00:00Z'),record(25,'2026-10-13T02:00:00Z')]):
            path=root/f'{i}.json';path.write_text(json.dumps({'charts':[a]}),encoding='utf-8');paths.append(path)
        with patch.object(gp,'snapshot_files',return_value=paths):self.assertEqual(len(gp.source_charts()['PK','2026-10-12']['rows']),100)


if __name__=='__main__':unittest.main()
