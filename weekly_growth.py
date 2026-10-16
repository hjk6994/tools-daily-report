"""真实周增长复算；只读取已保存记录，缺行、缺日和榜外名次不补零。"""
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import gp20_analysis as gp20
from daily_tables import rounded

ROOT = Path(__file__).resolve().parent
PS_COUNTRIES = [c for c in gp20.COUNTRIES if c not in ['IN', 'RU']]


def days_for(report_date):
    end = datetime.fromisoformat(report_date) - timedelta(days=1)
    return [(end-timedelta(days=i)).date().isoformat() for i in reversed(range(14))]


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def catalog_for(data, root=ROOT):
    catalog = {}
    path = Path(root)/'comparison_metadata.csv'
    if path.exists():
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for a in csv.DictReader(stream):
                if a.get('metadata_status') == 'verified' and a.get('is_tool', '').lower() in ['true', '1']:
                    catalog[a['package']] = {k: a.get(v, '') for k, v in [('package', 'package'), ('name', 'name'), ('subclass', 'business_subclass'), ('brief', 'brief')]}
    for a in data.get('gp20_analysis', {}).get('catalog', []):
        if a.get('tool_function'):
            catalog[a['package']] = {k: a[k] for k in ['package', 'name', 'subclass', 'brief']}
    for a in data.get('ps_frequency', []):
        catalog[a['package']] = {k: a[k] for k in ['package', 'name', 'subclass', 'brief']}
    for a in data.get('period_analysis', {}).get('windows', {}).get('14', {}).get('dsp', {}).get('apps', []):
        catalog[a['package']] = {k: a[k] for k in ['package', 'name', 'subclass', 'brief']}
    return catalog


def dsp_growth(rows, catalog, days, available_days):
    values = defaultdict(dict)
    for row in rows:
        if row['date'] not in days or row['package'] not in catalog:
            continue
        if not finite(row.get('revenue_usd')) or row['revenue_usd'] < 0:
            continue
        country = str(row.get('country') or '')
        if not country:
            continue
        key = row['package'], country
        day = row['date']
        values[key][day] = values[key].get(day, Decimal(0)) + Decimal(str(row['revenue_usd']))
    pairs = defaultdict(list)
    for (package, country), record in values.items():
        if all(day in record for day in days):
            pairs[package].append((country, record))
    apps, baseline = [], []
    excluded = {'missing_app_or_country_day': 0, 'zero_previous_cost': 0, 'non_increase': 0}
    for package in {p for p, _ in values}:
        nations = pairs.get(package, [])
        if not nations:
            excluded['missing_app_or_country_day'] += 1
            continue
        totals = [sum((record[d] for _, record in nations), Decimal(0)) for d in days]
        previous, current = sum(totals[:7]), sum(totals[7:])
        if previous <= 0:
            excluded['zero_previous_cost'] += 1
            continue
        baseline.append({'package': package, 'previous': float(previous)})
        gain = current-previous
        if gain <= 0:
            excluded['non_increase'] += 1
            continue
        pct = float(gain/previous*100)
        apps.append(catalog[package] | {
            'previous': float(previous), 'current': float(current), 'gain': float(gain), 'growth_pct': pct,
            'countries': sorted(c for c, _ in nations), 'previous_days': 7, 'current_days': 7,
            'display': {'previous': rounded(float(previous), 0), 'current': rounded(float(current), 0), 'gain': rounded(float(gain), 0)},
            'points': [{'date': d, 'value': float(v)} for d, v in zip(days, totals)],
        })
    # 基准包含未增长APP；先以完整可比样本的上周金额确定门槛，再筛增幅。
    baseline.sort(key=lambda a: (-a['previous'], a['package']))
    baseline_ranks = {a['package']: i+1 for i, a in enumerate(baseline)}
    cutoffs = {}
    for pct in [10, 20]:
        count = math.ceil(len(baseline)*pct/100)
        minimum = baseline[count-1]['previous'] if count else None
        cutoffs[str(pct)] = {'rank_limit': count, 'minimum_previous_usd': minimum,
                            'qualified_count': sum(a['previous'] >= minimum for a in baseline) if count else 0}
    for a in apps:
        a['baseline_rank'] = baseline_ranks[a['package']]
        a['baseline_pool_size'] = len(baseline)
    apps.sort(key=lambda a: (-a['growth_pct'], -a['gain'], a['package']))
    return {'rows': apps, 'default_threshold': 20, 'default_baseline_top_pct': 20,
            'baseline_pool': {'size': len(baseline), 'cutoffs': cutoffs,
                              'rule': '两周各7天都有固定国别实际记录且上周成本大于0的已核验工具APP；包含未增长APP。按上周未舍入成本降序，前N%向上取整，边界同金额全部保留。'},
            'available_days': [d for d in days if d in available_days],
            'missing_days': [d for d in days if d not in available_days], 'excluded': excluded,
            'method': '同一APP仅合计两周每天均有真实记录的固定国家；累计买量成本以原金额÷1000美元计算。缺行不视为零成本，零基数不计算百分比。'}


def rank_growth(charts, catalog, days, countries, source, threshold):
    """每个APP固定两周都有完整名次的国家；榜单身份变更时不比较。"""
    index = {(a['country'], a['date']): a for a in charts
             if a['country'] in countries and a['date'] in days and not a.get('no_chart')}
    ranks = {}
    for key, chart in index.items():
        ranks[key] = {a['package']: a['rank'] for a in chart['rows']
                      if a['package'] in catalog and finite(a.get('rank')) and a['rank'] >= 1}
    packages = {p for r in ranks.values() for p in r}
    scopes = {}
    for scope in ['all']+list(countries):
        selected = list(countries) if scope == 'all' else [scope]
        apps = []
        for package in packages:
            matched = []
            for country in selected:
                if not all((country, d) in index and package in ranks[country, d] for d in days):
                    continue
                identities = {index[country, d].get('identity', source) for d in days}
                if len(identities) != 1:
                    continue
                matched.append(country)
            if not matched:
                continue
            points = [{'date': d, 'value': sum(ranks[c, d][package] for c in matched)/len(matched),
                       'country_ranks': {c: ranks[c, d][package] for c in matched}} for d in days]
            previous = sum(p['value'] for p in points[:7])/7
            current = sum(p['value'] for p in points[7:])/7
            if previous-current <= 1e-9:
                continue
            apps.append(catalog[package] | {'previous': previous, 'current': current, 'gain': previous-current,
                                           'countries': matched, 'previous_days': 7, 'current_days': 7, 'points': points})
        apps.sort(key=lambda a: (-a['gain'], a['current'], a['package']))
        coverage = [{'country': c, 'previous_days': sum((c, d) in index for d in days[:7]),
                     'current_days': sum((c, d) in index for d in days[7:]),
                     'missing_days': [d for d in days if (c, d) not in index]} for c in selected]
        scopes[scope] = {'rows': apps, 'countries': selected, 'coverage': coverage,
                         'complete_country_count': sum(not a['missing_days'] for a in coverage),
                         'chart_count': sum((c, d) in index for c in selected for d in days),
                         'expected_chart_count': len(selected)*14}
    return {'source': source, 'default_threshold': threshold, 'scopes': scopes,
            'recorded_depths': sorted({len(a['rows']) for a in index.values()}),
            'source_files': sorted({a.get('snapshot', '') for a in index.values()}- {''}),
            'method': '只比较同一包名、同一国家、同一原榜；每个APP选择两周各7天都有名次的同一组国家等权平均。提升位数=上周均值−本周均值；已有20名后的实际名次也参与，未知名次不填101。'}


def palm_history(root=ROOT):
    """只认真实日期快照；推荐位置保留历史，但不参与热门榜升位。"""
    raw = Path(root)/'data/raw'
    charts, manifest = [], []
    pattern = re.compile(r'ps_api_([A-Z]{2})_(\d{4}-\d{2}-\d{2})\.json$')
    for path in sorted(raw.glob('ps_api_*.json')):
        match = pattern.fullmatch(path.name)
        if not match:
            continue
        country, day = match.groups()
        if country not in gp20.COUNTRIES:
            continue
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
            data = obj.get('data')
            if obj.get('code') not in [0, 200, '0', '200'] or not isinstance(data, dict):
                continue
            rows = data.get('data')
            if not isinstance(rows, list) or len(rows) < 20 or data.get('countryCode') not in [None, '', country]:
                continue
            name, chart_id = data.get('rankName'), str(data.get('rankId') or '')
            if name not in ['Top Charts', "Editor's Choice"] or not chart_id:
                continue
            audit_path = path.with_suffix('.audit.json')
            audit = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else {}
            if audit.get('collected_at') and audit['collected_at'][:10] != day:
                continue
            normalized = [{'package': r['packageName'], 'name': r.get('name', ''), 'rank': rank}
                          for rank, r in enumerate(rows, 1) if r.get('packageName')]
            if len({r['package'] for r in normalized}) != len(normalized):
                continue
            chart = {'country': country, 'date': day, 'chart_id': chart_id, 'chart_name': name,
                     'identity': f'PalmStore|{chart_id}|{name}', 'rows': normalized,
                     'snapshot': str(path.relative_to(root)).replace('\\', '/'),
                     'response_country_confirmed': bool(data.get('countryCode'))}
            manifest.append({k: chart[k] for k in ['country', 'date', 'chart_id', 'chart_name', 'snapshot', 'response_country_confirmed']})
            if name == 'Top Charts' and country not in ['IN', 'RU']:
                charts.append(chart)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return charts, manifest


def build(data, export=True, root=ROOT):
    root = Path(root)
    days = days_for(data['report_date'])
    catalog = catalog_for(data, root)
    period = data['period_analysis']
    available = {r['date'] for r in period['dsp_rows']}
    dsp = dsp_growth(period['dsp_rows'], catalog, days, available)
    gp_charts = list(gp20.source_charts().values())
    for a in gp_charts:
        a['identity'] = 'Sensor Tower|Google Play|tools|free'
    gp = rank_growth(gp_charts, catalog, days, gp20.COUNTRIES, 'Sensor Tower', 10)
    gp['source_files'] = [str(p.relative_to(gp20.ROOT)).replace('\\', '/') for p in gp20.snapshot_files()]
    from appmagic_growth import build as appmagic
    gp_appmagic = appmagic(catalog, root)
    ps_charts, manifest = palm_history(root)
    ps = rank_growth(ps_charts, catalog, days, PS_COUNTRIES, 'PalmStore', 5)
    ps['snapshot_dates'] = sorted({a['date'] for a in manifest})
    ps['status'] = '可进行完整周对比' if ps['scopes']['all']['complete_country_count'] else '历史未积累完整，周增长留空'
    result = {'report_date': data['report_date'], 'days': days, 'previous_days': days[:7], 'current_days': days[7:],
              'timezone': 'DSP为UTC业务日期，GP为原榜日期，PS为保存的观察日期；DSP和Sensor Tower截至报告前一天，AppMagic以最新真实日榜日期为截止',
              'dsp': dsp, 'gp': gp, 'gp_appmagic': gp_appmagic, 'ps': ps, 'simulated': False,
              'rule': '本周为最近7个完整业务日，上周为此前7天；三个来源独立筛选，不生成结论。'}
    if export:
        target = root/'data/weekly_growth'
        target.mkdir(parents=True, exist_ok=True)
        (target/f"{data['report_date']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        (target/'palmstore_history_index.json').write_text(json.dumps({'snapshots': manifest, 'rule': '索引只引用真实已保存快照；同一国家日期仅保存一次，不回填历史'}, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
