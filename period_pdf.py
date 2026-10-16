"""静态表格报告：前一天三榜Top20、历史次数和行内趋势。"""
import html
import re
from decimal import Decimal, ROUND_HALF_UP
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, PolyLine, Circle, Rect, String


def render(data, path):
    pdfmetrics.registerFont(TTFont('YaHei', 'C:/Windows/Fonts/msyh.ttc', subfontIndex=0))
    styles = {k: ParagraphStyle(k, fontName='YaHei', fontSize=s, leading=l, spaceAfter=sp, wordWrap='CJK')
              for k, s, l, sp in [('title', 17, 24, 8), ('heading', 13, 19, 8), ('body', 8, 12, 7), ('cell', 7.5, 10.5, 0)]}
    story = []
    W = 770
    P, D = data['period_analysis'], data['daily_tables']

    def safe(s):
        return html.escape(re.sub(r'[\u0600-\u06ff]+', '', str(s)).replace('–','-').replace('—','-').replace('‑','-')).strip(' |')

    def para(text, kind='body'):
        story.append(Paragraph(safe(text), styles[kind]))

    def page(title):
        if story:
            story.append(PageBreak())
        para(title, 'heading')

    def fmt(v, digits=0):
        return '数据不足' if v is None else format(Decimal(str(v)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), f',.{digits}f')

    def app(a):
        return safe(a['name']) + '<br/><font color="#5d7180">' + safe(a['subclass'] + ' · ' + a['brief']) + '</font>'

    def table(headers, rows, widths):
        def cell(v):
            return v if isinstance(v, Drawing) else Paragraph(str(v), styles['cell'])
        t = Table([[cell(safe(v)) for v in headers]] + [[cell(v) for v in row] for row in rows],
                  colWidths=[W*x for x in widths], repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#eaf1f7')),
            ('LINEBELOW', (0, 0), (-1, -1), .35, HexColor('#d4dde5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.extend([t, Spacer(1, 8)])

    def spark(points, field, digits, color, rank_scale=False):
        width, height, left, bottom = 120, 30, 5, 3
        result = Drawing(width, height)
        ink, muted = HexColor(color), HexColor('#5d7180')
        vals = [p[field] for p in points if p.get(field) is not None]
        if not vals:
            result.add(String(50, 18, '数据不足', fontName='YaHei', fontSize=6, fillColor=muted))
            return result
        maximum = max(.000001, max(vals)) * 1.08
        rank_max = max(20, max(vals))
        x = lambda i: left+i*(width-left-2)/max(1, len(points)-1)
        y = lambda v: height-4-(v-1)/(rank_max-1)*(height-bottom-4) if rank_scale else bottom+v/maximum*(height-bottom-4)
        segment = []
        for i, p in enumerate(points):
            v = p.get(field)
            if v is None:
                if len(segment) >= 4:
                    result.add(PolyLine(segment, strokeColor=ink, strokeWidth=.9))
                segment = []
            else:
                segment.extend([x(i), y(v)])
                result.add(Circle(x(i), y(v), .9, fillColor=ink, strokeColor=ink))
        if len(segment) >= 4:
            result.add(PolyLine(segment, strokeColor=ink, strokeWidth=.9))
        return result

    specs = [('downloads', '日下载', 0, '#1769aa'),
             ('buying_cost_usd', '日买量成本', 0, '#238b45'),
             ('unit_price_usd', '日单价', 4, '#a84b9b')]
    for n in ['14', '7']:
        window = D['history_windows'][n]
        for metric, label, digits, color in specs:
            page(f'DSP · {D["business_date"]} {label} Top20 · 历史近{n}天')
            para('前一天当日数据，非日均、非累计。日下载=resp；日买量成本=原始金额÷1000美元；日单价=当日金额÷当日下载。三个指标分别排序；成本榜和单价榜各日先筛日下载≥300。金额四舍五入至整数，单价4位小数，计算仍用原值。')
            para(f'历史{window["days"][0]}至{window["days"][-1]}，已观测榜单{len(window["available_days"])}/{n}天；次数按逐日进入本榜Top20统计，含前一天。小图为本榜指标每日实际值，纵轴从零起按本APP自适应，缺APP行断线。')
            rows = D['tables'][metric]['rows']
            if not rows:
                para('前一天榜单缺数，不用更早日期替代。')
                continue
            for start in range(0, len(rows), 10):
                if start:
                    page(f'DSP · {D["business_date"]} {label} Top20 · 历史近{n}天（续）')
                    para(f'历史{window["days"][0]}至{window["days"][-1]}；行内小图为{label}每日实际值。')
                table(['当日名次', 'APP与用途', '日下载（次）', '日买量成本（美元）', '日单价（美元/下载）', f'近{n}天本榜Top20次数', '数据趋势'],
                      [[a['rank'], app(a), fmt(a['downloads']), fmt(a['buying_cost_usd'], 0), fmt(a['unit_price_usd'], 4),
                        str(a['top20_counts'][n])+'次', spark([p for p in a['points'] if p['date'] in window['days']], 'value', digits, color)]
                       for a in rows[start:start+10]], [.055, .30, .09, .115, .115, .15, .175])
    g=data['gp20_analysis'];ga=g['scopes']['all']
    page('GP排名表 · 全部国家 Top20')
    para(f'{g["days"][0]}至{g["days"][-1]}（20天）；固定11国已取得{len(ga["available_days"])}/20个完整国家日组，SY/CD缺榜。'+
         ('11国未全齐日期'+ '、'.join(ga['missing_days'])+'。20天数据不足，次数仅为已观察下限。' if ga['missing_days'] else '20天数据完整。')+
         f'已取得{ga["observed_country_days"]}/220份国榜。逐国已观察日均热度按固定11国等权合成；次数按进入任一国家原Top20的日期数统计，同日跨国只计1次。缺日时为临时排名及次数下限。小图取APP当天有实际名次记录国家的平均原榜名次，含已取得的20名后记录；名次越小越靠上，仅无实际名次的日期断线，各日参与国家可变。排名积分不是下载量；各国表通过交互报告国家筛选查看。')
    if not ga['apps']:para('该范围缺榜，期间热度和趋势不可用，不能视为零下载或未上榜。')
    for start in range(0,min(20,len(ga['apps'])),10):
        if start:
            page('GP排名表 · 全部国家 Top20（续）')
            para('小图为当天有实际名次记录国家的平均原榜名次，含20名后记录；名次越小越靠上，无实际名次的日期断线。')
        table(['20天期间名次','APP与用途','平均榜单热度','20天原榜Top20出现次数','覆盖国家','出现平均原榜名次','数据趋势'],
              [[a['period_rank'],app(a),fmt(a['mean_heat'],2),str(a['top20_days'])+'次',
                a['country_count'],fmt(a['mean_appearing_rank'],2),spark(a['points'],'trend_rank',2,'#1769aa',True)]
               for a in ga['apps'][start:start+10]], [.055,.30,.09,.15,.07,.16,.175])
    ps=data['palmstore_view']['rows']
    for start in range(0,len(ps),10):
        page('PalmStore · 热门次数'+('（续）' if start else ''))
        para('2026-10-10快照：13国指定列表前20的出现国家次数合计，包含印度736、俄罗斯675推荐列表；每国最多计1次，按X/13降序。仅代表列表覆盖，7/14天历史数据不足。')
        for a in ps[start:start+10]:
            story.append(Paragraph(app(a),styles['cell']))
            bar=Drawing(W,15)
            bar.add(Rect(0,3,W-60,8,fillColor=HexColor('#edf3f8'),strokeColor=None))
            bar.add(Rect(0,3,(W-60)*a['hot_count']/13,8,fillColor=HexColor('#1769aa'),strokeColor=None))
            bar.add(String(W-8,3,f'{a["hot_count"]}/13',textAnchor='end',fontName='YaHei',fontSize=8,fillColor=HexColor('#172e40')))
            story.extend([bar,Spacer(1,8)])

    def footer(canvas, doc):
        canvas.setFont('YaHei', 7)
        canvas.drawString(36, 18, '工具类APP热度趋势日报'+data['report_date'].replace('-','')+' · DSP业务日'+D['business_date'])
        canvas.drawRightString(806, 18, str(doc.page))
    SimpleDocTemplate(str(path), pagesize=(842, 595), leftMargin=36, rightMargin=36,
                      topMargin=28, bottomMargin=32, title='工具类APP热度趋势日报'+data['report_date'].replace('-','')).build(story, onFirstPage=footer, onLaterPages=footer)
