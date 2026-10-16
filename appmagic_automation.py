"""为已授权浏览器采集规划联合Top100增量，保留每次真实观察及历史。"""
import argparse
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from appmagic_growth import validate

ROOT = Path(__file__).resolve().parent
COUNTRIES = ['PK', 'IN', 'NG', 'ID', 'BD', 'PH', 'IQ', 'RU', 'SA']


def saved_charts(root=ROOT):
    """固定九国的成功历史只读复用；不同国家组合不混入。"""
    result = {}
    for path in sorted((Path(root)/'data/raw').glob('appmagic_top100_joint_*.json')):
        obj = json.loads(path.read_text(encoding='utf-8'))
        if obj.get('source') != 'AppMagic' or obj.get('region_kind') != 'joint':
            continue
        if set(obj.get('countries', [])) != set(COUNTRIES):
            continue
        for chart in obj['charts']:
            validate(chart, COUNTRIES)
            result.setdefault(chart['date'], chart)
    return result


def prepare(latest_date, report_date, root=ROOT):
    """截止日期必须先在页面确认；不能推断来源发布延迟。"""
    end = datetime.fromisoformat(latest_date)
    report = datetime.fromisoformat(report_date)
    if end >= report:
        raise ValueError('仅采集报告日期之前已结束的真实日榜')
    days = [(end-timedelta(days=i)).date().isoformat() for i in reversed(range(14))]
    cached = saved_charts(root)
    jobs = []
    for day in days:
        if day in cached:
            continue
        url = ('https://appmagic.rocks/top-charts/apps?store=1&tag=115&aggregation=day'
               '&date='+day+'&country='+','.join(COUNTRIES))
        jobs.append({'requested_date': day, 'countries': COUNTRIES, 'entry_url': url,
                     'minimum_depth': 100})
    return {'source': 'AppMagic', 'report_date': report_date, 'latest_available_date': latest_date,
            'countries': COUNTRIES, 'window_days': days, 'cached_dates': [d for d in days if d in cached],
            'browser_jobs': jobs, 'rule': '先确认页面最新可选的已结束日期，再只采集尚未成功保存的日榜；联合原榜不复制为各国榜。'}


def import_observation(path, report_date, root=ROOT):
    """完整身份和原榜校验通过后归档；已成功保存的日期不重复覆盖。"""
    from daily_automation import new_run, save, refresh_metadata
    root = Path(root)
    incoming = json.loads(Path(path).read_text(encoding='utf-8'))
    if (incoming.get('source') != 'AppMagic' or incoming.get('region_kind') != 'joint'
            or set(incoming.get('countries', [])) != set(COUNTRIES)
            or not incoming.get('charts')):
        raise ValueError('需要固定九国联合Top100的真实页面观察')
    rows = [validate(c, COUNTRIES) for c in incoming['charts']]
    if len({c['date'] for c in rows}) != len(rows):
        raise ValueError('同次观察的日榜日期重复')
    if any(datetime.fromisoformat(c['date']) >= datetime.fromisoformat(report_date) for c in rows):
        raise ValueError('不能导入未结束或未来日榜')
    cached = saved_charts(root)
    fresh = [c for c in rows if c['date'] not in cached]
    run = new_run(report_date)
    save(run/'appmagic_observation.json', incoming)
    target = root/'data/raw'/('appmagic_top100_joint_'+report_date.replace('-', '')+'.json')
    if fresh:
        previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {
            'source': 'AppMagic', 'platform': 'Google Play', 'category': '实用工具',
            'region_kind': 'joint', 'countries': COUNTRIES, 'charts': []}
        if previous.get('source') != 'AppMagic' or previous.get('region_kind') != 'joint' or set(previous.get('countries', [])) != set(COUNTRIES):
            raise ValueError('已有文件的联合国家或来源不一致，不能覆盖')
        if target.exists():
            shutil.copy2(target, run/'before_appmagic_observation.json')
        previous['charts'].extend(fresh)
        previous['charts'].sort(key=lambda c: c['date'])
        save(target, previous)
        metadata = refresh_metadata([a['package'] for c in fresh for a in c['rows']])
    else:
        metadata = {'new_or_retried': 0, 'verified': 0}
    result = {'source': 'AppMagic', 'report_date': report_date,
              'status': 'imported' if fresh else 'cached',
              'new_dates': [c['date'] for c in fresh], 'new_rows': sum(len(c['rows']) for c in fresh),
              'cached_dates_skipped': [c['date'] for c in rows if c['date'] in cached],
              'run': str(run.relative_to(root)), 'metadata': metadata}
    if fresh:
        result['snapshot'] = str(target.relative_to(root))
    save(run/'run.json', result)
    save(root/'data/automation'/('appmagic_'+report_date+'.json'), result)
    return result


def main():
    parser = argparse.ArgumentParser(description='AppMagic联合Top100真实浏览器观察的增量规划与导入')
    parser.add_argument('action', choices=['prepare', 'import'])
    parser.add_argument('--date', required=True, help='北京时间的日报日期')
    parser.add_argument('--latest-date', help='浏览器页面已确认的最新可选、已结束日榜日期')
    parser.add_argument('--input', help='本次真实页面观察JSON')
    args = parser.parse_args()
    if args.action == 'prepare' and not args.latest_date:
        parser.error('prepare需要--latest-date')
    if args.action == 'import' and not args.input:
        parser.error('import需要--input')
    result = prepare(args.latest_date, args.date) if args.action == 'prepare' else import_observation(args.input, args.date)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
