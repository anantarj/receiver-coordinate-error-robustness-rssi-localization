#!/usr/bin/env python3
"""New locked matched real-data grid for Paper B, not a replay of old fields.
Every scheduled arm receives identical observations/selection/coordinates within
its matched design. Existing coordinate references remain conditional inputs.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,time,sys,platform,random
from pathlib import Path
import numpy as np
from model import need,sha,js,npz,weights,centroid,policies,removal,metrics,compare_errors,check_close
from step2_raw_helpers import Archive,load_raw,fit_all,raw_selection,row_key,populations,MAPS,CSV_SHA,ARCHIVE_SHA

def load_configs(archive:Path,csvpath:Path):
    ar=Archive(archive);raw=load_raw(csvpath);cal=np.array(ar.js('reproduction_inputs/results/rc5/populations/calibration_ordered_source_rows.json'),int)
    need(np.array_equal(cal,np.array(raw['source_order'][:16612])),'Raw calibration identity')
    calkeys={row_key(raw,int(i)) for i in cal};cfgs={};checks=[]
    for name in MAPS:
      coords=ar.js('reproduction_inputs/maps/'+name+'.json');ref=ar.npz('extension/'+name+'_reference.npz');meta=ar.js('extension/'+name+'_reference.json');rows=ref['source_rows'].astype(int)
      roster=np.array(sorted(map(int,coords)));axy=np.array([coords[str(g)] for g in roster]);a0dict,counts=fit_all(raw,cal,coords);a0=np.array([a0dict[str(g)] for g in roster]);check_close(a0,np.array([meta['intercepts'][str(g)] for g in roster]),'Reference fits',1e-9)
      rest=np.array(raw['source_order'][16612:]);eligible=rest[raw['valid'][rest][:,roster-1].sum(axis=1)>=3].tolist();sample=random.Random(9).sample(eligible,2500);rebuilt=[r for r in sample if row_key(raw,r) not in calkeys];need(np.array_equal(rows,rebuilt),'Native population changed')
      ids,rx=raw_selection(raw,rows,a0dict,coords);need(np.array_equal(ids,ref['selected_ids']),'Selected IDs differ');valid=ids>=0
      lookup={int(g):i for i,g in enumerate(roster)};slots=np.zeros_like(ids,dtype=int)
      for g,i in lookup.items():slots[ids==g]=i
      p=weights(rx,a0[slots],4.7,valid=valid);pred=centroid(p,axy[slots]);err=np.linalg.norm(pred-raw['xy'][rows],axis=1)
      checks.append({'map':name,'source_rows_n':len(rows),'max_prediction_difference_m':check_close(pred,ref['predictions'],'Reference prediction'),'max_error_difference_m':check_close(err,ref['errors'],'Reference error'),'max_weight_difference':check_close(p,ref['weights'],'Reference weights',1e-12),'median_m':float(np.median(err))})
      calbuf={int(g):{'xy':raw['xy'][cal[raw['valid'][cal,g-1]]],'rx':raw['rssi'][cal[raw['valid'][cal,g-1]],g-1]} for g in roster}
      cfgs[name]={'roster':roster,'axy':axy,'a0':a0,'lookup':lookup,'slots':slots,'ids':ids,'valid':valid,'rx':rx,'truth':raw['xy'][rows],'source_rows':rows,'calbuf':calbuf,'cal_source_rows':cal}
    return cfgs,ar.consumed,checks

def run(args):
    reg=json.loads(args.registry.read_text());lock=json.loads(args.lock.read_text());need(sha(args.registry)==lock['registry_sha256'],'Registry changed');need(not args.out.exists(),'Fresh out required');args.out.mkdir(parents=True)
    t0=time.perf_counter();cfgs,consumed,bridges=load_configs(args.archive,args.csv)
    need(sha(args.csv)==reg['raw_csv_sha256'] and sha(args.archive)==reg['upstream_sha256'],'Input identities')
    rows=[];contr=[];base=[];fitrows=[];manifest={};nq=0;designs=0
    checks={'max_shared_prediction_difference_m':0.,'max_zero_prediction_difference_m':0.,'max_untouched_prediction_difference_m':0.,'max_removal_identity_difference_m':0.,'max_reverse_triangle_excess_m':0.}
    for name in reg['maps']:
      c=cfgs[name]
      for targets in reg['target_sets']:
        k=len(targets);cell=f'{name}_top{k}';ids=c['ids'];tm=np.isin(ids,targets);affected=tm.any(axis=1);remain=c['valid'].sum(axis=1)-tm.sum(axis=1);pop=populations(affected,remain);loc=np.array([c['lookup'][g] for g in targets]);gmask=np.zeros(len(c['roster']),bool);gmask[loc]=True
        fields=[{'D':0.,'draw':-1}]+[{'D':float(d),'draw':int(r)} for d in reg['D_m'] if d>0 for r in reg['draws']]
        nf=len(fields);ne=len(ids);errors=np.empty((nf,4,5,ne));masses=np.empty_like(errors);coords_all=np.empty((nf,len(c['roster']),2));afs=np.empty((nf,len(c['roster'])));referrors=np.empty((4,ne));remerrors=np.empty((4,ne));refmass=np.empty((4,ne));rempred=np.empty((4,ne,2));prediction_hash=hashlib.sha256()
        refs=[]
        for ki,kap in enumerate(reg['kappa']):
          p0=weights(c['rx'],c['a0'][c['slots']],kap,valid=c['valid']);pr0=centroid(p0,c['axy'][c['slots']]);er0=np.linalg.norm(pr0-c['truth'],axis=1);u,defined=removal(p0,c['axy'][c['slots']],tm);need(defined.all(),'Removal undefined in original top1/top2 core');eu=np.linalg.norm(u-c['truth'],axis=1);pu=np.where(~tm,p0,0.).sum(axis=1)
          referrors[ki]=er0;remerrors[ki]=eu;refmass[ki]=pu;rempred[ki]=u;refs.append((p0,pr0,er0,u,eu,pu))
          for pn,ms in pop.items():
            if not ms.any():continue
            record={'map':name,'k':k,'kappa':kap,'population':pn,'n':int(ms.sum()),'full_n':ne,'affected_n':int(affected.sum()),'remaining_min':int(remain[ms].min()),'remaining_max':int(remain[ms].max()),'min3_coverage':float(np.mean(remain[ms]>=3))}
            for lab,er in [('reference',er0),('removal',eu)]:
              for qt,v in zip([50,90,95],np.quantile(er[ms],[.5,.9,.95],method='linear')):record[f'{lab}_p{qt}_m']=float(v)
            base.append(record)
        for fi,f in enumerate(fields):
          axy=c['axy'].copy();af=c['a0'].copy()
          if f['D']>0:
            for g,i in zip(targets,loc):
              axy[i]+=f['D']*np.array(reg['directions_by_draw_receiver'][str(f['draw'])][str(g)])
              cb=c['calbuf'][g];ds=np.linalg.norm(cb['xy']-axy[i],axis=1);af[i]=float(np.median(cb['rx']+47.*np.log10(ds+1)))
          afs[fi]=af;coords_all[fi]=axy;aa=policies(c['a0'],af);need(np.array_equal(af[~gmask],c['a0'][~gmask]),'Untargeted intercept mutation')
          for g,i in zip(targets,loc):fitrows.append({'cell':cell,'D_m':f['D'],'draw':f['draw'],'receiver_id':g,'calibration_n':len(c['calbuf'][g]['rx']),'reference_a0_dbm':float(c['a0'][i]),'unrestricted_a0_dbm':float(af[i]),'delta_db':float(af[i]-c['a0'][i])})
          slotxy=axy[c['slots']]
          for ki,kap in enumerate(reg['kappa']):
            p0,pr0,er0,u,eu,pu=refs[ki];preds=[]
            for pi,policy in enumerate(reg['policies']):
              p=weights(c['rx'],aa[pi][c['slots']],kap,valid=c['valid']);pred=centroid(p,slotxy);err=np.linalg.norm(pred-c['truth'],axis=1);bmass=np.where(tm,p,0.).sum(axis=1);errors[fi,ki,pi]=err;masses[fi,ki,pi]=bmass;preds.append(pred);prediction_hash.update(np.asarray(pred,dtype='<f8').tobytes())
              if (~affected).any():checks['max_untouched_prediction_difference_m']=max(checks['max_untouched_prediction_difference_m'],check_close(pred[~affected],pr0[~affected],'Untouched prediction'))
              vec=np.sum(np.where(tm,p,0.)[:,:,None]*(slotxy-u[:,None,:]),axis=1);checks['max_removal_identity_difference_m']=max(checks['max_removal_identity_difference_m'],check_close(pred-u,vec,'Real removal identity'))
              dist=np.linalg.norm(pred-u,axis=1);excess=np.abs(err-eu)-dist;need(excess.max()<1e-6,'Reverse triangle');checks['max_reverse_triangle_excess_m']=max(checks['max_reverse_triangle_excess_m'],float(excess.max()))
              for pn,ms in pop.items():
                if not ms.any():continue
                rec={'map':name,'k':k,'D_m':f['D'],'draw':f['draw'],'kappa':kap,'policy':policy,'population':pn,**metrics(err[ms],er0[ms]),'target_mass_p50':float(np.median(bmass[ms])),'target_mass_p95':float(np.quantile(bmass[ms],.95)),'target_mass_max':float(bmass[ms].max()),'removal_distance_p50_m':float(np.median(dist[ms])),'removal_distance_p95_m':float(np.quantile(dist[ms],.95)),'removal_distance_max_m':float(dist[ms].max())}
                rows.append(rec)
              nq+=ne
            checks['max_shared_prediction_difference_m']=max(checks['max_shared_prediction_difference_m'],check_close(preds[2],preds[0],'Shared prediction cancellation'))
            if f['D']==0:
              for pred in preds:checks['max_zero_prediction_difference_m']=max(checks['max_zero_prediction_difference_m'],check_close(pred,pr0,'Zero real condition'))
            for pn,ms in pop.items():
              if not ms.any():continue
              for pi in [1,2,3,4]:contr.append({'map':name,'k':k,'D_m':f['D'],'draw':f['draw'],'kappa':kap,'right_policy':reg['policies'][pi],'population':pn,'n':int(ms.sum()),**compare_errors(errors[fi,ki,0,ms],errors[fi,ki,pi,ms])})
          designs+=1
        fn=args.out/'arrays'/(cell+'.npz');npz(fn,errors=errors,target_masses=masses,reference_errors=referrors,removal_errors=remerrors,reference_untargeted_mass=refmass,removal_predictions=rempred,source_rows=c['source_rows'],calibration_source_rows=c['cal_source_rows'],selected_ids=c['ids'],remaining_count=remain,affected=affected,kappa=np.array(reg['kappa']),policies=np.array(reg['policies']),field_D_m=np.array([f['D'] for f in fields]),field_draw=np.array([f['draw'] for f in fields]),map_receiver_ids=c['roster'],field_coordinates_m=coords_all,reference_intercepts=c['a0'],refitted_intercepts=afs)
        manifest[str(fn.relative_to(args.out))]={'sha256':sha(fn),'prediction_stream_sha256':prediction_hash.hexdigest(),'prediction_stream_order':'field index, kappa index, policy index, message source-row order, easting/northing little-endian float64','all_errors_and_target_masses_retained':True}
        print('Real core completed',cell, 'seconds',round(time.perf_counter()-t0,2),flush=True)
        need(time.perf_counter()-t0<reg['resource_ceiling']['seconds_per_run'],'Resource ceiling reached; preserve partial outcomes')
    def csvwrite(name,data):
      with (args.out/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    csvwrite('arm_summaries.csv',rows);csvwrite('paired_contrasts.csv',contr);csvwrite('references_and_coverage.csv',base);csvwrite('intercept_fits.csv',fitrows)
    js(args.out/'CHECKS.json',{'status':'PASS','geometry_field_designs':designs,'positive_geometry_designs':designs-4,'arm_condition_evaluations':nq//2498,'message_condition_evaluations':nq,'checks':checks,'reference_bridges':bridges,'registry_sha256':sha(args.registry),'scope':'New calibration/weighting/magnitude fields on original two native populations; not physical map validation, independent campaign, spatial holdout, or other-estimator test.'})
    js(args.out/'ARRAY_MANIFEST.json',manifest);js(args.out/'CONSUMED_INPUTS.json',{'csv_sha256':sha(args.csv),'archive_sha256':sha(args.archive),'archive_members':consumed,'helper_sha256':sha(Path(__file__).with_name('step2_raw_helpers.py'))});js(args.out/'ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()})
    js(args.out/'RUN_RECEIPT.json',{'status':'PASS','seconds':time.perf_counter()-t0,'output_bytes':sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file()),'runner_sha256':sha(Path(__file__)),'model_sha256':sha(Path(__file__).with_name('model.py'))})
    need(sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())<reg['resource_ceiling']['max_output_bytes'],'Storage ceiling exceeded')
    print('REAL CORE COMPLETE',len(rows),'summary rows',nq,'message conditions',round(time.perf_counter()-t0,2),'seconds',flush=True)

def main():
    ap=argparse.ArgumentParser()
    for k in ['archive','csv','registry','lock','out']:ap.add_argument('--'+k,type=Path,required=True)
    args=ap.parse_args()
    try:run(args)
    except Exception as e:
      if args.out.exists():js(args.out/'FAILURE.json',{'status':'STOPPED','error_type':type(e).__name__,'error':str(e)})
      raise
if __name__=='__main__':main()
