"""按原始日数据独立核验当日三榜、逐日Top20次数和缺数边界。"""
import json
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'.deps'))
import pandas as pd
from daily_tables import build, METRICS, rounded


class DailyTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT/'data/comparison_report_data.json').read_text(encoding='utf-8'))
        cls.result = build(cls.data, export=False)
        raw = pd.read_csv(ROOT/'dsp_daily.csv')
        metadata = pd.read_csv(ROOT/'comparison_metadata.csv')
        tools = set(metadata.loc[(metadata.is_tool == True) & (metadata.metadata_status == 'verified'), 'package'])
        cls.daily = raw[raw.package.isin(tools)].groupby(['date', 'package'])[['downloads', 'raw_revenue']].sum()
        cls.daily['buying_cost_usd'] = cls.daily.raw_revenue/1000
        cls.daily['unit_price_usd'] = cls.daily.buying_cost_usd/cls.daily.downloads.replace(0, float('nan'))

    def packages(self, date, metric):
        rows = self.daily.loc[date].reset_index().dropna(subset=[metric])
        if metric != 'downloads':rows = rows[rows.downloads >= 300]
        return rows.sort_values([metric, 'package'], ascending=[False, True]).head(20).package.tolist()

    def test_minimum_downloads_applies_to_cost_price_each_day_only(self):
        for metric in ['buying_cost_usd', 'unit_price_usd']:
            self.assertTrue(all(a['downloads'] >= 300 for a in self.result['tables'][metric]['rows']))
            for day, packages in self.result['rankings_by_day'][metric].items():
                self.assertTrue(all(self.daily.loc[(day,p), 'downloads'] >= 300 for p in packages))
        # 当前源数据中，原单价榜首194次下载必须被排除。
        self.assertFalse(any(a['downloads'] < 300 for a in self.result['tables']['unit_price_usd']['rows']))

    def test_rounding_is_half_up_and_display_does_not_change_raw_values(self):
        self.assertEqual(rounded(2.5,0),'3')
        self.assertEqual(rounded(0.00005,4),'0.0001')
        self.assertEqual(rounded(1.23445,4),'1.2345')
        for table in self.result['tables'].values():
            for a in table['rows']:
                self.assertEqual(a['display']['buying_cost_usd'],rounded(a['buying_cost_usd'],0))
                self.assertEqual(a['display']['unit_price_usd'],rounded(a['unit_price_usd'],4))

    def test_day_is_previous_report_day_and_three_independent_twenty(self):
        expected = (datetime.fromisoformat(self.data['report_date'])-timedelta(days=1)).date().isoformat()
        self.assertEqual(self.result['business_date'], expected)
        lists = []
        for metric, table in self.result['tables'].items():
            rows = table['rows'];self.assertEqual(len(rows), 20)
            actual = [r['package'] for r in rows]
            self.assertEqual(actual, self.packages(expected, metric))
            self.assertEqual([r['rank'] for r in rows], list(range(1, 21)))
            lists.append(tuple(actual))
        self.assertEqual(len(set(lists)), 3)

    def test_all_three_tables_daily_values_and_amount_scale(self):
        for table in self.result['tables'].values():
            for a in table['rows']:
                expected = self.daily.loc[(a['business_date'], a['package'])]
                self.assertEqual(a['downloads'], expected.downloads)
                self.assertAlmostEqual(a['buying_cost_usd'], expected.raw_revenue/1000, places=9)
                self.assertAlmostEqual(a['unit_price_usd'], expected.buying_cost_usd/expected.downloads, places=9)

    def test_top20_counts_are_metric_specific_daily_memberships(self):
        for metric, table in self.result['tables'].items():
            for a in table['rows']:
                for n in [7, 14]:
                    expected = sum(a['package'] in self.packages(d, metric) for d in self.result['days'][-n:])
                    self.assertEqual(a['top20_counts'][str(n)], expected)
        counts = [a['top20_counts']['14'] for t in self.result['tables'].values() for a in t['rows']]
        self.assertTrue(any(c < 14 for c in counts))

    def test_spark_values_are_daily_metric_and_preserve_gaps(self):
        for metric, table in self.result['tables'].items():
            for a in table['rows']:
                self.assertEqual([p['date'] for p in a['points']], self.result['days'])
                for p in a['points']:
                    if (p['date'], a['package']) not in self.daily.index:
                        self.assertIsNone(p['value']);continue
                    expected = self.daily.loc[(p['date'], a['package']), metric]
                    if pd.isna(expected):self.assertIsNone(p['value'])
                    else:self.assertAlmostEqual(p['value'], expected, places=9)

    def test_missing_previous_day_never_substitutes_older_rankings(self):
        next_report=(datetime.fromisoformat(self.data['report_date'])+timedelta(days=1)).date().isoformat()
        altered = dict(self.data, report_date=next_report)
        result = build(altered, export=False)
        self.assertEqual(result['business_date'], self.data['report_date'])
        self.assertTrue(all(not t['rows'] for t in result['tables'].values()))
        self.assertIn('不', result['status'])


if __name__ == '__main__':
    unittest.main()
