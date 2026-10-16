"""复算前一天的三个独立 Top20，以及近7/14天的逐日上榜次数。"""
import csv
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
METRICS = {
    'downloads': ('日下载', 'downloads'),
    'buying_cost_usd': ('日买量成本', 'revenue_usd'),
    'unit_price_usd': ('日单价', 'unit_price_usd'),
}


def rounded(value, digits):
    """只格式化展示值，排序和比例仍使用未舍入的真实数值。"""
    if value is None:
        return None
    return format(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), f'.{digits}f')


def build(data, export=True):
    period = data['period_analysis']
    day = (datetime.fromisoformat(data['report_date']) - timedelta(days=1)).date().isoformat()
    days = [(datetime.fromisoformat(day) - timedelta(days=i)).date().isoformat()
            for i in reversed(range(14))]
    apps = period['windows']['14']['dsp']['apps']
    points = {a['package']: {p['date']: p for p in a['points']} for a in apps}
    available = sorted({r['date'] for r in period['dsp_rows'] if r['date'] in days})
    rankings = {}
    tables = {}
    for metric, (label, field) in METRICS.items():
        daily = {}
        for date in days:
            candidates = [a for a in apps if points[a['package']].get(date, {}).get(field) is not None
                          and (metric == 'downloads' or points[a['package']][date]['downloads'] >= 300)]
            candidates.sort(key=lambda a: (-points[a['package']][date][field], a['package']))
            daily[date] = [a['package'] for a in candidates[:20]] if date in available else None
        rankings[metric] = daily
        rows = []
        lookup = {a['package']: a for a in apps}
        for rank, package in enumerate(daily.get(day) or [], 1):
            a = lookup[package]
            current = points[package][day]
            history = [{
                'date': date,
                'value': points[package].get(date, {}).get(field),
                'rank': (daily[date].index(package) + 1) if daily[date] and package in daily[date] else None,
                'status': ('当日榜单缺数' if daily[date] is None else
                           'APP缺行，数值未知' if points[package].get(date, {}).get('downloads') is None else
                           '零下载，不计算单价' if metric == 'unit_price_usd' and points[package][date][field] is None else
                           '有实际记录；日下载低于300，不参加本榜' if metric != 'downloads' and points[package][date]['downloads'] < 300 else
                           '有实际记录'),
            } for date in days]
            counts = {str(n): sum(package in (daily[date] or []) for date in days[-n:]) for n in [7, 14]}
            rows.append({k: a[k] for k in ['package', 'name', 'subclass', 'brief']} | {
                'rank': rank, 'business_date': day,
                'downloads': current['downloads'],
                'buying_cost_usd': current['revenue_usd'],
                'unit_price_usd': current['unit_price_usd'],
                'display': {'buying_cost_usd': rounded(current['revenue_usd'], 0),
                            'unit_price_usd': rounded(current['unit_price_usd'], 4)},
                'top20_counts': counts, 'points': history,
            })
        tables[metric] = {'label': label, 'minimum_daily_downloads': None if metric == 'downloads' else 300, 'rows': rows}
        if export:
            path = ROOT / f'dsp_day_{metric}_top20.csv'
            with path.open('w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    '业务日期', '本榜指标', '当日名次', '包名', 'APP', '用途', '简要说明',
                    '日下载（次）', '日买量成本（美元）', '日单价（美元/下载）',
                    '近7天本榜Top20次数', '近14天本榜Top20次数'])
                writer.writeheader()
                for a in rows:
                    writer.writerow(dict(zip(writer.fieldnames, [
                        day, label, a['rank'], a['package'], a['name'], a['subclass'], a['brief'],
                        a['downloads'], a['display']['buying_cost_usd'], a['display']['unit_price_usd'],
                        a['top20_counts']['7'], a['top20_counts']['14']])))
    return {
        'business_date': day, 'days': days, 'available_days': available,
        'history_windows': {str(n): {'days': days[-n:], 'available_days': [d for d in days[-n:] if d in available],
                                  'missing_days': [d for d in days[-n:] if d not in available]} for n in [7, 14]},
        'tables': tables, 'rankings_by_day': rankings,
        'cost_mapping': '日买量成本=原始金额total_revenue÷1000，单位美元；按用户命名，不新增成本来源。',
        'count_rule': '截至前一天，逐日按本榜对应指标独立取已核验工具Top20；成本榜和单价榜各日先筛日下载≥300；仅计入该APP进入本榜Top20的日期次数，含前一天。',
        'price_rule': '日单价=同一业务日全部实际观测国家的美元金额合计÷下载合计；零下载不可用。',
        'status': '前一天有实际记录' if day in available else '前一天缺数，不用更早日期替代',
    }
