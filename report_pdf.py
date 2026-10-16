"""将已核验数据排成可阅读的静态报告；交互以HTML为准。"""
import html,re
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def pdf_report(data,paths,path):
    from comparison_report import COUNTRIES,value
    pdfmetrics.registerFont(TTFont('YaHei','C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
    styles={k:ParagraphStyle(k,fontName='YaHei',fontSize=s,leading=l,spaceAfter=sp) for k,s,l,sp in [('title',20,28,12),('heading',14,21,9),('body',9,14,8),('cell',8,11,0)]}
    story=[];W=720
    def safe(s):return html.escape(re.sub(r'[\u0600-\u06ff]+','',str(s))).strip(' |')
    def p(text,style='body'):
        text=re.sub(r'\d+(?:\.\d+)+',lambda m:' <nobr>'+m.group(0)+'</nobr> ',text)
        story.append(Paragraph(text,styles[style]))
    def table(headers,rows,widths,rich=False):
        allrows=[[Paragraph(safe(v),styles['cell']) for v in headers]]
        allrows += [[Paragraph(str(v) if rich else safe(v),styles['cell']) for v in row] for row in rows]
        t=Table(allrows,colWidths=[W*x for x in widths],repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#eaf1f7')),('GRID',(0,0),(-1,-1),.35,HexColor('#d4dde5')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,8)])
    def appcell(a):return safe(a['name'])+'<br/><font color="#5d7180">'+safe(a['brief'])+'</font>'
    p('工具 APP 三源数据与结论','title');p(f"报告日期 {data['report_date']} · DSP业务日期 {data['dsp_end']} · PalmStore采集 {data['ps_observation_date']} · GP总榜 {data['gp_history']['date']} · 两源对照 {data['gp_magic']['date']}")
    table(['DSP指标','榜首APP与用途','最新日数值'],[[label,appcell(data['dsp_rankings'][f][0]),value(data['dsp_rankings'][f][0][f],n)+' '+unit] for f,label,n,unit in [('downloads','下载',0,'次'),('revenue_usd','收益',4,'美元'),('unit_price_usd','单价',6,'美元/下载')]],[.13,.64,.23],True)
    a=data['ps_frequency'][0];p(f"PalmStore：{safe(a['name'])}出现{a['country_count']}/13国；仅出现国家的平均位置为{value(a['mean_position'],2)}。印度736、俄罗斯675保持编辑推荐，其余11国为Top Charts。")
    p(data.get('gp_comparison',{}).get('conclusion','AppMagic已取得9国实用工具Top10；未提供下载量数值。'))
    p('DSP表格下载和收益均为'+data['dsp_end']+'当日合计：汇总该日全部实际观测国家；不是日均，也不是多日累计。曲线每个点为对应业务日的当日值。下载=resp；收益=total_revenue÷1000，单位美元；单价=当日美元收益÷当日下载。三榜分别按最新日对应指标排序，只列主要功能资料已核验的工具；零下载不计算单价。')
    p('图表按各日实际返回国家汇总，国家覆盖可能变化；不能据此认定同范围增长。HTML中每张图可独立选择Top5至Top10、近7/14天，点击名称或曲线加粗，并隐藏或恢复曲线。')
    for f,label,n in [('downloads','下载',0),('revenue_usd','收益',4),('unit_price_usd','单价',6)]:
        story.append(PageBreak());p('DSP · '+label+'Top10','heading')
        p('表内数值为'+data['dsp_end']+'当日合计，汇总该日全部实际观测国家；不是日均或多日累计。')
        table(['名次','APP与用途','当日下载（次）','当日收益（美元）','当日单价（美元/下载）'],[[a['metric_rank'],appcell(a),value(a['downloads']),value(a['revenue_usd'],4),value(a['unit_price_usd'],6)] for a in data['dsp_rankings'][f]],[.055,.505,.12,.15,.17],True)
        if f=='unit_price_usd':p('单价榜保留少下载样本，不设置额外下载门槛；下载数是该单价的实际分母。')
        story.append(PageBreak());p('DSP · '+label+'Top10每日趋势','heading');story.append(Image(str(paths[f]),width=W,height=330));p(f"{data['days'][0]}至{data['days'][-1]}；每款APP一条线。缺行断线，零下载单价不可用。来源：DSP接口实际返回记录。")
    story.append(PageBreak());p('PalmStore · 工具出现频次Top10','heading');story.append(Image(str(paths['frequency']),width=W,height=318));p('13国各取前20项，共260个原榜/推荐席位，识别19款工具。出现国家数不等于连续上榜天数。')
    story.append(PageBreak());p('PalmStore · 各国名次 / 推荐位置','heading');story.append(Image(str(paths['ranks']),width=W,height=410));p('；'.join(c+' '+name for c,name in COUNTRIES.items())+'。IN和RU列为编辑推荐位置，其余为Top Charts名次。')
    story.append(PageBreak());p('PalmStore · 出现国家数、平均位置与用途','heading');p('平均位置仅对出现过的国家求均值，未出现国家不计入；总体均值混合指定列表位置，另列热门榜与编辑推荐均值。')
    table(['APP与用途','出现国数','平均位置','热门榜平均名次','推荐平均位置'],[[appcell(a),a['country_count'],value(a['mean_position'],2),value(a['mean_top_charts_rank'],2),value(a['mean_editor_position'],2)] for a in data['ps_frequency']],[.52,.09,.12,.135,.135],True)
    history=data['gp_history'];leader=history['aggregate'][0]
    story.append(PageBreak());p('GP · 全部国家工具热度Top10','heading')
    p(f"{history['date']} · 13国指定范围中，11国完整覆盖14天，共154份Top10日榜。叙利亚与刚果民主共和国缺榜，不计入分母。{safe(leader['name'])}以{value(leader['heat_index'],2)}热度指数排名第1，在{leader['country_count']}国进入前10，出现平均名次{value(leader['mean_appearing_rank'],2)}。")
    p(history['method'])
    table(['总榜名次','APP与用途','热度指数','Top10积分','出现国数','出现平均名次'],[[a['heat_rank'],appcell(a),value(a['heat_index'],2),a['score'],a['country_count'],value(a['mean_appearing_rank'],2)] for a in history['aggregate'][:10]],[.06,.49,.12,.1,.10,.13],True)
    for key,label in [('gp_heat','热度指数趋势'),('gp_rank','总榜排名位置变化')]:
        story.append(PageBreak());p('GP · 全部国家工具Top10 · '+label,'heading');story.append(Image(str(paths[key]),width=W,height=330))
        p(f"{history['days'][0]}至{history['days'][-1]}；固定展示{history['date']}工具Top10。13国范围，固定覆盖11国。名次越小越靠前；未进入已取得前10时，热度指数为0，实际商店名次未知。HTML支持近7/14天、Top5至Top10及各国原榜名次趋势。")
    story.append(PageBreak());p('GP · AppMagic与Sensor Tower交叉验证 · '+data['gp_magic']['date'],'heading')
    p(data.get('gp_comparison',{}).get('conclusion',''))
    for insight in data.get('gp_comparison',{}).get('insights',[]):p(insight)
    p('AppMagic：Google Play、实用工具、免费榜/下载量，名次按该来源估算下载顺序；Sensor Tower：Google Play、工具、免费下载，名次为商店榜。两种分类与排序方法可能不同，共同上榜用于佐证热度，不将名次转换为下载量。')
    comparison=data.get('gp_comparison',{})
    table(['国家','AppMagic已获取项数','Sensor Tower已获取项数','共同APP数','共同占Top10'],[[COUNTRIES[a['country']],a['appmagic_count'],a['sensor_count'],a['overlap_count'] if a['comparable'] else '不可比',value(a['overlap_ratio']*100,0)+'%' if a['comparable'] else '不可比'] for a in comparison.get('countries',[])],[.32,.17,.17,.17,.17])
    story.append(PageBreak());p('GP · AppMagic跨国出现频次Top10','heading');story.append(Image(str(paths['gp']),width=W,height=324));p('仅按AppMagic已获取的9国去重统计，未提供国家不计为未上榜。')
    for country in COUNTRIES:
        am=next((a for a in data['gp_magic']['charts'] if a['country']==country),None);st=next((a for a in data.get('gp_sensor',{}).get('charts',[]) if a['country']==country),None)
        if not am and not st:continue
        story.append(PageBreak());p('GP · '+COUNTRIES[country]+' '+country+' · '+data['gp_magic']['date'],'heading');p('两列分别按各自名次排列；同一行不代表同一APP。应用名称使用公共资料中的名称，包名用于跨来源对应。')
        table(['名次','AppMagic · APP与用途','Sensor Tower · APP与用途'],[[i+1,appcell(am['rows'][i]) if am else '来源未提供该国',appcell(st['rows'][i]) if st else '来源未提供该国'] for i in range(10)],[.055,.4725,.4725],True)
        for name,c in [('AppMagic',am),('Sensor Tower',st)]:
            if c:p(name+'来源：<link href="'+html.escape(c['url'],quote=True)+'" color="#1769aa">'+html.escape(c['url'])+'</link>')
    story.append(PageBreak());p('全部展示APP · 简要用途','heading')
    table(['APP','主用途','简要说明'],[[a['name'],a['subclass'],a['brief']] for a in data['app_functions']],[.37,.14,.49])
    story.append(PageBreak());p('PalmStore · 13国完整链接','heading')
    table(['国家','栏目','完整地址'],[[a['country_name']+' '+a['country'],a['chart_name'],a['url']] for a in data['ps_links']],[.22,.2,.58])
    def footer(c,doc):c.setFont('YaHei',8);c.drawString(36,20,'工具 APP 数据与结论 · '+data['report_date']);c.drawRightString(756,20,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=(792,612),leftMargin=36,rightMargin=36,topMargin=30,bottomMargin=34,title='工具APP三源数据与结论',author='').build(story,onFirstPage=footer,onLaterPages=footer)
