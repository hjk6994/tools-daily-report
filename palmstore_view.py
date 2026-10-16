"""合并13国指定列表覆盖次数，生成当前PalmStore进度条视图。"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build(data, export=True):
    rows = []
    for app in data['ps_frequency']:
        countries = sorted(app['positions'])
        count = app['top_charts_count'] + app['editor_count']
        if count != len(countries) or not 0 <= count <= 13:
            raise ValueError('PalmStore热门次数与实际出现国家不匹配：'+app['package'])
        rows.append({k: app[k] for k in ['package', 'name', 'subclass', 'brief']} | {
            'hot_count': count, 'denominator': 13, 'countries': countries,
            'positions': app['positions'], 'ratio': count / 13,
        })
    rows.sort(key=lambda a: (-a['hot_count'], a['package']))
    if export:
        with (ROOT/'ps_hot_frequency_13countries.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['APP', '包名', '用途', '简要说明', '热门次数', '国家总数', '出现国家'])
            for a in rows:
                writer.writerow([a['name'], a['package'], a['subclass'], a['brief'], a['hot_count'], 13, '、'.join(a['countries'])])
    return {'observation_date': data['ps_observation_date'], 'rows': rows,
            'rule': '13国指定列表前20的出现国家次数合计，印度736与俄罗斯675推荐列表纳入；每个APP每国最多计1次，按X/13降序。仅当前快照，不代表下载次数。'}
