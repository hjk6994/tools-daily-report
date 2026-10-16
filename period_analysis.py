"""用已保存的真实快照复算期间热门与趋势；不联网、不补历史。"""
import json,sys,math,html,shutil
from pathlib import Path
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import pandas as pd

def span(end,n):
    d=datetime.fromisoformat(end)
    return [(d-timedelta(days=i)).date().isoformat() for i in reversed(range(n))]

def ratio(new,old):return new/old-1 if old and new is not None else None

def build(data):
    from comparison_report import COLORS,COUNTRIES
    end=(datetime.fromisoformat(data['report_date'])-timedelta(days=1)).date().isoformat()
    days=span(end,14)
    chunks=[chunk[chunk.date.isin(days)] for chunk in pd.read_csv(ROOT/'dsp_daily.csv',chunksize=100000)]
    dsp=pd.concat(chunks,ignore_index=True);meta=pd.read_csv(ROOT/'comparison_metadata.csv').fillna('')
    verified=meta[(meta.is_tool==True)&(meta.metadata_status=='verified')]
    lookup={r.package:{'package':r.package,'name':r['name'],'subclass':r.business_subclass,'brief':r.brief} for _,r in verified.iterrows()}
    dsp=dsp[dsp.date.isin(days)&dsp.package.isin(lookup)].copy()
    raw=dsp[['date','package','country','downloads','revenue_usd']].to_dict('records')
    daily=dsp.groupby(['package','date'])[['downloads','revenue_usd']].sum()
    all_daily=dsp.groupby('date').downloads.sum().to_dict()
    history=data['gp_history'];gps={c['country']+'|'+c['date']:c for c in history['charts']}
    gpcatalog={a['package']:a for a in history['catalog']}
    colors={p:COLORS[i%len(COLORS)] for i,p in enumerate(sorted(set(lookup)|set(gpcatalog)))}
    windows={}
    for n in [7,14]:
        selected=span(end,n);rows=dsp[dsp.date.isin(selected)];totals=rows.groupby('package')[['downloads','revenue_usd']].sum();apps=[]
        recent,prior=days[-7:],days[:7]
        for package,t in totals.iterrows():
            ps=[]
            for day in days:
                key=(package,day);v=daily.loc[key] if key in daily.index else None
                ps.append({'date':day,'downloads':float(v.downloads) if v is not None else None,'revenue_usd':float(v.revenue_usd) if v is not None else None,'unit_price_usd':float(v.revenue_usd/v.downloads) if v is not None and v.downloads>0 else None})
            obs=[p for p in ps if p['date'] in selected and p['downloads'] is not None]
            rp=[p for p in ps if p['date'] in recent and p['downloads'] is not None];bp=[p for p in ps if p['date'] in prior and p['downloads'] is not None]
            ready=len(rp)==7 and len(bp)==7
            rd=sum(p['downloads'] for p in rp);bd=sum(p['downloads'] for p in bp);rr=sum(p['revenue_usd'] for p in rp);br=sum(p['revenue_usd'] for p in bp)
            a=lookup[package]|{'downloads':float(t.downloads),'revenue_usd':float(t.revenue_usd),'unit_price_usd':float(t.revenue_usd/t.downloads) if t.downloads>0 else None,'observed_days':len(obs),'active_days':sum(p['downloads']>0 for p in obs),'country_count':int(rows[rows.package==package].country.nunique()),'color':colors[package],'points':ps,'recent_downloads':rd,'prior_downloads':bd,'download_gain':rd-bd if ready else None,'download_growth':ratio(rd,bd) if ready else None,'revenue_growth':ratio(rr,br) if ready else None,'price_growth':ratio(rr/rd if rd else None,br/bd if bd else None) if ready else None,'trend_complete':ready,'trend_note':'近7日对前7日，均有实际APP记录' if ready else f'近7日记录{len(rp)}/7，前7日{len(bp)}/7；缺行不补零','recent_share':rd/sum(all_daily.get(d,0) for d in recent) if sum(all_daily.get(d,0) for d in recent) else None,'peak_day_share':max((p['downloads'] for p in obs),default=0)/t.downloads if t.downloads>0 else None}
            a['prior_share']=bd/sum(all_daily.get(d,0) for d in prior) if sum(all_daily.get(d,0) for d in prior) else None
            a['share_delta_pp']=100*(a['recent_share']-a['prior_share']) if ready and a['recent_share'] is not None and a['prior_share'] is not None else None
            a['sample_note']='小样本：期间下载<100或有量不足3天；仅作观察' if a['downloads']<100 or a['active_days']<3 else ''
            a['state']='记录不足' if not ready else ('观测放量' if rd>bd else '近期回落' if rd<bd else '观测持平')
            if a['peak_day_share'] is not None and a['peak_day_share']>.5:a['state']+='；单日集中'
            apps.append(a)
        ranks={f:[a['package'] for a in sorted((a for a in apps if a[f] is not None),key=lambda a:(-a[f],a['package']))[:10]] for f in ['downloads','revenue_usd','unit_price_usd']}
        apps.sort(key=lambda a:(-a['downloads'],a['package']))
        gpscopes={}
        for scope in ['all']+list(COUNTRIES):
            countries=history['countries'] if scope=='all' else [scope]
            available=[d for d in selected if all(c+'|'+d in gps for c in countries)]
            members={a['package'] for d in available for c in countries for a in gps[c+'|'+d]['rows'] if a['tool_function']}
            gs=[]
            for package in members:
                points=[];locations={};positions=[];seen=0
                for day in days:
                    complete=all(c+'|'+day in gps for c in countries)
                    rawr=[(c,a['rank']) for c in countries if c+'|'+day in gps for a in gps[c+'|'+day]['rows'] if a['tool_function'] and a['package']==package]
                    ranked=next((a for a in history['rankings'][scope].get(day,[]) if a['package']==package),None)
                    score=sum(11-r for _,r in rawr)
                    points.append({'date':day,'heat_index':100*score/(10*len(countries)) if complete else None,'rank':ranked['heat_rank'] if scope=='all' and ranked else (rawr[0][1] if rawr and scope!='all' else None),'status':'缺榜' if not complete else '上榜' if rawr else '未进入所取Top10，实际名次未知'})
                    if day in available and rawr:
                        seen+=1
                        for c,r in rawr:locations.setdefault(c,[]).append(r);positions.append(r)
                heat=[p['heat_index'] for p in points if p['date'] in available]
                rec=[p['heat_index'] for p in points if p['date'] in recent];base=[p['heat_index'] for p in points if p['date'] in prior]
                ready=len(rec)==7 and len(base)==7 and all(v is not None for v in rec+base)
                # 窗口内方向用等长两段；明确日期，不能冒充7日环比。
                half=len(available)//2;first=available[:half];last=available[-half:] if half else []
                bydate={p['date']:p['heat_index'] for p in points}
                inside=(sum(bydate[d] for d in last)-sum(bydate[d] for d in first))/half if half else None
                gs.append({k:gpcatalog[package][k] for k in ['package','name','subclass','brief']}|{'color':colors[package],'mean_heat':sum(heat)/len(heat),'observed_days':len(available),'appearing_days':seen,'country_count':len(locations),'mean_appearing_rank':sum(positions)/len(positions),'country_days':len(positions),'positions':{c:sum(r)/len(r) for c,r in locations.items()},'points':points,'trend_complete':ready,'heat_delta':(sum(rec)-sum(base))/7 if ready else None,'within_delta':inside,'within_basis':f'窗口后{half}日均值减前{half}日均值（{first[0]}—{first[-1]} 对 {last[0]}—{last[-1]}）' if half else '数据不足','state':'窗口内升温' if inside is not None and inside>0 else '窗口内回落' if inside is not None and inside<0 else '窗口内持平'})
            gs.sort(key=lambda a:(-a['mean_heat'],-a['country_days'],a['mean_appearing_rank'],a['package']))
            for i,a in enumerate(gs):a['period_rank']=i+1
            gpscopes[scope]={'apps':gs,'available_days':available,'requested_days':n,'coverage_country_count':len(countries) if available else 0,'complete':len(available)==n,'missing_days':[d for d in selected if d not in available]}
        top=[next(a for a in apps if a['package']==p) for p in ranks['downloads']]
        ups=sorted((a for a in apps if a['trend_complete'] and (a['download_gain'] or 0)>0),key=lambda a:-(a['download_gain'] or 0))
        downs=sorted((a for a in apps if a['trend_complete'] and (a['download_gain'] or 0)<0),key=lambda a:a['download_gain'])
        dspcon=[f'{selected[0]}至{selected[-1]}，共{n}个已结束UTC业务日；期间{len(apps)}款主要功能已核验工具有记录。热门按期间累计下载，三榜分别排序；单价为期间收益÷期间下载。',f"期间下载前三："+'；'.join(f"{a['name']}（{a['subclass']}）{a['downloads']:,.0f}次" for a in top[:3])+'。']
        income_top=next(a for a in apps if a['package']==ranks['revenue_usd'][0]);price_top=next(a for a in apps if a['package']==ranks['unit_price_usd'][0])
        dspcon.append(f"期间收益榜首{income_top['name']}（{income_top['subclass']}）{income_top['revenue_usd']:,.2f}美元；加权单价榜首{price_top['name']}（{price_top['subclass']}）{price_top['unit_price_usd']:.6f}美元/下载，分母{price_top['downloads']:,.0f}次、有量{price_top['active_days']}天。"+(price_top['sample_note']+'。' if price_top['sample_note'] else ''))
        if ups:dspcon.append('近7日对前7日，观测下载增量靠前：'+'；'.join(f"{a['name']}（{a['subclass']}）增加{a['download_gain']:,.0f}次" for a in ups[:3])+'。')
        if downs:dspcon.append('观测下载回落较多：'+'；'.join(f"{a['name']}（{a['subclass']}）减少{-a['download_gain']:,.0f}次" for a in downs[:3])+'。')
        dspcon.append('下载与收益变化可能包含投放及国家结构变化，不解释为自然需求或广告主盈利。缺少APP记录的日期不补零；业务日期已结束不代表已封账。')
        ga=gpscopes['all'];gpcon=[f"{selected[0]}至{selected[-1]}，固定{len(history['countries'])}国；取得{len(ga['available_days'])}/{n}个完整国家日组。SY、CD缺榜。主榜按可用日平均Top10榜单热度排序，不能换算下载。",'期间热度前三：'+'；'.join(f"{a['name']}（{a['subclass']}）均值{a['mean_heat']:.2f}、上榜{a['appearing_days']}/{a['observed_days']}天" for a in ga['apps'][:3])+'。','近7日对前7日数据不足：前期缺2026-09-26，7日环比不可用；另展示窗口内等长两段的均值变化，标明实际日期。观察范围仅来源“工具”分类Top10，榜外不等于不热门。']
        gpup=sorted((a for a in ga['apps'] if (a['within_delta'] or 0)>0),key=lambda a:-a['within_delta'])
        gpdown=sorted((a for a in ga['apps'] if (a['within_delta'] or 0)<0),key=lambda a:a['within_delta'])
        if gpup:gpcon.append('窗口内升温靠前：'+'；'.join(f"{a['name']}（{a['subclass']}）+{a['within_delta']:.2f}指数点" for a in gpup[:3])+'。依据：'+gpup[0]['within_basis']+'；不是下载增长率。')
        if gpdown:gpcon.append('窗口内回落靠前：'+'；'.join(f"{a['name']}（{a['subclass']}）{a['within_delta']:.2f}指数点" for a in gpdown[:2])+'。')
        hotps=sorted(data['ps_frequency'],key=lambda a:(-a['top_charts_count'],a['mean_top_charts_rank'] or 99,a['package']))
        pscon=[f"仅{data['ps_observation_date']}一次多国快照，近7/14天趋势均不足，不生成历史曲线或连续升位结论。",'11国Top Charts中出现较广：'+'；'.join(f"{a['name']}（{a['subclass']}）{a['top_charts_count']}国、出现平均名次{a['mean_top_charts_rank']:.2f}" for a in hotps[:3])+'。','印度736与俄罗斯675保留为编辑推荐，只作推荐覆盖参考；其位置不进入热门榜频次排序及平均名次。所有13国的原位置仍单列保留。']
        dm={a['package']:a for a in apps};gm={a['package']:a for a in ga['apps']};pm={a['package']:a for a in data['ps_frequency']}
        candidates=list(dict.fromkeys(ranks['downloads']+[a['package'] for a in ups[:5]]+[a['package'] for a in ga['apps'][:10]+hotps[:5]]))
        joint=[]
        for package in candidates:
            a=dm.get(package);g=gm.get(package);p=pm.get(package);info=lookup.get(package) or gpcatalog.get(package) or p
            notes=[]
            if a:notes.append('DSP '+a['state'])
            else:notes.append('DSP没有已核验期间记录，投放表现未知')
            if g:notes.append(f"GP出现{g['appearing_days']}/{g['observed_days']}天"+('；14日窗仅13日' if not ga['complete'] else ''))
            else:notes.append('未进所取GP工具Top10，不能认定市场冷门')
            if p:notes.append(f"PS热门榜{p['top_charts_count']}国、推荐{p['editor_count']}国，仅快照")
            tier='投放热门观察' if a else '市场或渠道观察'
            if a and a['state'].startswith('观测放量'):tier='投放放量观察'
            if a and a['state'].startswith('近期回落'):tier='近期回落观察'
            if a and a['sample_note']:
                tier='小样本观察';notes.append(a['sample_note'])
            joint.append({k:info[k] for k in ['package','name','subclass','brief']}|{'tier':tier,'dsp_downloads':a['downloads'] if a else None,'dsp_growth':a['download_growth'] if a else None,'gp_heat':g['mean_heat'] if g else None,'gp_days':g['appearing_days'] if g else None,'ps_hot_countries':p['top_charts_count'] if p else None,'conclusion':'；'.join(notes)+'。'})
        leader=top[0]
        leader_note=f"期间下载最高为{leader['name']}（{leader['subclass']}），{leader['downloads']:,.0f}次。"
        if leader['trend_complete'] and leader['download_growth'] is not None:
            leader_note+=f"近7日下载较前7日{leader['download_growth']*100:+.1f}%，收益{leader['revenue_growth']*100:+.1f}%，加权单价{leader['price_growth']*100:+.1f}%；规模领先与近期升温需要分别判断。"
        jointcon=[leader_note]
        supported=[a for a in ups if a['package'] in gm and gm[a['package']]['appearing_days']>=.7*gm[a['package']]['observed_days'] and not a['sample_note']]
        if supported:
            a=supported[0];g=gm[a['package']]
            jointcon.append(f"{a['name']}（{a['subclass']}）是有市场热度佐证的投放放量对象：近7日下载增加{a['download_gain']:,.0f}次（{a['download_growth']*100:+.1f}%），GP在可用{g['observed_days']}日中持续出现{g['appearing_days']}日、期间平均热度{g['mean_heat']:.2f}。其DSP收益{a['revenue_growth']*100:+.1f}%、单价{a['price_growth']*100:+.1f}%，量价方向分别说明；GP持续上榜不等于GP同步增长。")
        market=[g for g in ga['apps'] if g['package'] in pm and pm[g['package']]['top_charts_count']>=5]
        if market:
            g=market[0];p=pm[g['package']]
            jointcon.append(f"{g['name']}（{g['subclass']}）具有市场与渠道覆盖证据：GP期间平均热度{g['mean_heat']:.2f}、出现{g['appearing_days']}/{g['observed_days']}日；PalmStore当前热门榜出现{p['top_charts_count']}/11国。渠道证据仅为单次快照，不能据此确认传音下载规模或连续增长。")
        jointcon.append('GP的完整7日对7日比较不足，PalmStore无期间历史，本次不能给出“三源趋势一致上升”的结论。DSP为全部实际投放国家，GP为指定国家工具榜；跨源覆盖不同，保留分歧。')
        windows[str(n)]={'days':selected,'dsp':{'apps':apps,'rankings':ranks,'conclusions':dspcon,'rising':[a['package'] for a in ups],'falling':[a['package'] for a in downs]},'gp':gpscopes,'gp_conclusions':gpcon,'ps_conclusions':pscon,'joint':joint,'joint_conclusions':jointcon}
        for source,records in [('dsp',apps),('gp',ga['apps']),('joint',joint)]:
            pd.DataFrame([{k:v for k,v in a.items() if k not in ['points','positions']} for a in records]).to_csv(ROOT/f'{source}_period_{n}d.csv',index=False,encoding='utf-8-sig')
    merged={a['package']:a for a in data['app_functions']}
    for w in windows.values():
        for a in w['dsp']['apps']:merged.setdefault(a['package'],{k:a[k] for k in ['package','name','subclass','brief']})
    data['app_functions']=list(merged.values());pd.DataFrame(data['app_functions']).to_csv(ROOT/'app_function_catalog.csv',index=False,encoding='utf-8-sig')
    return {'end':end,'timezone':'UTC+0','days':days,'windows':windows,'dsp_rows':raw,'source_days':{'DSP':14,'GP':13,'PalmStore':1},'gp_realtime_excluded':[d for d in history['days'] if d>end],'notes':['DSP按用户确认的传音投放范围解释；接口未另提供设备字段。','零下载不计算单价；缺行不代表零下载。','GP保留原商店名次；排名积分不是下载量。','未采集新的业务数据；使用真实缓存复算，保留来源日期。']}

def main():
    data=json.loads((ROOT/'data/comparison_report_data.json').read_text(encoding='utf-8'))
    data['period_analysis']=build(data)
    from daily_tables import build as build_daily
    data['daily_tables']=build_daily(data)
    from palmstore_view import build as build_palmstore
    data['palmstore_view']=build_palmstore(data)
    from gp20_analysis import build as build_gp20
    data['gp20_analysis']=build_gp20(data)
    pd.DataFrame(data['app_functions']).to_csv(ROOT/'app_function_catalog.csv',index=False,encoding='utf-8-sig')
    data['ranking_scope']='DSP为前一天三个指标独立Top20，成本及单价须日下载≥300；历史7/14天用于本榜次数与小图。GP为固定20日原Top20复算，总榜按各国已观察日均热度等权平均，原榜出现日期去重计次；缺日为临时排名及次数下限。PalmStore按13国列表覆盖合并次数降序。'
    (ROOT/'data/comparison_report_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    out=ROOT/'output';history=out/'history';history.mkdir(exist_ok=True)
    for suffix in ['html','pdf']:
        existing=out/f'report_20261010.{suffix}';backup=history/f'report_20261010_before_gp20_palmstore_bars.{suffix}'
        if existing.exists() and not backup.exists():shutil.copy2(existing,backup)
    template=(ROOT/'period_template.html').read_text(encoding='utf-8')
    script=(ROOT/'period_script.js').read_text(encoding='utf-8')
    template=template.replace('__SCRIPT__',script).replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    filename='工具类APP热度趋势日报'+data['report_date'].replace('-','')
    template=template.replace('__REPORT_NAME__',filename)
    template=template.replace('__PS_DATE__',data['ps_observation_date'])
    (out/f'{filename}.html').write_text(template,encoding='utf-8')
    # 旧浏览器地址保留兼容跳转，不继续展示旧版正文。
    (out/'report_20261010.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='+filename+'.html"><title>'+filename+'</title><a href="'+filename+'.html">'+filename+'</a></html>',encoding='utf-8')
    from period_pdf import render
    render(data,out/f'{filename}.pdf')
    print(json.dumps({'end':data['period_analysis']['end'],'DSP_apps':len(data['period_analysis']['windows']['14']['dsp']['apps']),'GP20_charts':data['gp20_analysis']['chart_count'],'GP20_complete_all_days':len(data['gp20_analysis']['scopes']['all']['available_days']),'functions':len(data['app_functions'])},ensure_ascii=False))

if __name__=='__main__':main()
