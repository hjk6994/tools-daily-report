"""生成已确认的周增长HTML；只嵌入真实复算数据，不引入预览模拟记录。"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def payload(data):
    keys = ['report_date', 'dsp_end', 'ps_observation_date', 'daily_tables', 'gp20_analysis', 'palmstore_view', 'weekly_growth']
    result = {k: data[k] for k in keys}
    gp = copy.deepcopy(data['gp20_analysis'])
    for scope in gp['scopes'].values():
        scope['apps'] = scope['apps'][:20]
    result['gp20_analysis'] = gp
    if result['weekly_growth'].get('simulated') is not False:
        raise ValueError('周增长必须来自真实数据复算，不能使用模拟记录')
    return result


def render_html(data, path):
    name = '工具类APP热度趋势日报'+data['report_date'].replace('-', '')
    template = (ROOT/'weekly_report_template.html').read_text(encoding='utf-8')
    content = template.replace('__REPORT_NAME__', name).replace('__REPORT_DATE_DISPLAY__', data['report_date'].replace('-', '.'))
    content = content.replace('__DATA__', json.dumps(payload(data), ensure_ascii=False, allow_nan=False).replace('</', r'<\/'))
    content = content.replace('__SCRIPT__', (ROOT/'weekly_report_script.js').read_text(encoding='utf-8'))
    Path(path).write_text(content, encoding='utf-8')
