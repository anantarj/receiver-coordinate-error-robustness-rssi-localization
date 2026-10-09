#!/usr/bin/env python3
"""Separate numerical implementation for D3.
Uses Python CSV reading, scalar coordinate projection, explicit RSSI sorting,
sorted-median fitting, direct positive-power weights and uncentered centroids.
Does not import run_d3, the new/parent scoring model, or load_configs.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,sys,time,zipfile
from pathlib import Path
import numpy as np
from pyproj import Transformer
ROOT='receiver-coordinate-error-robustness-rssi-localization-v1.1.0/calibration_extension/'
CSV_SHA='870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446'
ZIP_SHA='01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268'

def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def require(x,m):
 if not x:raise ValueError(m)
def close(a,b,m,atol=1e-6,rtol=1e-12):
 a=np.asarray(a);b=np.asarray(b);require(a.shape==b.shape,m+' shape')
 require(np.isfinite(a).all() and np.isfinite(b).all(),m+' finite')
 d=np.abs(a-b);v=float(d.max()) if d.size else 0.;require(np.all(d<=atol+rtol*np.maximum(np.abs(a),np.abs(b))),m+str(v));return v

def med(a):
 s=np.sort(np.asarray(a),axis=0);n=len(s)
 return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2

def quantiles(e):
 s=np.sort(e);out=[]
 for q in [.5,.9,.95]:
  p=(len(s)-1)*q;i=math.floor(p);j=math.ceil(p);out.append(float(s[i]+(s[j]-s[i])*(p-i)))
 return out

def main():
 ap=argparse.ArgumentParser()
 for k in ['csv','archive','root']:ap.add_argument('--'+k,type=Path,required=True)
 a=ap.parse_args();root=a.root;t=time.perf_counter();reg=json.loads((root/'protocol/D3_REGISTRY.json').read_text());lock=json.loads((root/'protocol/D3_LOCK.json').read_text())
 require(sha(root/'protocol/D3_REGISTRY.json')==lock['registry_sha256'],'Registry hash')
 require(sha(a.csv)==CSV_SHA and sha(a.archive)==ZIP_SHA,'Input hashes')
 with zipfile.ZipFile(a.archive) as z:
  coords=json.loads(z.read(ROOT+'reproduction_inputs/maps/official32_minus71.json'))
  cal=np.array(json.loads(z.read(ROOT+'reproduction_inputs/results/rc5/populations/calibration_ordered_source_rows.json')),int)
  with np.load(io.BytesIO(z.read(ROOT+'extension/official32_minus71_reference.npz')),allow_pickle=False) as r:
   evalrows=r['source_rows'].copy();saved_ids=r['selected_ids'].copy()
 wanted=set(map(int,np.concatenate([cal,evalrows])));store={};proj=Transformer.from_crs('EPSG:4326','EPSG:32631',always_xy=True)
 with a.csv.open(newline='') as f:
  reader=csv.DictReader(f)
  for i,row in enumerate(reader):
   if i not in wanted:continue
   rx=np.array([float(row[f'BS {g}']) for g in range(1,73)])
   store[i]=(rx,np.array(proj.transform(float(row['Longitude']),float(row['Latitude']))))
 require(len(store)==len(wanted),'Missing source rows')
 calrx=np.array([store[int(i)][0] for i in cal]);calxy=np.array([store[int(i)][1] for i in cal]);truth=np.array([store[int(i)][1] for i in evalrows]);erx=np.array([store[int(i)][0] for i in evalrows])
 roster=sorted(map(int,coords));axy=np.array([coords[str(g)] for g in roster]);look={g:i for i,g in enumerate(roster)}
 validcal=np.isfinite(calrx)&(calrx>=-150)&(calrx<=-20);counts={g:int(validcal[:,g-1].sum()) for g in roster}
 order=sorted([g for g in roster if counts[g]>=10],key=lambda g:(-counts[g],g));groups=np.array_split(order,3);chosen=[]
 for group in groups:
  m=len(group);idx=[(m-1)//3,2*(m-1)//3]
  if len(set(idx))<2:idx=[0,m-1]
  chosen.extend(int(group[i]) for i in idx)
 require(chosen==reg['target_receivers'],'Calibration-only selection disagreement')
 selected=np.full((len(evalrows),10),-1,np.int16);rx=np.zeros((len(evalrows),10));slots=np.zeros_like(selected,int)
 for j,rr in enumerate(erx):
  gs=sorted([g for g in roster if np.isfinite(rr[g-1]) and -150<=rr[g-1]<=-20],key=lambda g:(-rr[g-1],g))[:10]
  for s,g in enumerate(gs):selected[j,s]=g;rx[j,s]=rr[g-1];slots[j,s]=look[g]
 require(np.array_equal(selected,saved_ids),'Receiver selection mismatch');valid=selected>=0
 calbuf={g:(calxy[validcal[:,g-1]],calrx[validcal[:,g-1],g-1]) for g in roster}
 a0=np.array([float(med(calbuf[g][1]+47*np.log10(np.hypot(*(calbuf[g][0]-axy[look[g]]).T)+1))) for g in roster])
 maxima={'error_m':0.,'target_mass':0.,'removal_distance_m':0.,'fit_db':0.,'arm_quantile_m':0.};checks=0;qchecks=0;remchecks=0;registry_index={r['receiver_id']:r for r in reg['target_records']}
 tables={}
 with (root/'results/d3/arm_summaries.csv').open() as f:
  for r in csv.DictReader(f):tables[(int(r['receiver_id']),float(r['D_m']),int(r['draw']),float(r['kappa']),r['policy'],r['population'])]=r
 def calc(xy,aa,kap):
  w=np.where(valid,10.**(kap*(rx-aa[slots])/47.),0.)
  require(np.isfinite(w).all() and (w[valid]>0).all(),'Bad direct weights')
  p=w/w.sum(axis=1)[:,None];pred=np.sum(p[:,:,None]*xy[slots],axis=1)
  return pred,p,np.hypot(*(pred-truth).T)
 for g in chosen:
  file=root/'results/d3/arrays'/f'official32_minus71_receiver{g}.npz'
  with np.load(file,allow_pickle=False) as zz:z={k:zz[k] for k in zz.files}
  require(np.array_equal(z['source_rows'],evalrows) and np.array_equal(z['selected_ids'],selected),'Array identity')
  tm=selected==g;hit=tm.any(axis=1);remain=valid.sum(axis=1)-tm.sum(axis=1);elig=remain>=3
  require(np.array_equal(hit,z['affected']) and np.array_equal(remain,z['remaining_count']),'Masks')
  pops={'full':np.ones(len(evalrows),bool),'affected':hit,'eligible_min3':elig,'affected_eligible_min3':hit&elig,'ineligible_min3':~elig,'affected_ineligible_min3':hit&~elig}
  maxima['fit_db']=max(maxima['fit_db'],close(a0,z['reference_intercepts'],'Reference fit',1e-9))
  refs=[]
  for ki,kap in enumerate(reg['kappa']):
   pr,p,er=calc(axy,a0,kap);pp=np.where(tm,0,p);pu=pp.sum(axis=1);u=np.sum(pp[:,:,None]*axy[slots],axis=1)/pu[:,None];eu=np.hypot(*(u-truth).T)
   close(er,z['reference_errors'][ki],'Reference error');close(eu,z['removal_errors'][ki],'Removal error');close(u,z['removal_predictions'][ki],'Removal position')
   refs.append(u);remchecks+=len(eu)
  for fi,(D,draw) in enumerate(zip(z['field_D_m'],z['field_draw'])):
   xy=axy.copy();af=a0.copy()
   if D:
    vector=reg['directions_by_draw_receiver'][str(int(draw))][str(g)];xy[look[g]]+=D*np.array(vector)
    cx,cr=calbuf[g];af[look[g]]=float(med(cr+47*np.log10(np.hypot(*(cx-xy[look[g]]).T)+1)))
   close(xy,z['field_coordinates_m'][fi],'Field coordinates');maxima['fit_db']=max(maxima['fit_db'],close(af,z['refitted_intercepts'][fi],'Refit',1e-9))
   delta=af-a0;aa=[a0,af,a0+med(delta),a0+np.minimum(10,np.maximum(-10,delta)),a0+np.minimum(30,np.maximum(-30,delta))]
   for ki,kap in enumerate(reg['kappa']):
    for pi,policy in enumerate(reg['policies']):
     pr,p,er=calc(xy,aa[pi],kap);bm=np.sum(p*tm,axis=1);di=np.hypot(*(pr-refs[ki]).T)
     maxima['error_m']=max(maxima['error_m'],close(er,z['errors'][fi,ki,pi],'Error'))
     maxima['target_mass']=max(maxima['target_mass'],close(bm,z['target_masses'][fi,ki,pi],'Mass',1e-12))
     maxima['removal_distance_m']=max(maxima['removal_distance_m'],close(di,z['removal_distances'][fi,ki,pi],'Removal distance'));checks+=len(er)
     for pn,mask in pops.items():
      if not mask.any():continue
      row=tables[(g,float(D),int(draw),float(kap),policy,pn)]
      maxima['arm_quantile_m']=max(maxima['arm_quantile_m'],close(quantiles(er[mask]),[float(row[x]) for x in ['p50_m','p90_m','p95_m']],'Quantiles'));qchecks+=3
  print('Verified D3 receiver',g,flush=True)
 report={'status':'PASS','method':'Separate CSV parser, scalar projection, Python receiver sorting, sorted-median refits, direct powers and uncentered centroid sums; no primary D3 scoring import. NumPy and pyproj libraries and input data remain shared.','selected_receivers':chosen,'error_values_checked':checks,'mass_values_checked':checks,'removal_distance_values_checked':checks,'removal_scores_checked':remchecks,'arm_quantiles_checked':qchecks,'maximum_discrepancies':maxima,'seconds':time.perf_counter()-t,'verifier_sha256':sha(Path(__file__))}
 (root/'reports/D3_INDEPENDENT_NUMERICAL_CHECK.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
