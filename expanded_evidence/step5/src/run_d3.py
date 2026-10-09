#!/usr/bin/env python3
"""Run locked calibration-participation stratified target validation.
All new cases retained; minimum-three removal eligibility is reported separately.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,platform,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/step4'))
from model import need,sha,js,npz,weights,centroid,policies,removal,metrics,compare_errors,check_close
from run_real_core import load_configs
from step2_raw_helpers import populations

def writecsv(path,rows):
 need(bool(rows),'Empty '+str(path))
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def run(args):
 reg=json.loads(args.registry.read_text());lock=json.loads(args.lock.read_text())
 need(sha(args.registry)==lock['registry_sha256'],'Changed registry');need(not args.out.exists(),'Fresh output required')
 args.out.mkdir(parents=True);t=time.perf_counter()
 cfgs,consumed,bridges=load_configs(args.archive,args.csv);c=cfgs[reg['map']]
 nk=len(reg['kappa']);npoli=len(reg['policies']);N=len(c['ids'])
 need(sha(args.csv)==reg['raw_csv_sha256'] and sha(args.archive)==reg['upstream_sha256'],'Input fingerprint')
 need(npoli==5 and reg['policies']==['frozen','unrestricted','shared_update','bounded10','bounded30'],'Policy order')
 checks={'max_shared_prediction_difference_m':0.,'max_zero_prediction_difference_m':0.,'max_untouched_prediction_difference_m':0.,'max_removal_identity_difference_m':0.,'max_reverse_triangle_excess_m':0.}
 armrows=[];pairedrows=[];refrows=[];fitrows=[];manifest={};total=0;empty=[]
 for rec in reg['target_records']:
  g=rec['receiver_id'];idx=c['lookup'][g];cell=f"{reg['map']}_receiver{g}";tm=c['ids']==g;affected=tm.any(axis=1)
  remaining=c['valid'].sum(axis=1)-tm.sum(axis=1);pops=populations(affected,remaining)
  for pn,ms in pops.items():
   if not ms.any():empty.append({'cell':cell,'population':pn,'n':0,'no_substitution':True})
  fields=[(0.,-1)]+[(float(D),r) for D in reg['D_m'] if D>0 for r in reg['draws']]
  nf=len(fields);errors=np.empty((nf,nk,npoli,N));masses=np.empty_like(errors);distances=np.empty_like(errors)
  coords_all=np.empty((nf,len(c['roster']),2));af_all=np.empty((nf,len(c['roster'])))
  referrors=np.empty((nk,N));remerrors=np.empty((nk,N));pu_all=np.empty((nk,N));rempred=np.empty((nk,N,2));refs=[];predhash=hashlib.sha256()
  for ki,kap in enumerate(reg['kappa']):
   p0=weights(c['rx'],c['a0'][c['slots']],kap,valid=c['valid']);pr0=centroid(p0,c['axy'][c['slots']]);er0=np.linalg.norm(pr0-c['truth'],axis=1)
   u,defined=removal(p0,c['axy'][c['slots']],tm);need(defined.all(),'Removal undefined');eu=np.linalg.norm(u-c['truth'],axis=1);pu=np.where(~tm,p0,0).sum(axis=1)
   refs.append((p0,pr0,er0,u,eu));referrors[ki]=er0;remerrors[ki]=eu;pu_all[ki]=pu;rempred[ki]=u
   for pn,ms in pops.items():
    if not ms.any():continue
    out={'map':reg['map'],'receiver_id':g,'stratum':rec['stratum'],'calibration_receptions':rec['calibration_receptions'],'kappa':kap,'population':pn,'n':int(ms.sum()),'full_n':N,'affected_n':int(affected.sum()),'remaining_min':int(remaining[ms].min()),'remaining_max':int(remaining[ms].max()),'removal_min3_n':int((remaining[ms]>=3).sum()),'removal_coverage':float((remaining[ms]>=3).mean())}
    for name,er in [('reference',er0),('removal',eu)]:
     for q,v in zip([50,90,95],np.quantile(er[ms],[.5,.9,.95],method='linear')):out[f'{name}_p{q}_m']=float(v)
    refrows.append(out)
  for fi,(D,r) in enumerate(fields):
   xy=c['axy'].copy();af=c['a0'].copy()
   if D:
    xy[idx]+=D*np.array(reg['directions_by_draw_receiver'][str(r)][str(g)])
    cb=c['calbuf'][g];af[idx]=float(np.median(cb['rx']+47*np.log10(np.linalg.norm(cb['xy']-xy[idx],axis=1)+1)))
   coords_all[fi]=xy;af_all[fi]=af;aa=policies(c['a0'],af);slotxy=xy[c['slots']]
   fitrows.append({'map':reg['map'],'receiver_id':g,'stratum':rec['stratum'],'D_m':D,'draw':r,'calibration_n':len(c['calbuf'][g]['rx']),'reference_a0_dbm':float(c['a0'][idx]),'refitted_a0_dbm':float(af[idx]),'delta_db':float(af[idx]-c['a0'][idx])})
   for ki,kap in enumerate(reg['kappa']):
    p0,pr0,er0,u,eu=refs[ki];preds=[]
    for pi,policy in enumerate(reg['policies']):
     p=weights(c['rx'],aa[pi][c['slots']],kap,valid=c['valid']);pr=centroid(p,slotxy);er=np.linalg.norm(pr-c['truth'],axis=1);mass=np.where(tm,p,0.).sum(axis=1)
     di=np.linalg.norm(pr-u,axis=1);errors[fi,ki,pi]=er;masses[fi,ki,pi]=mass;distances[fi,ki,pi]=di;preds.append(pr);predhash.update(np.asarray(pr,dtype='<f8').tobytes())
     if (~affected).any():checks['max_untouched_prediction_difference_m']=max(checks['max_untouched_prediction_difference_m'],check_close(pr[~affected],pr0[~affected],'Untouched'))
     vec=np.sum(np.where(tm,p,0.)[:,:,None]*(slotxy-u[:,None,:]),axis=1)
     checks['max_removal_identity_difference_m']=max(checks['max_removal_identity_difference_m'],check_close(pr-u,vec,'Removal identity'))
     excess=np.abs(er-eu)-di;need(excess.max()<1e-6,'Error bound');checks['max_reverse_triangle_excess_m']=max(checks['max_reverse_triangle_excess_m'],float(excess.max()))
     for pn,ms in pops.items():
      if not ms.any():continue
      armrows.append({'map':reg['map'],'receiver_id':g,'stratum':rec['stratum'],'D_m':D,'draw':r,'kappa':kap,'policy':policy,'population':pn,**metrics(er[ms],er0[ms]),'target_mass_p50':float(np.median(mass[ms])),'target_mass_p95':float(np.quantile(mass[ms],.95)),'target_mass_max':float(mass[ms].max()),'removal_distance_p50_m':float(np.median(di[ms])),'removal_distance_p95_m':float(np.quantile(di[ms],.95)),'removal_distance_max_m':float(di[ms].max())})
     total+=N
    checks['max_shared_prediction_difference_m']=max(checks['max_shared_prediction_difference_m'],check_close(preds[2],preds[0],'Shared cancellation'))
    if not D:
     for pr in preds:checks['max_zero_prediction_difference_m']=max(checks['max_zero_prediction_difference_m'],check_close(pr,pr0,'Zero'))
    for pn,ms in pops.items():
     if not ms.any():continue
     for pi in range(1,npoli):pairedrows.append({'map':reg['map'],'receiver_id':g,'stratum':rec['stratum'],'D_m':D,'draw':r,'kappa':kap,'right_policy':reg['policies'][pi],'population':pn,'n':int(ms.sum()),**compare_errors(errors[fi,ki,0,ms],errors[fi,ki,pi,ms])})
  f=args.out/'arrays'/(cell+'.npz')
  npz(f,errors=errors,target_masses=masses,removal_distances=distances,reference_errors=referrors,removal_errors=remerrors,reference_untargeted_mass=pu_all,removal_predictions=rempred,source_rows=c['source_rows'],calibration_source_rows=c['cal_source_rows'],selected_ids=c['ids'],remaining_count=remaining,affected=affected,kappa=np.array(reg['kappa']),policies=np.array(reg['policies']),field_D_m=np.array([f[0] for f in fields]),field_draw=np.array([f[1] for f in fields]),map_receiver_ids=c['roster'],field_coordinates_m=coords_all,reference_intercepts=c['a0'],refitted_intercepts=af_all,target_receiver_id=np.array(g),stratum=np.array(rec['stratum']))
  manifest[str(f.relative_to(args.out))]={'sha256':sha(f),'prediction_stream_sha256':predhash.hexdigest(),'affected_n':int(affected.sum()),'calibration_receptions':rec['calibration_receptions']}
  print('D3 completed receiver',g,'affected',int(affected.sum()),'seconds',round(time.perf_counter()-t,2),flush=True)
  need(time.perf_counter()-t<reg['resource_ceiling']['seconds_per_run'],'Time budget; preserve partial results')
 writecsv(args.out/'arm_summaries.csv',armrows);writecsv(args.out/'paired_contrasts.csv',pairedrows);writecsv(args.out/'references_and_coverage.csv',refrows);writecsv(args.out/'intercept_fits.csv',fitrows)
 js(args.out/'ARRAY_MANIFEST.json',manifest);js(args.out/'EMPTY_POPULATIONS.json',empty)
 js(args.out/'CHECKS.json',{'status':'PASS','target_count':len(reg['target_receivers']),'positive_fields':len(reg['target_receivers'])*2*32,'arm_conditions_including_zero':total//N,'message_condition_evaluations':total,'checks':checks,'reference_bridges':bridges,'registry_sha256':sha(args.registry),'selection_rule_verified_by_lock':True,'scope':'New calibration-stratified single-target comparisons on original catalogue-map native population; not independent deployment or population-random receiver sample.'})
 js(args.out/'CONSUMED_INPUTS.json',{'csv_sha256':sha(args.csv),'archive_sha256':sha(args.archive),'archive_members':consumed})
 js(args.out/'ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()})
 js(args.out/'RUN_RECEIPT.json',{'status':'PASS','seconds':time.perf_counter()-t,'runner_sha256':sha(Path(__file__)),'bytes':sum(f.stat().st_size for f in args.out.rglob('*') if f.is_file())})
 need(sum(f.stat().st_size for f in args.out.rglob('*') if f.is_file())<reg['resource_ceiling']['max_output_bytes'],'Storage budget')
 print('D3 COMPLETE',total,'query conditions',flush=True)

def main():
 ap=argparse.ArgumentParser()
 for k in ['archive','csv','registry','lock','out']:ap.add_argument('--'+k,type=Path,required=True)
 a=ap.parse_args()
 try:run(a)
 except Exception as e:
  if a.out.exists():js(a.out/'FAILURE.json',{'status':'STOPPED','error':str(e),'error_type':type(e).__name__})
  raise
if __name__=='__main__':main()
