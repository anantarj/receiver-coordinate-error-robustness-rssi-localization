#!/usr/bin/env python3
"""Locked finite/noisy synthetic WCL comparison. Full outcomes retained.
No reference literature method is claimed reproduced by these generated models.
"""
from __future__ import annotations
import argparse,csv,json,time,platform,sys
from pathlib import Path
import numpy as np
from model import need,sha,js,npz,fit,weights,centroid,policies,removal,metrics,compare_errors,check_close

def rng(li,seed,stream):return np.random.default_rng(np.random.SeedSequence([20261007,4,li,seed,stream]))
def uniform_rect(gen,n,bounds):return gen.uniform(np.array(bounds)[:,0],np.array(bounds)[:,1],(n,2))

def generated(reg,layout_name,seed):
    li=list(reg['layouts']).index(layout_name);lay=reg['layouts'][layout_name]
    cal=uniform_rect(rng(li,seed,10),reg['cal_n'],lay['cal_bounds_m']);query=uniform_rect(rng(li,seed,20),reg['eval_n'],lay['eval_bounds_m'])
    noise_cal=rng(li,seed,30).normal(size=(reg['cal_n'],6));noise_query=rng(li,seed,40).normal(size=(reg['eval_n'],6))
    th=rng(li,seed,50).uniform(0,2*np.pi,6);thc=float(rng(li,seed,60).uniform(0,2*np.pi))
    directions={'receiverwise':np.column_stack([np.cos(th),np.sin(th)]),'coherent':np.tile([np.cos(thc),np.sin(thc)],(6,1))}
    return cal,query,noise_cal,noise_query,directions

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--registry',type=Path,required=True);ap.add_argument('--lock',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    reg=json.loads(args.registry.read_text());lock=json.loads(args.lock.read_text());need(sha(args.registry)==lock['registry_sha256'],'Registry changed')
    need(not args.out.exists(),'Fresh out required');args.out.mkdir(parents=True);start=time.perf_counter()
    checks={'max_shared_prediction_difference_m':0.,'max_zero_prediction_difference_m':0.,'max_removal_identity_difference_m':0.,'max_reverse_triangle_excess_m':0.,'max_untargeted_relative_weight_difference':0.}
    files={};total=0;rows=[];comp=[];base=[];datasets=0
    def logrow(row):rows.append(row)
    for name,lay in reg['layouts'].items():
      a=np.asarray(lay['receivers_m'],float)
      for seed in reg['seeds']:
        cal,query,nc,nq,dirs=generated(reg,name,seed)
        dc=np.linalg.norm(cal[:,None,:]-a[None,:,:],axis=2);dq=np.linalg.norm(query[:,None,:]-a[None,:,:],axis=2)
        for condition in reg['propagation_conditions']:
          cn=condition['name'];ntrue=condition['n_true'];sig=condition['sigma_db'];atrue=np.array(reg['A_true_dbm'])
          rxc=atrue-10*ntrue*np.log10(dc+1)+sig*nc;rxq0=atrue-10*ntrue*np.log10(dq+1)+sig*nq
          a0=fit(rxc,cal,a,reg['n_fit'])
          if sig==0 and ntrue==reg['n_fit']:check_close(a0,atrue,'Noiseless original intercept',1e-10)
          designs=[]
          for t in reg['target_sets']:
            for pattern in reg['direction_patterns']:
              for ratio in reg['D_over_L']:designs.append({'targets':t,'pattern':pattern,'ratio':ratio,'weak_db':0.})
          if name==reg['query_support_challenge']['layout']:
            for ratio in reg['D_over_L']:designs.append({'targets':[0],'pattern':'receiverwise','ratio':ratio,'weak_db':-40.})
          nq_=len(query);nk=len(reg['kappa']);npol=len(reg['policies']);nd=len(designs)
          errors=np.empty((nd,nk,npol,nq_),float);af_all=np.empty((nd,6));inputs_id=f'{name}_{cn}_s{seed:02d}'
          basecache={}
          for di,desc in enumerate(designs):
            targets=np.array(desc['targets']);mask=np.zeros(6,bool);mask[targets]=True;U=~mask
            rxq=rxq0.copy();rxq[:,U]+=desc['weak_db'];axy=a.copy();axy[mask]+=desc['ratio']*reg['L_m']*dirs[desc['pattern']][mask]
            af=fit(rxc,cal,axy,reg['n_fit']);af_all[di]=af;check_close(af[U],a0[U],'Untargeted fits unchanged',1e-10)
            aa=policies(a0,af)
            for ki,kappa in enumerate(reg['kappa']):
              bkey=(tuple(targets),desc['weak_db'],ki)
              if bkey not in basecache:
                p0=weights(rxq,a0,kappa);pbase=centroid(p0,a);ebase=np.linalg.norm(pbase-query,axis=1)
                u,defined=removal(p0,a,np.broadcast_to(mask,p0.shape));pu=np.sum(p0[:,U],axis=1)
                basecache[bkey]=(p0,pbase,ebase,u,defined,pu)
                base.append({'dataset':inputs_id,'layout':name,'condition':cn,'seed':seed,'target_count':len(targets),'weak_db':desc['weak_db'],'kappa':kappa,'remaining_count':int(U.sum()),'mathematical_removal_defined_n':int(defined.sum()),'operational_min3_coverage':float(U.sum()>=3),'reference_p50_m':float(np.median(ebase)),'reference_p95_m':float(np.quantile(ebase,.95)),'remaining_reference_mass_p50':float(np.median(pu)),'remaining_reference_mass_min':float(pu.min())})
              p0,pbase,ebase,u,defined,pu=basecache[bkey]
              preds=[];fps=[]
              for pi,policy in enumerate(reg['policies']):
                p=weights(rxq,aa[pi],kappa);pred=centroid(p,axy);err=np.linalg.norm(pred-query,axis=1);errors[di,ki,pi]=err;preds.append(pred);fps.append(p)
                bmass=p[:,mask].sum(axis=1);record={'dataset':inputs_id,'design_index':di,'layout':name,'condition':cn,'seed':seed,'pattern':desc['pattern'],'target_count':len(targets),'remaining_count':int(U.sum()),'weak_db':desc['weak_db'],'D_over_L':desc['ratio'],'D_m':desc['ratio']*reg['L_m'],'kappa':kappa,'policy':policy,**metrics(err,ebase),'target_mass_p50':float(np.median(bmass)),'target_mass_max':float(bmass.max()),'target_delta_a_min_db':float((af-a0)[mask].min()),'target_delta_a_max_db':float((af-a0)[mask].max()),'removal_defined':bool(defined.all()),'operational_min3_coverage':float(U.sum()>=3)}
                if U.any():
                  dist=np.linalg.norm(pred-u,axis=1);vec=np.sum(p[:,mask,None]*(axy[mask][None,:,:]-u[:,None,:]),axis=1)
                  diff=check_close(pred-u,vec,'Removal finite identity');checks['max_removal_identity_difference_m']=max(checks['max_removal_identity_difference_m'],diff)
                  erem=np.linalg.norm(u-query,axis=1);excess=np.abs(err-erem)-dist;need(excess.max()<=1e-6,'Triangle bound');checks['max_reverse_triangle_excess_m']=max(checks['max_reverse_triangle_excess_m'],float(excess.max()))
                  # Non-target common offsets do not change relative non-target weights.
                  rel=p[:,U]/p[:,U].sum(axis=1,keepdims=True);rel0=p0[:,U]/p0[:,U].sum(axis=1,keepdims=True)
                  diff=check_close(rel,rel0,'Non-target relative weights',1e-12);checks['max_untargeted_relative_weight_difference']=max(checks['max_untargeted_relative_weight_difference'],diff)
                  record.update(removal_distance_p50_m=float(np.median(dist)),removal_distance_p95_m=float(np.quantile(dist,.95)),removal_distance_max_m=float(dist.max()),removal_p50_m=float(np.median(erem)),removal_p95_m=float(np.quantile(erem,.95)))
                else:record.update(removal_distance_p50_m=None,removal_distance_p95_m=None,removal_distance_max_m=None,removal_p50_m=None,removal_p95_m=None)
                logrow(record);total+=nq_
              checks['max_shared_prediction_difference_m']=max(checks['max_shared_prediction_difference_m'],check_close(preds[2],preds[0],'Shared versus frozen'))
              if desc['ratio']==0:
                for pr in preds:checks['max_zero_prediction_difference_m']=max(checks['max_zero_prediction_difference_m'],check_close(pr,pbase,'Zero-displacement baseline'))
              for pi in (1,2,3,4):
                comp.append({'dataset':inputs_id,'design_index':di,'layout':name,'condition':cn,'seed':seed,'pattern':desc['pattern'],'target_count':len(targets),'remaining_count':int(U.sum()),'weak_db':desc['weak_db'],'D_over_L':desc['ratio'],'kappa':kappa,'right_policy':reg['policies'][pi],**compare_errors(errors[di,ki,0],errors[di,ki,pi])})
          # Complete error vectors and synthetic source inputs retained. All centroids can be regenerated.
          fn=args.out/'arrays'/(inputs_id+'.npz');npz(fn,errors=errors,calibration_positions_m=cal,query_positions_m=query,calibration_rssi=rxc,query_rssi_unshifted=rxq0,reference_intercepts=a0,refitted_intercepts=af_all,receivers_m=a,coherent_directions=dirs['coherent'],receiverwise_directions=dirs['receiverwise'],kappa=reg['kappa'],design_target_mask=np.array([[i in d['targets'] for i in range(6)] for d in designs]),design_pattern=np.array([d['pattern'] for d in designs]),design_D_over_L=np.array([d['ratio'] for d in designs]),design_weak_db=np.array([d['weak_db'] for d in designs]),policies=np.array(reg['policies']))
          files[str(fn.relative_to(args.out))]=sha(fn);datasets+=1
          if datasets%12==0:print('C2 datasets',datasets,'/144; seconds',round(time.perf_counter()-start,2),flush=True)
          need(time.perf_counter()-start<reg['resource_ceiling']['seconds_per_run'],'Time budget reached; partial outputs retained, never filtered')
    def csvwrite(name,data):
      with (args.out/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    csvwrite('arm_summaries.csv',rows);csvwrite('paired_contrasts.csv',comp);csvwrite('reference_and_coverage.csv',base)
    js(args.out/'CHECKS.json',{'status':'PASS','synthetic_datasets':datasets,'arm_condition_rows':len(rows),'paired_summary_rows':len(comp),'condition_query_evaluations':total,'checks':checks,'registry_sha256':sha(args.registry),'shared_includes_duplicate_reference_checks':True,'statistical_scope':'Generated Monte Carlo designs, not physical campaigns; fields and paired arms share inputs; no p values.'})
    js(args.out/'ARRAY_MANIFEST.json',files);js(args.out/'ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()})
    js(args.out/'RUN_RECEIPT.json',{'status':'PASS','seconds':time.perf_counter()-start,'output_bytes':sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file()),'runner_sha256':sha(Path(__file__)),'model_sha256':sha(Path(__file__).with_name('model.py'))})
    need(sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())<reg['resource_ceiling']['max_output_bytes'],'Storage ceiling exceeded')
    print('C2 COMPLETE',len(rows),total,'seconds',time.perf_counter()-start,flush=True)
if __name__=='__main__':main()
