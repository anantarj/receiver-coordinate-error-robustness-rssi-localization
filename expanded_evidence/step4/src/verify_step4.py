#!/usr/bin/env python3
"""Separately implemented full error-vector verifier.
Uses direct positive power weights, uncentered sums and sorted calibration medians;
it imports neither the primary scoring model nor either execution driver.
The same underlying numerical libraries remain a shared dependency.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,platform,sys,random,time
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def equal(a,b,msg,atol=1e-6):
 a=np.asarray(a);b=np.asarray(b)
 if a.shape!=b.shape or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):raise ValueError(msg+' shape/nonfinite')
 err=np.abs(a-b);mx=float(err.max()) if err.size else 0
 if np.any(err>atol+1e-12*np.maximum(np.abs(a),np.abs(b))):raise ValueError(msg+f' {mx}')
 return mx

def med(x,axis=0):
 y=np.sort(x,axis=axis);n=y.shape[axis]
 return (np.take(y,(n-1)//2,axis=axis)+np.take(y,n//2,axis=axis))/2

def pmats(a0,af):
 d=af-a0
 return [a0,af,a0+med(d),np.minimum(np.maximum(af,a0-10),a0+10),np.minimum(np.maximum(af,a0-30),a0+30)]

def c2(regpath,out):
 reg=json.loads(regpath.read_text());manifest=json.loads((out/'ARRAY_MANIFEST.json').read_text());N=0;mx=0;ai=0;input_checks=0;errc=0
 arms=pd.read_csv(out/'arm_summaries.csv');arms=arms.set_index(['dataset','design_index','kappa','policy'])
 summarymx=0.;files=sorted((out/'arrays').glob('*.npz'))
 for file in files:
  if sha(file)!=manifest[str(file.relative_to(out))]:raise ValueError('C2 manifest')
  with np.load(file,allow_pickle=False) as z:a={k:z[k] for k in z.files}
  stem=file.stem;layout=next(n for n in reg['layouts'] if stem.startswith(n+'_'));cn=next(n for n in [v['name'] for v in reg['propagation_conditions']] if ('_'+n+'_') in stem);seed=int(stem.rsplit('_s',1)[1]);li=list(reg['layouts']).index(layout);lay=reg['layouts'][layout];cond=next(v for v in reg['propagation_conditions'] if v['name']==cn)
  def randomgen(st):return np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261007,4,li,seed,st])))
  cp=randomgen(10).uniform(np.array(lay['cal_bounds_m'])[:,0],np.array(lay['cal_bounds_m'])[:,1],(400,2));qp=randomgen(20).uniform(np.array(lay['eval_bounds_m'])[:,0],np.array(lay['eval_bounds_m'])[:,1],(400,2));equal(cp,a['calibration_positions_m'],'Generated cal',1e-10);equal(qp,a['query_positions_m'],'Generated query',1e-10)
  aa=np.asarray(lay['receivers_m'],float);equal(aa,a['receivers_m'],'Layout',0.)
  dc=np.hypot(cp[:,None,0]-aa[None,:,0],cp[:,None,1]-aa[None,:,1]);dq=np.hypot(qp[:,None,0]-aa[None,:,0],qp[:,None,1]-aa[None,:,1])
  calrx=np.array(reg['A_true_dbm'])-10*cond['n_true']*np.log10(dc+1)+cond['sigma_db']*randomgen(30).standard_normal((400,6));qrx=np.array(reg['A_true_dbm'])-10*cond['n_true']*np.log10(dq+1)+cond['sigma_db']*randomgen(40).standard_normal((400,6));equal(calrx,a['calibration_rssi'],'Generated calibration noise',1e-9);equal(qrx,a['query_rssi_unshifted'],'Generated query noise',1e-9)
  theta=randomgen(50).uniform(0,2*np.pi,6);thetac=float(randomgen(60).uniform(0,2*np.pi));dirm={'receiverwise':np.column_stack([np.cos(theta),np.sin(theta)]),'coherent':np.tile([np.cos(thetac),np.sin(thetac)],(6,1))}
  equal(a['receiverwise_directions'],dirm['receiverwise'],'Direction stream',1e-12);equal(a['coherent_directions'],dirm['coherent'],'Coherent stream',1e-12)
  a0=med(calrx+47*np.log10(dc+1));ai=max(ai,equal(a0,a['reference_intercepts'],'C2 a0',1e-9));input_checks+=1
  for di in range(len(a['design_D_over_L'])):
   mask=a['design_target_mask'][di];pts=aa.copy();pattern=str(a['design_pattern'][di]);pts[mask]+=a['design_D_over_L'][di]*reg['L_m']*dirm[pattern][mask]
   dist=np.hypot(cp[:,None,0]-pts[None,:,0],cp[:,None,1]-pts[None,:,1]);af=med(calrx+47*np.log10(dist+1));ai=max(ai,equal(af,a['refitted_intercepts'][di],'C2 refit',1e-9));rx=qrx.copy();rx[:,~mask]+=a['design_weak_db'][di]
   aps=pmats(a0,af)
   for ki,kap in enumerate(a['kappa']):
    for pi,av in enumerate(aps):
     w=np.power(10.,kap*(rx-av)/(47.));s=w.sum(axis=1);pred=np.column_stack([np.sum(w*pts[None,:,d],axis=1)/s for d in (0,1)]);err=np.hypot(pred[:,0]-qp[:,0],pred[:,1]-qp[:,1]);mx=max(mx,equal(err,a['errors'][di,ki,pi],'C2 all errors'));N+=len(err);errc+=1
     row=arms.loc[(stem,di,kap,str(a['policies'][pi]))];q=np.quantile(err,[.5,.9,.95]);summarymx=max(summarymx,equal(q,row[['p50_m','p90_m','p95_m']].to_numpy(float),'C2 summary quantiles'))
  if input_checks%24==0:print('C2 verified datasets',input_checks,flush=True)
 return {'status':'PASS','datasets':len(files),'generated_input_checks':input_checks,'condition_vectors_checked':errc,'all_error_values_checked':N,'max_error_difference_m':mx,'max_intercept_difference_db':ai,'max_summary_quantile_difference_m':summarymx,'basis':'Direct power weights, uncentered centroid, sorted median, separate seed/observation generation; same NumPy dependency.'}

def real(regpath,out,csvpath):
 reg=json.loads(regpath.read_text());assert sha(csvpath)==reg['raw_csv_sha256'];f=pd.read_csv(csvpath);rxall=f[[f'BS {i}' for i in range(1,73)]].to_numpy(float);valid=np.isfinite(rxall)&(rxall>=-150)&(rxall<=-20)
 tr=Transformer.from_crs(4326,32631,always_xy=True);x,y=tr.transform(f.Longitude.to_numpy(float),f.Latitude.to_numpy(float));xy=np.column_stack([x,y]);order=np.flatnonzero(valid.sum(axis=1)>=3).tolist();random.Random(1).shuffle(order);assert len(order)==55375
 manifest=json.loads((out/'ARRAY_MANIFEST.json').read_text());arms=pd.read_csv(out/'arm_summaries.csv').set_index(['map','k','D_m','draw','kappa','policy','population']);mx=0.;wmx=0.;amx=0.;qmx=0.;rv=0;mc=0;policys=['frozen','unrestricted','shared_update','bounded10','bounded30'];count=0
 for file in sorted((out/'arrays').glob('*.npz')):
  assert sha(file)==manifest[str(file.relative_to(out))]['sha256']
  with np.load(file,allow_pickle=False) as z:a={k:z[k] for k in z.files}
  name=file.stem.rsplit('_top',1)[0];nt=int(file.stem.rsplit('_top',1)[1]);targets=[14] if nt==1 else [14,69]
  rows=a['source_rows'];cal=a['calibration_source_rows'];assert np.array_equal(cal,np.array(order[:16612]));ids=a['selected_ids'];ok=ids>=0;slot=np.maximum(ids-1,0);rx=np.where(ok,rxall[rows[:,None],slot],0.)
  roster=a['map_receiver_ids'];coord0=a['field_coordinates_m'][0];lookup={int(g):i for i,g in enumerate(roster)};idx=np.zeros_like(ids,dtype=int)
  for j in range(len(rows)):
   eligible=[g for g in roster if valid[rows[j],g-1]];eligible.sort(key=lambda g:(-rxall[rows[j],g-1],g));expected=eligible[:10]
   assert expected==list(ids[j,ok[j]])
   for sloti,g in enumerate(ids[j]):idx[j,sloti]=lookup[int(g)] if g>=0 else 0
  ac=[];buf={}
  for g in roster:
   crows=cal[valid[cal,g-1]];buf[int(g)]=(xy[crows],rxall[crows,g-1]);i=lookup[int(g)];ds=np.hypot(xy[crows,0]-coord0[i,0],xy[crows,1]-coord0[i,1]);ac.append(float(med(rxall[crows,g-1]+47*np.log10(ds+1))))
  a0=np.array(ac);amx=max(amx,equal(a0,a['reference_intercepts'],'Real independent baseline',1e-9));masks={'full':np.ones(len(rows),bool),'affected':a['affected'],'eligible_min3':a['remaining_count']>=3,'affected_eligible_min3':a['affected']&(a['remaining_count']>=3),'ineligible_min3':a['remaining_count']<3,'affected_ineligible_min3':a['affected']&(a['remaining_count']<3)};ts=np.isin(ids,targets)
  # Verify output rows and all parameter/magnitude combinations.
  for fi,(D,r) in enumerate(zip(a['field_D_m'],a['field_draw'])):
   pts=coord0.copy();af=a0.copy()
   if D>0:
    for g in targets:
     th=float(np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261007,2,int(r),g]))).uniform(0,2*np.pi));i=lookup[g];pts[i]+=D*np.array([np.cos(th),np.sin(th)]);cp,crx=buf[g];ds=np.hypot(cp[:,0]-pts[i,0],cp[:,1]-pts[i,1]);af[i]=float(med(crx+47*np.log10(ds+1)))
   equal(pts,a['field_coordinates_m'][fi],'Field generation',1e-8);amx=max(amx,equal(af,a['refitted_intercepts'][fi],'Real independent refit',1e-9));aps=pmats(a0,af);slotxy=pts[idx]
   for ki,kap in enumerate(a['kappa']):
    for pi,av in enumerate(aps):
     w=np.where(ok,np.power(10.,kap*(rx-av[idx])/47.),0.);s=w.sum(axis=1);pred=np.column_stack([np.sum(w*slotxy[:,:,d],axis=1)/s for d in (0,1)]);err=np.hypot(pred[:,0]-xy[rows,0],pred[:,1]-xy[rows,1]);bm=np.sum(np.where(ts,w,0.),axis=1)/s
     mx=max(mx,equal(err,a['errors'][fi,ki,pi],'Real all errors'));wmx=max(wmx,equal(bm,a['target_masses'][fi,ki,pi],'Real target mass',1e-12));rv+=len(rows);mc+=1
     for pn,ms in masks.items():
      if not ms.any():continue
      row=arms.loc[(name,nt,float(D),int(r),kap,policys[pi],pn)];qmx=max(qmx,equal(np.quantile(err[ms],[.5,.9,.95]),row[['p50_m','p90_m','p95_m']].to_numpy(float),'Real summary'))
  count+=1;print('Real verified cell',file.stem,flush=True)
 return {'status':'PASS','cells':count,'arm_condition_vectors_checked':mc,'all_error_values_checked':rv,'all_target_mass_values_checked':rv,'max_error_difference_m':mx,'max_target_mass_difference':wmx,'max_intercept_difference_db':amx,'max_summary_quantile_difference_m':qmx,'basis':'Independent direct-weight/uncentered/numpy-hypot scorer; sorted medians and receiver sorting; full known raw CSV, separate field generation. Shared pandas/pyproj and NumPy dependencies.'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--csv',type=Path,required=True);args=ap.parse_args();t=time.perf_counter()
 cr=c2(args.root/'protocol/C2_REGISTRY.json',args.root/'results/c2');write(args.root/'reports/C2_NUMERICAL_VERIFICATION.json',cr)
 rr=real(args.root/'protocol/REAL_CORE_REGISTRY.json',args.root/'results/real',args.csv);write(args.root/'reports/REAL_NUMERICAL_VERIFICATION.json',rr);write(args.root/'reports/INDEPENDENT_VERIFICATION_RECEIPT.json',{'status':'PASS','seconds':time.perf_counter()-t,'verifier_sha256':sha(Path(__file__)),'python':sys.version,'numpy':np.__version__});print('ALL VERIFICATION PASSED',time.perf_counter()-t)
if __name__=='__main__':main()
