#!/usr/bin/env python3
"""Calculate all registered error-exceedance and availability comparisons.
A lossless error-vector basis and an export CLI represent every empirical curve;
all summary rows and fixed draw-0 examples are retained, not selected by sign.
"""
from __future__ import annotations
import argparse,csv,gzip,io,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'vendor/step4'))
from model import js,sha,need
from step2_raw_helpers import populations
from exceedance import curve

def write_curve(path,data,n):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('wb') as raw:
  with gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gz:
   with io.TextIOWrapper(gz,encoding='utf-8',newline='') as out:
    w=csv.writer(out);w.writerow(['threshold_m','left_exceedance_count','right_exceedance_count','benefit_count','denominator'])
    w.writerows(zip(data['threshold_m'],data['left_exceedance_count'],data['right_exceedance_count'],data['benefit_count'],np.full(len(data['threshold_m']),n)))

def describe(source,path,a):
 if source=='core':
  k=int(path.stem[-1]);mp=path.stem.rsplit('_top',1)[0]
  return {'source':source,'cell':path.stem,'map':mp,'k':k,'receiver_id':0,'stratum':'historical_targets'}
 return {'source':source,'cell':path.stem,'map':'official32_minus71','k':1,'receiver_id':int(a['target_receiver_id']),'stratum':str(a['stratum'])}

def scores(a,fi,ki,name):
 if name=='reference':return a['reference_errors'][ki]
 if name in ['removal','removal_operational']:return a['removal_errors'][ki]
 return a['errors'][fi,ki,list(a['policies']).index(name)]

def run(args):
 need(not args.out.exists(),'Fresh out required');reg=json.loads(args.registry.read_text());lock=json.loads(args.lock.read_text())
 need(sha(args.registry)==lock['registry_sha256'],'Registry modified');args.out.mkdir(parents=True)
 t=time.perf_counter();allmeta=[];examples=[];empty=[];total=0;integral_max=0.;maxadjust=0.;basis={};nfields=0
 f=(args.out/'all_field_curve_summaries.csv').open('w',newline='');writer=None
 for source,folder in [('core',args.core),('d3',args.d3)]:
  for path in sorted((folder/'arrays').glob('*.npz')):
   with np.load(path,allow_pickle=False) as z:a={k:z[k] for k in ['errors','reference_errors','removal_errors','source_rows','remaining_count','affected','kappa','policies','field_D_m','field_draw']+([] if source=='core' else ['target_receiver_id','stratum'])}
   meta=describe(source,path,a);pops=populations(a['affected'],a['remaining_count']);N=len(a['source_rows'])
   basis[f'{source}/{path.name}']={'sha256':sha(path),'source_rows_n':N,'axis':'field,kappa,policy,message','all_errors_retained':True,'array_filename':path.name}
   for fi,(D,draw) in enumerate(zip(a['field_D_m'],a['field_draw'])):
    if D<=0:continue
    nfields+=1
    for ki,kap in enumerate(a['kappa']):
     for pop,mask in pops.items():
      if pop not in reg['populations']:continue
      n=int(mask.sum())
      if not n:
       empty.append({**meta,'D_m':float(D),'draw':int(draw),'kappa':float(kap),'population':pop});continue
      for left,right in reg['comparisons']:
       l=scores(a,fi,ki,left)[mask];r=scores(a,fi,ki,right)[mask]
       la=(a['remaining_count'][mask]>=3) if left=='removal_operational' else np.ones(n,bool)
       ra=(a['remaining_count'][mask]>=3) if right=='removal_operational' else np.ones(n,bool)
       data,summary=curve(l,r,la,ra)
       row={**meta,'D_m':float(D),'draw':int(draw),'kappa':float(kap),'population':pop,'left':left,'right':right,**summary}
       if writer is None:writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader()
       writer.writerow(row);total+=1
       integral_max=max(integral_max,summary['integral_identity_residual_m'] or 0.);maxadjust=max(maxadjust,summary['max_canonicalization_m'])
       if draw==0 and pop in ['full','affected'] and (left,right) in [('frozen','unrestricted'),('unrestricted','removal_operational')]:
        name=f"{source}_{path.stem}_D{int(D)}_kappa{kap:g}_{pop}_{left}_vs_{right}.csv.gz"
        q=args.out/'draw0_curves'/name;write_curve(q,data,n);examples.append({'filename':'draw0_curves/'+name,**meta,'D_m':float(D),'draw':int(draw),'kappa':float(kap),'population':pop,'left':left,'right':right,'sha256':sha(q)})
   print('Curves complete',source,path.stem,'rows',total,'seconds',round(time.perf_counter()-t,1),flush=True)
   need(time.perf_counter()-t<reg['resource_ceiling']['seconds_per_run'],'Time ceiling; retain partial results')
 f.close();js(args.out/'CURVE_INPUTS.json',basis);js(args.out/'DRAW0_CURVE_MANIFEST.json',examples);js(args.out/'EMPTY_POPULATIONS.json',empty)
 js(args.out/'CHECKS.json',{'status':'PASS','positive_fields':nfields,'curve_comparisons':total,'complete_draw0_curves':len(examples),'maximum_integral_identity_residual_m':integral_max,'maximum_numeric_alignment_m':maxadjust,'registry_sha256':sha(args.registry),'scope':'Exact finite empirical curves over all finite thresholds, with roundoff-aligned pair ties and explicit availability. Not population-confidence inference or application pass/fail.'})
 js(args.out/'RUN_RECEIPT.json',{'seconds':time.perf_counter()-t,'runner_sha256':sha(Path(__file__)),'curve_kernel_sha256':sha(Path(__file__).with_name('exceedance.py'))})
 need(sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())<reg['resource_ceiling']['max_output_bytes'],'Storage ceiling')
 print('EXCEEDANCE COMPLETE',total,flush=True)

def main():
 ap=argparse.ArgumentParser()
 for k in ['core','d3','registry','lock','out']:ap.add_argument('--'+k,type=Path,required=True)
 a=ap.parse_args()
 try:run(a)
 except Exception as e:
  if a.out.exists():js(a.out/'FAILURE.json',{'status':'STOPPED','error_type':type(e).__name__,'error':str(e)})
  raise
if __name__=='__main__':main()
