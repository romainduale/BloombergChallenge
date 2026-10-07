import argparse, csv, datetime as dt, gzip, hashlib, json, pathlib, re, zipfile
import collections
import openpyxl
import pandas as pd
from lxml import etree as ET

parser=argparse.ArgumentParser()
parser.add_argument('--input',default='upload')
parser.add_argument('--output',default='outputs/bloomberg_data')
args=parser.parse_args()
src=pathlib.Path(args.input); out=pathlib.Path(args.output)
for d in ['data','supplementary','audit','scripts']: (out/d).mkdir(parents=True,exist_ok=True)
ASOF='2026-10-07'
manifest=[]; quality=[]; mappings=[]
def clean(x):
    if x is None or isinstance(x,str) and x.startswith('#'): return None
    if isinstance(x,str):return x.strip()
    return x
def date(x):
    if x is None or pd.isna(x):return None
    if isinstance(x,(int,float)):x=openpyxl.utils.datetime.from_excel(x)
    return x.strftime('%Y-%m-%d') if hasattr(x,'strftime') else str(x)
def read(name,sheet=None,skip=0):
    p=src/name; w=openpyxl.load_workbook(p,read_only=True,data_only=True)
    rows=list((w[sheet] if sheet else w.active).values);w.close()
    return rows[skip]
def rows(name,sheet=None,skip=0):
    p=src/name;w=openpyxl.load_workbook(p,read_only=True,data_only=True)
    r=list((w[sheet] if sheet else w.active).values);w.close()
    cleaned=[[clean(c) for c in row] for row in r[skip+1:]]
    return [row for row in cleaned if any(c is not None for c in row)]
def frame(name,cols,sheet=None,skip=0):
    h=read(name,sheet,skip);mappings.extend({'source':name,'sheet':sheet or 'first','source_column':str(a),'output_column':b} for a,b in zip(h,cols))
    return pd.DataFrame(rows(name,sheet,skip),columns=cols)
def save(df,name,keys=None,folder='data'):
    if keys:
        assert not df.duplicated(keys).any(),(name,'duplicate keys')
        df=df.sort_values(keys,kind='stable')
    p=out/folder/name
    df.to_csv(p,index=False,float_format='%.17g',encoding='utf-8',compression='gzip' if name.endswith('.gz') else None)
    manifest.append({'path':str(p.relative_to(out)),'rows':len(df),'columns':len(df.columns),'size_bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    for c in df.columns:
        quality.append({'file':str(p.relative_to(out)),'column':c,'rows':len(df),'missing':int(df[c].isna().sum())})
    return df

u=frame('wls_universe(1).xlsx',['ticker_exchange','name','index_weight_pct','index_position_source','px_last_universe'])
u.insert(0,'id',u.ticker_exchange+' Equity');u['index_weight']=u.index_weight_pct/100
assert abs(u.index_weight.sum()-1)<1e-10
save(u,'universe.csv',['id'])
st=frame('wls_static(1).xlsx',['id','px_last','volume_latest','market_cap','sector'],skip=1)
st.insert(1,'as_of_date',ASOF);save(st,'static.csv',['id'])
mo=frame('wls_momentum(1).xlsx',['id','as_of_date','px_last','mom_1m','mom_3m','mom_6m'])
mo.as_of_date=mo.as_of_date.map(date);save(mo,'momentum.csv',['id'])
rm=frame('wls_rmom_inputs(1).xlsx',['id','as_of_date','mom_1m','mom_3m']);rm.as_of_date=rm.as_of_date.map(date)
rmcheck=rm.merge(mo[['id','mom_1m','mom_3m']],on='id',suffixes=('_r','_m'),validate='one_to_one')
rm_diffs={c:int((~(rmcheck[c+'_r'].eq(rmcheck[c+'_m'])|(rmcheck[c+'_r'].isna()&rmcheck[c+'_m'].isna()))).sum()) for c in ['mom_1m','mom_3m']}
save(rmcheck[~((rmcheck.mom_1m_r.eq(rmcheck.mom_1m_m)|(rmcheck.mom_1m_r.isna()&rmcheck.mom_1m_m.isna()))&(rmcheck.mom_3m_r.eq(rmcheck.mom_3m_m)|(rmcheck.mom_3m_r.isna()&rmcheck.mom_3m_m.isna())))],'momentum_conflicts.csv',['id'],folder='audit')
save(rm,'rmom_inputs.csv',['id'])
eps=frame('wls_eps(1).xlsx',['id','eps_actual_latest_quarter']);eps.insert(1,'as_of_date',ASOF);save(eps,'eps_actual.csv',['id'])
def pivot_snap(name,cols):
    df=frame(name,['id','observation_date']+cols);df.observation_date=df.observation_date.map(date)
    assert not df.duplicated(['id','observation_date']).any()
    rec=[]
    for ident,g in df.groupby('id',sort=False):
        r={'id':ident,'as_of_date':ASOF}
        for c in cols:
            good=g[g[c].notna()]
            assert len(good)<=1,(name,ident,c)
            r[c]=good[c].iloc[0] if len(good) else None
            r[c+'_date']=good.observation_date.iloc[0] if len(good) else None
        rec.append(r)
    return pd.DataFrame(rec)
er=pivot_snap('wls_eps_revisions(1).xlsx',['eps_estimate_now','eps_estimate_1m_ago','eps_estimate_3m_ago'])
save(er,'eps_estimates.csv',['id'])
ro=pivot_snap('wls_roe(1).xlsx',['roe_now_pct','roe_3m_ago_pct']);save(ro,'roe.csv',['id'])
assert rows('wls_roe(1).xlsx')==rows('Classeur7wls_roe2(1).xlsx')
le=pivot_snap('wls_leverage(1).xlsx',['debt_now','assets_now','debt_3m_ago','assets_3m_ago'])
for suffix in ['now','3m_ago']:
    le['leverage_'+suffix]=le['debt_'+suffix]/le['assets_'+suffix].where(le['assets_'+suffix].ne(0))
save(le,'leverage.csv',['id'])
breads=[]
for window,sheet in [('1m','EPS_REV_BREADTH_1M'),('3m','EPS_BREADTH_3M')]:
    b=frame('wls_eps_rev_breadth_1m_3m(1).xlsx',['id','as_of_date','eps_num_up_'+window,'eps_num_down_'+window],sheet)
    b.as_of_date=b.as_of_date.map(date)
    den=b['eps_num_up_'+window]+b['eps_num_down_'+window]
    b['revision_breadth_'+window]=(b['eps_num_up_'+window]-b['eps_num_down_'+window])/den.where(den.ne(0))
    breads.append(b)
br=breads[0].merge(breads[1],on=['id','as_of_date'],validate='one_to_one');save(br,'revision_breadth.csv',['id'])
master=u.copy()
for f in [st,mo.drop(columns=['px_last']),eps,er,ro,le,br]:
    f=f.drop(columns=['as_of_date'],errors='ignore');assert set(f.id)==set(u.id)
    master=master.merge(f,on='id',how='left',validate='one_to_one')
master.insert(1,'as_of_date',ASOF);save(master,'features_snapshot.csv',['id'])
bench=[]
for name in ['wls_benchmark_10y 1(1).xlsx','wls_benchmark_10y(1).xlsx']:
    b=frame(name,['date','px_last'],skip=1);b.date=b.date.map(date);bench.append(b)
save(bench[0],'benchmark_10y.csv',['date'])
save(bench[1],'benchmark_10y_alternative.csv',['date'],folder='supplementary')
bc=bench[0].merge(bench[1],on='date',suffixes=('_primary','_alternative'),validate='one_to_one')
diff=bc[~(bc.px_last_primary.eq(bc.px_last_alternative)|(bc.px_last_primary.isna()&bc.px_last_alternative.isna()))]
save(diff,'benchmark_conflicts.csv',['date'],folder='audit')
print('SMALL FILES DONE',len(master),'benchmark conflicts',len(diff),flush=True)

# Stream the mixed workbook without loading its millions of cells into memory.
p=src/'wls_greater_0,01 1(1).xlsx'; ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
history_stats=[];unknown=[];formulas=[];headers={};prior={};current=None;handles=[]
def val(c,ss):
    t=c.get('t');v=c.find(ns+'v');s=v.text if v is not None else None
    if t=='s':return ss[int(s)] if s is not None else None
    if t=='inlineStr':return ''.join(c.find(ns+'is').itertext())
    if t=='e':return s
    if s is None:return None
    try:return float(s) if any(a in s for a in '.eE') else int(s)
    except ValueError:return s
def colnum(ref):
    v=0
    for c in re.match('[A-Z]+',ref).group():v=v*26+ord(c)-64
    return v
with zipfile.ZipFile(p) as z:
    ss=[''.join(si.itertext()) for _,si in ET.iterparse(z.open('xl/sharedStrings.xml'),tag=ns+'si')]
    for _,r in ET.iterparse(z.open('xl/worksheets/sheet1.xml'),tag=ns+'row'):
        rn=int(r.get('r')); values={colnum(c.get('r')):val(c,ss) for c in r}
        for c in list(r):
            f=c.find(ns+'f')
            if f is not None:formulas.append({'cell':c.get('r'),'formula':f.text,'cached_value':val(c,ss)})
        if any(values.get(c) is not None for c in range(1,10)):
            unknown.append({'source_excel_row':rn,**{'col_'+chr(64+c):values.get(c) for c in range(1,10)}})
        if values.get(11)=='DATES':
            current=None
            fields=[(c,str(v)) for c,v in sorted(values.items()) if c>=12 and v is not None]
            if fields:
                field=fields[0][1];assert all(f==field for _,f in fields)
                assert all(isinstance(prior.get(c),str) and (' Equity' in prior[c] or ' Index' in prior[c]) for c,_ in fields),(rn,'missing ticker header')
                ids=[prior[c] for c,_ in fields];assert len(ids)==len(set(ids))
                window=re.search(r'range\(-(\d+Y)',field).group(1).lower()
                metric='volumes' if 'px_volume' in field else 'prices'
                label=('benchmark' if ids==['WLS Index'] else metric)+'_'+window
                key=label;version=1
                while key in headers:version+=1;key=label+'_v'+str(version)
                headers[key]=ids
                folder='data' if key in ['prices_10y','volumes_10y'] else 'supplementary'
                filename=key+'.csv.gz';hp=out/folder/filename
                handle=gzip.open(hp,'wt',encoding='utf-8',newline='');handles.append(handle);writer=csv.writer(handle);writer.writerow(['date']+ids)
                stat={'path':str(hp.relative_to(out)),'field':field,'source_header_row':rn,'rows':0,'tickers':len(ids),'missing':0,'nonpositive':0,'start_date':None,'end_date':None}
                history_stats.append(stat);current=(writer,fields,stat,hp);print('BLOCK',key,len(ids),'row',rn,flush=True)
        elif current and isinstance(values.get(11),(int,float)):
            writer,fields,stat,hp=current;d=date(values[11]);vv=[clean(values.get(c)) for c,_ in fields]
            writer.writerow([d]+vv);stat['rows']+=1;stat['missing']+=sum(v is None for v in vv)
            stat['nonpositive']+=sum(isinstance(v,(int,float)) and v<=0 for v in vv)
            if stat['start_date'] is None:stat['start_date']=d
            assert stat['end_date'] is None or d>stat['end_date'],(hp,d)
            stat['end_date']=d
        elif current:current=None
        prior=values
        r.clear()
        while r.getprevious() is not None:del r.getparent()[0]
for h in handles:h.close()
for stat in history_stats:
    hp=out/stat['path'];manifest.append({**stat,'size_bytes':hp.stat().st_size,'sha256':hashlib.sha256(hp.read_bytes()).hexdigest()})
save(pd.DataFrame(unknown),'unlabeled_columns_a_i.csv',folder='supplementary')
(out/'audit/unlabeled_formulas.json').write_text(json.dumps(formulas,indent=2,default=str))
assert set(headers['prices_10y'])==set(headers['volumes_10y'])
assert set(headers['prices_10y'])<=set(u.id)
hs=pd.DataFrame({'id':headers['prices_10y']});hs=hs.merge(u[['id','index_weight_pct']],on='id',validate='one_to_one')
save(hs,'history_universe.csv',['id'])
q=pd.DataFrame(quality);save(q,'missing_values.csv',folder='audit')
save(pd.DataFrame(mappings),'column_mapping.csv',folder='audit')
sources=[{'file':f.name,'size_bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(src.glob('*.xlsx'))]
report={'as_of_date':ASOF,'universe_tickers':len(u),'history_tickers':len(hs),'history_weight_pct':float(hs.index_weight_pct.sum()),'benchmark_conflicts':diff.to_dict('records'),'history_blocks':history_stats,'roe_duplicate_verified':True,'rmom_momentum_different_values':rm_diffs,'unlabeled_formulas_count':len(formulas),'sources':sources,'outputs':manifest}
(out/'audit/report.json').write_text(json.dumps(report,indent=2,default=str))
print('DONE',json.dumps({k:report[k] for k in ['universe_tickers','history_tickers','history_weight_pct','benchmark_conflicts','unlabeled_formulas_count']}),flush=True)
