"""生成真实三源数据对比报告；每张 DSP 图展示5至10款工具。"""
import os,sys,json,html,re,base64
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp'/'matplotlib'))
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from collect import now,config
from app_functions import function_for
FP=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
plt.rcParams['font.family']=FP.get_name();plt.rcParams['axes.unicode_minus']=False
COLORS=['#1769aa','#e46b17','#238b45','#a84b9b','#d34242','#6558b1','#078c99','#8a642e','#af2c73','#667526']
COUNTRIES={'PK':'巴基斯坦','IN':'印度','NG':'尼日利亚','ID':'印度尼西亚','BD':'孟加拉国','PH':'菲律宾','CI':'科特迪瓦','IQ':'伊拉克','RU':'俄罗斯','SY':'叙利亚','SA':'沙特阿拉伯','CD':'刚果民主共和国','BF':'布基纳法索'}
PS_TOOLS={
 'com.talpa.hibrowser':('Hola','浏览器'),'com.playit.videoplayer':('PLAYit','本地播放器'),
 'com.dewmobile.kuaiya.play':('Zapya','文件传输'),'com.lenovo.anyshare.gps':('SHAREit','文件传输'),
 'com.snaptube.premium':('Snaptube','媒体下载'),'cn.wps.moffice_eng':('WPS Office','文档处理'),
 'com.transsion.phoenix':('Phoenix','浏览器'),'com.intsig.camscanner':('CamScanner','文档扫描'),
 'com.opera.mini.native':('Opera Mini','浏览器'),'com.dywx.larkplayer':('Lark Player','本地播放器'),
 'cn.xender':('Xender','文件传输'),'com.truecaller':('Truecaller','来电管理'),
 'com.lemon.lvoverseas':('CapCut','视频编辑'),'com.bigwinepot.nwdn.international':('Remini','图片编辑'),
 'com.picsart.studio':('Picsart','图片视频编辑'),'vsin.t16_funny_photo':('Photo Lab','图片编辑'),
 'com.camerasideas.instashot':('InShot','视频编辑'),'com.maps.locator.gps.gpstracker.phone':('Phone Tracker and GPS Location','定位工具'),
 'com.phongphan.miracast':('Miracast','屏幕投射')}
MANUAL={
 'com.dubox.drive':'云存储','com.eyecon.global':'来电管理','app.source.getcontact':'来电管理',
 'com.opera.mini.native':'浏览器','com.bbg.callerblock.blockspammer':'来电管理','com.ltd.trustcall.callerblock.number':'来电管理',
 'com.redfinger.global':'云手机','com.ezt.pdfreader.pdfviewer':'文档处理','com.herofightinggames.duck.blast':'启动器',
 'com.atc.calleraid.callerid':'来电管理','com.callerid.phonenumbertracker.spamcall':'来电管理','com.truecaller.callerid.callername':'来电管理',
 'com.funny.voicechanger.free.voiceeditor.voiceeffects.soundeffects':'音频处理','com.reverse.audio.singchallenge':'音频处理',
 'com.diy.wallpaper.maker.collage':'主屏定制'}

def clean(obj):return json.loads(json.dumps(obj,ensure_ascii=False,default=str).replace('NaN','null'))
def value(x,n=0):return '不可用' if x is None or pd.isna(x) else f'{x:,.{n}f}'
def datasets():
    d=pd.read_csv(ROOT/'dsp_daily.csv');days=sorted(d.date.unique())[-14:];d=d[d.date.isin(days)].copy()
    meta=pd.read_csv(ROOT/'comparison_metadata.csv')
    for ix,r in meta.iterrows():
        function=function_for(r.package,r.get('name',''),r.get('summary',''),r.get('official_category',''))
        sub=function[0] if function else None
        meta.loc[ix,'business_subclass']=sub;meta.loc[ix,'brief']=function[1] if function else None
        meta.loc[ix,'is_tool']=bool(sub) and r.metadata_status=='verified'
        meta.loc[ix,'classification_basis']='依据Google Play主要功能资料及中文用途映射' if sub else '主要功能不属于工具用途或资料未核验'
    meta.to_csv(ROOT/'comparison_metadata.csv',index=False,encoding='utf-8-sig')
    meta.to_csv(ROOT/'app_metadata.csv',index=False,encoding='utf-8-sig')
    totals=d[d.date==days[-1]].groupby('package')[['downloads','revenue_usd']].sum().reset_index()
    tools=totals.merge(meta[meta.is_tool==True][['package','name','developer','business_subclass','brief']],on='package').sort_values(['downloads','package'],ascending=[False,True])
    tools['unit_price_usd']=tools.revenue_usd/tools.downloads.replace(0,np.nan)
    six=days[-6:];rankings={}
    for field in ['downloads','revenue_usd','unit_price_usd']:
        selected=tools[tools[field].notna()].sort_values([field,'package'],ascending=[False,True]).head(10).copy()
        selected['metric']=field;selected['metric_rank']=range(1,len(selected)+1)
        rankings[field]=clean(selected.to_dict('records'))
        selected.to_csv(ROOT/f'dsp_{field}_top10.csv',index=False,encoding='utf-8-sig')
    selected_packages=list(dict.fromkeys(a['package'] for rank in rankings.values() for a in rank))
    extra_colors=['#155c51','#86471d','#9b2237','#555eac','#637b22','#327eaa','#a15186','#793e81','#617985','#b58a12','#b14a18','#244d80','#485c32','#655341','#0c7478','#a0485e','#4952a4','#87991a','#17694d','#9a6416']
    color_map={p:(COLORS+extra_colors)[i] for i,p in enumerate(selected_packages)}
    top=tools[tools.package.isin(selected_packages)].copy();top['color']=top.package.map(color_map)
    metrics=pd.read_csv(ROOT/'metrics.csv');metric_lookup=metrics.set_index('package')
    apps=[];series=[]
    for _,r in top.iterrows():
        common=set.intersection(*[set(d[(d.package==r.package)&(d.date==day)].country) for day in six])
        app={**r.to_dict(),'countries':sorted(common)}
        app['coverage_base']=float(metric_lookup.loc[r.package,'coverage_base']) if r.package in metric_lookup.index else None
        app['coverage_recent']=float(metric_lookup.loc[r.package,'coverage_recent']) if r.package in metric_lookup.index else None
        apps.append(clean(app))
        for day in days:
            rows=d[(d.package==r.package)&(d.date==day)&d.country.isin(common)]
            complete=bool(common) and common.issubset(set(rows.country))
            downloads=float(rows.downloads.sum()) if complete else None
            income=float(rows.revenue_usd.sum()) if complete else None
            series.append({'package':r.package,'date':day,'downloads':downloads,'revenue_usd':income,'unit_price_usd':income/downloads if downloads and income is not None else None,'status':'observed' if complete else 'missing_comparable_country'})
    for field,ranking in rankings.items():
        for i,a in enumerate(ranking):a['color']=color_map[a['package']];a['countries']=next(x['countries'] for x in apps if x['package']==a['package'])
    pd.DataFrame(rankings['downloads']).to_csv(ROOT/'dsp_comparison_top10.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(series).to_csv(ROOT/'dsp_comparison_series.csv',index=False,encoding='utf-8-sig')
    link_snapshot=sorted((ROOT/'data'/'raw').glob('ps_browser_links_*.json'))[-1]
    links=json.loads(link_snapshot.read_text(encoding='utf-8'))
    pd.DataFrame(links).to_csv(ROOT/'palmstore_country_links.csv',index=False,encoding='utf-8-sig')
    audit=json.loads((ROOT/'data'/'ps_multicountry_audit.json').read_text(encoding='utf-8'))
    linkmap={x['country']:x for x in links};valid=[]
    for a in audit:
        country=a['requested_country'];link=linkmap[country]
        if a.get('depth',0)>=20 and a.get('chart_name')==link['chart_name'] and str(a.get('chart_id'))==link['chart_id']:
            a['status']='complete_observed_top20';a['actual_country']=country;a['country_verification']='浏览器页面地区与用户指定国家匹配；榜单前项已核对；响应本身未填国家字段';valid.append(country)
        else:a['status']='unverified_selected_list'
    (ROOT/'data'/'ps_multicountry_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    ps=pd.read_csv(ROOT/'ps_multicountry_snapshots.csv');ps=ps[(ps['rank']<=20)&ps.requested_country.isin(valid)].copy()
    ps['actual_country']=ps.requested_country;ps['status']='complete_observed_top20';ps['position_type']=np.where(ps.chart_name=="Editor's Choice",'编辑推荐位置','Top Charts 原榜名次')
    ps['is_tool']=ps.package.isin(PS_TOOLS);ps['canonical_name']=ps.package.map(lambda p:PS_TOOLS[p][0] if p in PS_TOOLS else None)
    ps['business_subclass']=ps.package.map(lambda p:PS_TOOLS[p][1] if p in PS_TOOLS else None)
    ps.to_csv(ROOT/'ps_top20_13countries.csv',index=False,encoding='utf-8-sig')
    ps.rename(columns={'observation_date':'date'}).to_csv(ROOT/'ps_snapshots.csv',index=False,encoding='utf-8-sig')
    pt=ps[ps.is_tool];frequency=[]
    for package,g in pt.groupby('package'):
        places={r.requested_country:int(r['rank']) for _,r in g.iterrows()}
        info=function_for(package);hot=g[g.chart_name=='Top Charts']['rank'];editor=g[g.chart_name=="Editor's Choice"]['rank']
        frequency.append({'package':package,'name':PS_TOOLS[package][0],'subclass':info[0],'brief':info[1],'country_count':len(places),'mean_position':float(g['rank'].mean()),'mean_top_charts_rank':float(hot.mean()) if len(hot) else None,'mean_editor_position':float(editor.mean()) if len(editor) else None,'top_charts_count':int(g[g.chart_name=='Top Charts'].requested_country.nunique()),'editor_count':int(g[g.chart_name=="Editor's Choice"].requested_country.nunique()),'best_top_charts_rank':int(hot.min()) if len(hot) else None,'positions':places,'locations_text':'；'.join(f'{COUNTRIES[c]} {places[c]}'+('（推荐位置）' if c in ['IN','RU'] else '名') for c in COUNTRIES if c in places)})
    frequency=sorted(frequency,key=lambda a:(-a['country_count'],-a['top_charts_count'],a['best_top_charts_rank'] or 99,a['name']))
    pd.DataFrame([{k:v for k,v in r.items() if k!='positions'} for r in frequency]).to_csv(ROOT/'ps_tool_frequency.csv',index=False,encoding='utf-8-sig')
    gp_snapshot=sorted((ROOT/'data'/'raw').glob('gp_public_observed_*.json'))[-1]
    gp=json.loads(gp_snapshot.read_text(encoding='utf-8'))
    for a in gp['apps']:
        num,unit=a['recent_30d_display'].split();a['estimated_recent_downloads']=float(num)*{'million':1e6,'thousand':1e3,'billion':1e9}[unit]
        a['country']=None;a['scope']='整体口径，未分国家';a['estimate_status']='供应商公开页的舍入估算';a['observation_date']=a['collected_at'][:10]
    pd.DataFrame(gp['apps']).to_csv(ROOT/'gp_public_snapshots.csv',index=False,encoding='utf-8-sig')
    gp_standard=[]
    for a in gp['apps']:
        total_num,total_unit=a['total_display'].split()
        gp_standard.append({'date':a['observation_date'],'package':a['package'],'name':a['name'],'developerName':'Google LLC','marketCategory':'Tools','estimatedDownloads':int(float(total_num)*{'million':1e6,'billion':1e9}[total_unit]),'estimatedRecentDownloads':int(a['estimated_recent_downloads']),'infoRefreshTime':None,'data_updated_date':a['data_updated'],'country':None,'scope':'整体口径，未分国家','source_type':'appbrain_public_page','estimate_status':'公开页舍入估算','snapshot':str(gp_snapshot.relative_to(ROOT)),'collected_at':a['collected_at']})
    gp_path=ROOT/'gp_snapshots.csv';previous=pd.read_csv(gp_path) if gp_path.exists() else pd.DataFrame()
    if len(previous):previous['source_type']=previous.get('source_type',pd.Series('appbrain_api',index=previous.index)).fillna('appbrain_api')
    combined=pd.concat([previous,pd.DataFrame(gp_standard)],ignore_index=True).drop_duplicates(['date','package','source_type'],keep='last')
    combined.to_csv(gp_path,index=False,encoding='utf-8-sig')
    qualified=metrics[metrics.numerical_qualified==True].merge(meta[meta.is_tool==True][['package','name','developer','business_subclass','brief']],on='package').sort_values('R',ascending=False)
    qualified.to_csv(ROOT/'current_tool_candidates.csv',index=False,encoding='utf-8-sig')
    qualified.to_csv(ROOT/'candidates.csv',index=False,encoding='utf-8-sig')
    tools.to_csv(ROOT/'tools_latest.csv',index=False,encoding='utf-8-sig')
    from appmagic_data import build as magic_data
    magic=magic_data()
    from sensortower_data import build as sensor_data
    sensor,comparison=sensor_data(magic)
    from gp_history_data import build as history_data
    history=history_data()
    catalog={a['package']:{'package':a['package'],'name':a['name'],'subclass':a['business_subclass'],'brief':a['brief']} for a in apps+clean(qualified.to_dict('records'))}
    for a in frequency:catalog.setdefault(a['package'],{k:a[k] for k in ['package','name','subclass','brief']})
    for a in magic['frequency']:catalog.setdefault(a['package'],{k:a[k] for k in ['package','name','subclass','brief']})
    for chart in sensor['charts']:
        for a in chart['rows']:catalog.setdefault(a['package'],{k:a[k] for k in ['package','name','subclass','brief']})
    for a in history['catalog']:catalog.setdefault(a['package'],a)
    pd.DataFrame(catalog.values()).to_csv(ROOT/'app_function_catalog.csv',index=False,encoding='utf-8-sig')
    return {'report_date':now()[:10],'dsp_end':days[-1],'ps_observation_date':ps.observation_date.max(),'gp_observation_date':magic['observation_date'],'days':days,'apps':rankings['downloads'],'dsp_rankings':rankings,'series':series,'dsp_rows':d[d.package.isin(top.package)][['date','package','country','downloads','revenue_usd']].to_dict('records'),'ps_frequency':frequency,'ps_rows':clean(ps.to_dict('records')),'ps_links':links,'ps_audit':audit,'gp':gp,'gp_magic':magic,'gp_sensor':sensor,'gp_comparison':comparison,'gp_history':history,'app_functions':list(catalog.values()),'candidates':clean(qualified.to_dict('records')),'verified_tools':len(tools),'metadata_unknown_count':int((meta.metadata_status!='verified').sum()),'ranking_scope':'最新日已核验用途的工具APP'}

def figures(data,out):
    paths={};days=data['days'];frame=pd.DataFrame(data['dsp_rows']).groupby(['package','date'])[['downloads','revenue_usd']].sum().reset_index();frame['unit_price_usd']=frame.revenue_usd/frame.downloads.where(frame.downloads>0)
    for field,label,dec in [('downloads','每日下载（次）',0),('revenue_usd','每日收益（美元）',2),('unit_price_usd','每日单价（美元/下载）',5)]:
        fig,ax=plt.subplots(figsize=(12,5.5))
        for a in data['dsp_rankings'][field]:
            s=frame[frame.package==a['package']].set_index('date').reindex(days)
            ax.plot(range(len(days)),s[field],label=a['name'],color=a['color'],marker='o',markersize=3,linewidth=1.7)
        ax.set_title('DSP 工具 Top10 · '+label,fontproperties=FP,fontsize=15,pad=16)
        ax.set_ylabel(label,fontproperties=FP,fontsize=11);ax.set_xlabel('业务日期 · 各日实际观测国家汇总；缺行断线',fontproperties=FP,fontsize=10)
        ax.set_xticks(range(len(days)),[x[5:] for x in days]);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.18),ncol=2,prop=FontProperties(fname=FP.get_file(),size=8),frameon=False)
        fig.subplots_adjust(left=.09,right=.98,top=.88,bottom=.32);path=out/(field+'_top10.png');fig.savefig(path,dpi=180);plt.close(fig);paths[field]=path
    freq=data['ps_frequency'];ff=freq[:10];fig,ax=plt.subplots(figsize=(12,5.3))
    ax.barh(range(len(ff)),[x['country_count'] for x in ff],color='#1769aa');ax.invert_yaxis();ax.set_yticks(range(len(ff)),[x['name'] for x in ff]);ax.set_xlim(0,14);ax.set_xticks(range(0,14));ax.set_xlabel('出现国家数（同国只计1次；共13国指定列表）',fontproperties=FP);ax.set_title('PalmStore 工具出现频次 Top10',fontproperties=FP,fontsize=15)
    for i,a in enumerate(ff):ax.text(a['country_count']+.15,i,str(a['country_count']),va='center')
    ax.spines[['top','right']].set_visible(False);fig.tight_layout();path=out/'ps_frequency.png';fig.savefig(path,dpi=180);plt.close(fig);paths['frequency']=path
    arr=np.array([[a['positions'].get(c,np.nan) for c in COUNTRIES] for a in freq]);fig,ax=plt.subplots(figsize=(13,7.5));im=ax.imshow(arr,cmap='Blues_r',vmin=1,vmax=20,aspect='auto')
    ax.set_yticks(range(len(freq)),[a['name'] for a in freq]);ax.set_xticks(range(13),[c+(' *' if c in ['IN','RU'] else '') for c in COUNTRIES]);ax.xaxis.tick_top()
    for y in range(len(freq)):
        for x in range(13):
            v=arr[y,x];ax.text(x,y,'—' if np.isnan(v) else str(int(v)),ha='center',va='center',color='#555' if np.isnan(v) or v>=10 else 'white',fontsize=10)
    ax.set_title('PalmStore 13国指定列表 Top20 · 名次 / 推荐位置\nIN、RU：编辑推荐位置；其余：Top Charts 原榜名次。—：未出现在该列表Top20。',fontproperties=FP,fontsize=13,pad=20)
    fig.colorbar(im,ax=ax,shrink=.5,label='名次 / 推荐位置（越小越靠前）');fig.tight_layout();path=out/'ps_country_ranks.png';fig.savefig(path,dpi=180);plt.close(fig);paths['ranks']=path
    gp=data['gp_magic']['frequency'][:10];fig,ax=plt.subplots(figsize=(12,5.4));ax.barh(range(len(gp)),[a['country_count'] for a in gp],color='#1769aa');ax.invert_yaxis();ax.set_yticks(range(len(gp)),[a['name'] for a in gp]);ax.set_xlim(0,10)
    for i,a in enumerate(gp):ax.text(a['country_count']+.12,i,str(a['country_count']),va='center')
    ax.set_xlabel(f"进入国家Top10的次数（同国只计1次；已获取{len(data['gp_magic']['charts'])}国）",fontproperties=FP);ax.set_title('GP / AppMagic 实用工具跨国出现频次 Top10',fontproperties=FP,fontsize=14);ax.spines[['top','right']].set_visible(False);fig.tight_layout();path=out/'gp_top10.png';fig.savefig(path,dpi=180);plt.close(fig);paths['gp']=path
    history=data['gp_history']
    for metric,label in [('heat_index','Top10热度指数'),('heat_rank','总榜名次（越小越靠前）')]:
        fig,ax=plt.subplots(figsize=(12,5.5));gpdays=history['days']
        for a in history['aggregate'][:10]:
            points=history['series']['all'][a['package']]
            ax.plot(range(len(gpdays)),[p[metric] if p[metric] is not None else np.nan for p in points],color=a['color'],label=a['name'],marker='o',markersize=3,linewidth=1.7)
        if metric=='heat_rank':ax.invert_yaxis()
        ax.set_title('GP 全部国家工具Top10 · '+label,fontproperties=FP,fontsize=15,pad=16)
        ax.set_ylabel(label,fontproperties=FP);ax.set_xlabel('榜单日期 · 13国范围，固定覆盖11国，各国等权',fontproperties=FP,fontsize=10)
        ax.set_xticks(range(len(gpdays)),[d[5:] for d in gpdays]);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.18),ncol=2,prop=FontProperties(fname=FP.get_file(),size=8),frameon=False)
        fig.subplots_adjust(left=.09,right=.98,top=.88,bottom=.32);key='gp_heat' if metric=='heat_index' else 'gp_rank';path=out/(key+'.png');fig.savefig(path,dpi=180);plt.close(fig);paths[key]=path
    return paths

def html_report(data,path):
    template=(ROOT/'comparison_template_v2.html').read_text(encoding='utf-8')
    template=template.replace('__GP_HISTORY_SCRIPT__',(ROOT/'gp_history_script.js').read_text(encoding='utf-8'))
    template=template.replace('__GP_COMPARE_SCRIPT__',(ROOT/'gp_compare_script.js').read_text(encoding='utf-8'))
    path.write_text(template.replace('__DATA__',json.dumps(clean(data),ensure_ascii=False).replace('</','<\\/')),encoding='utf-8')

def pdf_report(data,paths,path):
    from report_pdf import pdf_report as render_pdf
    render_pdf(data,paths,path)

def main():
    data=datasets();output=ROOT/'output';output.mkdir(exist_ok=True);figdir=output/'comparison_figures';figdir.mkdir(exist_ok=True)
    stamp=data['report_date'].replace('-','');(ROOT/'data'/'comparison_report_data.json').write_text(json.dumps(clean(data),ensure_ascii=False,indent=2),encoding='utf-8')
    # 当前DSP交付为前一天独立Top20；期间缓存支持GP表格及历史小图。
    from period_analysis import main as period_main
    period_main()
if __name__=='__main__':main()
