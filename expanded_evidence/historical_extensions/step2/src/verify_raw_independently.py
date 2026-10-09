#!/usr/bin/env python3
"""Separate scalar raw-source verification, using pinned original WCL/fit bodies.

Does not import the new reconstruction driver. CSV parsing, scalar projection,
receiver selection, centroid calculation and quantile interpolation are separately
implemented. All original cases are checked; no new scientific field is generated.
"""
from __future__ import annotations
import argparse, ast, csv, hashlib, io, json, math, sys, time, zipfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from pyproj import Transformer
CSV_SHA='870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446'
ARC_SHA='01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268'
PREFIX='receiver-coordinate-error-robustness-rssi-localization-v1.1.0/'
ATOL=1e-6;WTOL=1e-12

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def req(ok,msg):
 if not ok:raise ValueError(msg)
def close(a,b,label,tol=ATOL):
 a=np.asarray(a);b=np.asarray(b);req(a.shape==b.shape,label+' shape');req(np.isfinite(a).all() and np.isfinite(b).all(),label+' finite')
 d=float(np.max(np.abs(a-b))) if a.size else 0.;req(d<=tol,f'{label}: {d} > {tol}');return d
def quantile(v,q):
 a=sorted(map(float,v));req(len(a)>0,'empty quantile');h=(len(a)-1)*q;l=int(math.floor(h));u=int(math.ceil(h));return a[l]+(h-l)*(a[u]-a[l])
def original_fn(text,name,env):
 ns=[n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name];req(len(ns)==1,'Function not unique')
 n=ns[0];mod=ast.fix_missing_locations(ast.Module(body=[n],type_ignores=[]));exec(compile(mod,'<immutable-original-body>','exec'),env)
 return env[name],{'name':name,'start_line':n.lineno,'end_line':n.end_lineno,'body_sha256':hashlib.sha256(ast.get_source_segment(text,n).encode()).hexdigest()}

def main(args):
 req(not args.report.exists(),'Report already exists');start=time.perf_counter();req(sha(args.csv)==CSV_SHA,'CSV hash');req(sha(args.archive)==ARC_SHA,'Archive hash')
 z=zipfile.ZipFile(args.archive);ex=PREFIX+'calibration_extension/'
 def js(p):return json.loads(z.read(ex+p))
 def nz(p):
  with np.load(io.BytesIO(z.read(ex+p)),allow_pickle=False) as a:return {k:a[k] for k in a.files}
 protocol=js('protocol/PROTOCOL.json');fields=js('protocol/DIRECTION_REGISTER.json')['cases']
 text=z.read(PREFIX+'code/baseline_001_e123_pairfallback_040926.py').decode();req(hashlib.sha256(text.encode()).hexdigest()==protocol['immutable_inputs']['harness']['sha256'],'Harness hash')
 fit,fitmeta=original_fn(text,'fit_a0',{'np':np,'math':math})
 text=z.read(PREFIX+'code/deltamesh_antwerp_eval_v10_fixed_080826.py').decode();req(hashlib.sha256(text.encode()).hexdigest()==protocol['immutable_inputs']['evaluator']['sha256'],'Evaluator hash')
 wcl,wclmeta=original_fn(text,'wcl_estimate',{'np':np})
 refs={name:nz(f'extension/{name}_reference.npz') for name in ['recovered29','official32_minus71']}
 metas={name:js(f'extension/{name}_reference.json') for name in refs}
 wanted=set(int(i) for a in refs.values() for key in ['source_rows','calibration_source_rows'] for i in a[key]);messages={};working=[];transform=Transformer.from_crs(4326,32631,always_xy=True)
 with args.csv.open(newline='') as f:
  reader=csv.DictReader(f)
  for rowid,row in enumerate(reader):
   vals=[float(row[f'BS {g}']) for g in range(1,73)]
   rec=[SimpleNamespace(gid=str(g),rssi=v) for g,v in enumerate(vals,1) if math.isfinite(v) and -150<=v<=-20]
   if len(rec)>=3:working.append(rowid)
   if rowid in wanted:
    x,y=transform.transform(float(row['Longitude']),float(row['Latitude']));req(math.isfinite(x) and math.isfinite(y),'Nonfinite scalar projection')
    rec.sort(key=lambda r:r.rssi,reverse=True);messages[rowid]=SimpleNamespace(x=x,y=y,receptions=rec)
 req(len(working)==55375 and rowid+1==130429,'Scalar CSV counts');req(set(messages)==wanted,'Requested row coverage')
 import random
 random.Random(1).shuffle(working)
 calrows=refs['recovered29']['calibration_source_rows'];req(working[:16612]==calrows.tolist(),'Scalar calibration order')
 cal=[messages[int(i)] for i in calrows];contexts={};maxp=maxe=maxw=maxa=maxrem=0.;scores={};inputcounts=[]
 for name,ref in refs.items():
  meta=metas[name];coords={g:np.asarray(xy,float) for g,xy in meta['coordinates'].items()};a0=fit(cal,coords,4.7)
  maxa=max(maxa,close([a0[g] for g in coords],[meta['intercepts'][g] for g in coords],'Canonical reference fits',1e-9))
  selected=[];truth=[];preds=[];errs=[]
  for j,rowid in enumerate(ref['source_rows']):
   m=messages[int(rowid)];rx=[r for r in m.receptions if r.gid in coords and r.gid in a0][:10]
   req([int(r.gid) for r in rx]==ref['selected_ids'][j][ref['selected_ids'][j]>=0].tolist(),'Scalar selected IDs/order')
   xy=np.array([coords[r.gid] for r in rx]);rr=np.array([r.rssi-a0[r.gid] for r in rx]);p=wcl(xy,rr)
   err=math.hypot(float(p[0]-m.x),float(p[1]-m.y));selected.append(rx);truth.append([m.x,m.y]);preds.append(p);errs.append(err)
   ww=[10.**((r.rssi-a0[r.gid])/10.) for r in rx];sw=math.fsum(ww)
   maxw=max(maxw,close([v/sw for v in ww],ref['weights'][j,:len(rx)],'Scalar weights',WTOL))
  preds=np.asarray(preds);truth=np.asarray(truth);errs=np.asarray(errs)
  maxp=max(maxp,close(preds,ref['predictions'],'Canonical baseline predictions'));maxe=max(maxe,close(errs,ref['errors'],'Canonical baseline errors'))
  contexts[name]={'coords':coords,'a0':a0,'rx':selected,'truth':truth,'reference_errors':errs,'rows':ref['source_rows']}
  scores[name+'_reference']={'errors':errs}
  print('Scalar reference passed',name,flush=True)
 removals={}
 for name,c in contexts.items():
  for k in [1,2]:
   targets={14} if k==1 else {14,69};values=[];pc=[];remaining=[];touched=[]
   for j,rx in enumerate(c['rx']):
    rr=[r for r in rx if int(r.gid) not in targets];req(len(rr)>0,'Undefined removal');remaining.append(len(rr));touched.append(len(rr)!=len(rx))
    ww=[10.**((r.rssi-c['a0'][r.gid])/10.) for r in rr];sw=math.fsum(ww)
    p=[math.fsum(w*float(c['coords'][r.gid][axis]) for r,w in zip(rr,ww))/sw for axis in (0,1)]
    pc.append(p);values.append(math.hypot(p[0]-c['truth'][j,0],p[1]-c['truth'][j,1]))
   a=np.load(args.results/'message_arrays'/f'{name}_top{k}.npz',allow_pickle=False)
   maxrem=max(maxrem,close(values,a['removal_errors'],'Scalar removal error'));req(remaining==a['remaining_count'].tolist(),'Remaining counts')
   req(touched==a['touched'].tolist(),'Touched mask');req(c['rows'].tolist()==a['source_rows'].tolist(),'Removal source rows')
   removals[name,k]={'errors':np.asarray(values),'remaining':np.asarray(remaining),'touched':np.asarray(touched)}
   inputcounts.append({'map':name,'k':k,'scores_checked':len(values),'min3_eligible':sum(x>=3 for x in remaining)})
 ncal=0;pairn=0
 for f in fields:
  name,k,r=f['map'],f['k'],f['draw'];case=f'{name}_top{k}_r{r:02d}';c=contexts[name];a=nz(f'extension/pairs/{case}.npz');meta=js(f'extension/pairs/{case}.json')
  coords={g:xy.copy() for g,xy in c['coords'].items()}
  for g,v in f['offsets'].items():coords[g]=coords[g]+np.array([v['dx_m'],v['dy_m']])
  # The original fit is separable by receiver. Refit each target and retain the
  # independently reconstructed non-target reference values, which do not change.
  targetfits=fit(cal,{g:coords[g] for g in f['offsets']},4.7);afit={**c['a0'],**targetfits}
  maxa=max(maxa,close([afit[g] for g in coords],[meta['refit_a0'][g] for g in coords],'Canonical target fits',1e-9));ncal+=len(targetfits)
  scores[case]={}
  for arm,aa in [('refit',afit),('frozen',c['a0'])]:
   ps=[];es=[]
   for j,rx in enumerate(c['rx']):
    xy=np.array([coords[t.gid] for t in rx]);rr=np.array([t.rssi-aa[t.gid] for t in rx]);p=wcl(xy,rr)
    ps.append(p);es.append(math.hypot(p[0]-c['truth'][j,0],p[1]-c['truth'][j,1]))
   ps=np.asarray(ps);es=np.asarray(es)
   maxp=max(maxp,close(ps,a[arm+'_predictions'],'Canonical pair predictions'));maxe=max(maxe,close(es,a[arm+'_errors'],'Canonical pair errors'))
   scores[case][arm]=es
   rep=np.load(args.results/'replay_arrays'/f'{name}_top{k}_{arm}.npz',allow_pickle=False)
   close(rep['predictions'][r],ps,'New driver vs canonical predictions');close(rep['errors'][r],es,'New driver vs canonical errors')
  pairn+=1
  if pairn%32==0:print('Scalar canonical pairs checked',pairn,flush=True)
 qchecks=0;qmax=0.
 with (args.results/'paired_comparator_quantiles.csv').open() as f:
  for row in csv.DictReader(f):
   name=row['map'];k=int(row['k']);r=int(row['draw']);case=row['case'];u=removals[name,k];h=u['touched'];v=u['remaining']>=3
   masks={'full':np.ones(len(h),bool),'affected':h,'eligible_min3':v,'affected_eligible_min3':h&v,'ineligible_min3':~v,'affected_ineligible_min3':h&~v};m=masks[row['population']]
   req(int(m.sum())==int(row['n']),'Quantile denominator');t=float(row['quantile'])
   vals={arm:quantile(es[m],t) for arm,es in [('reference',contexts[name]['reference_errors']),('refit',scores[case]['refit']),('frozen',scores[case]['frozen']),('removal',u['errors'])]}
   for arm,val in vals.items():qmax=max(qmax,close(val,float(row[arm+'_m']),'Manual quantile'));qchecks+=1
   for key,val in [('frozen_minus_refit_m',vals['frozen']-vals['refit']),('removal_minus_refit_m',vals['removal']-vals['refit']),('frozen_minus_removal_m',vals['frozen']-vals['removal'])]:close(val,float(row[key]),'Paired quantile difference')
 report={'status':'PASS','scope':'Separate CSV parser, scalar coordinate projection and selected-message construction, original AST-extracted fit/WCL functions; original-case numerical verification, not an independent physical dataset or novel-model validation','csv_sha256':CSV_SHA,'upstream_sha256':ARC_SHA,'original_functions':[fitmeta,wclmeta],'raw_rows_counted':130429,'working_rows_reconstructed':55375,'calibration_rows_checked':16612,'source_rows_materialized_in_memory':len(wanted),'reference_predictions_checked':4996,'original_pairs_checked':pairn,'paired_predictions_errors_checked':pairn*2*2498,'original_target_refits_checked':ncal,'removal_scores_checked':9992,'manual_quantile_cells_checked':qchecks,'max_prediction_absolute_difference_m':maxp,'max_error_absolute_difference_m':maxe,'max_reference_weight_difference':maxw,'max_intercept_difference_db':maxa,'max_removal_error_difference_m':maxrem,'max_manual_quantile_difference_m':qmax,'coverage_checks':inputcounts,'elapsed_seconds':time.perf_counter()-start,'source_sha256':sha(Path(__file__))}
 args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['archive','csv','results','report']:p.add_argument('--'+name,type=Path,required=True)
 main(p.parse_args())
