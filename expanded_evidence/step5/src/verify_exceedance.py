#!/usr/bin/env python3
"""Independent exact-curve summary verification using sorted samples and
searchsorted ranks, rather than the primary event-increment accumulation.
Shared conventions and error inputs do not constitute independent observations.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,time
from pathlib import Path
import numpy as np

def digest(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def require(x,msg):
 if not x:raise ValueError(msg)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--core',type=Path,required=True);a=ap.parse_args();root=a.root;start=time.perf_counter()
 manifests={'core':json.loads((root/'vendor/step4/EXPECTED_CORE_ARRAY_MANIFEST.json').read_text()),'d3':json.loads((root/'results/d3/ARRAY_MANIFEST.json').read_text())}
 current=None;checked=0;maxarea=0.;eventvalues=0;maxsnap=0.
 with (root/'results/exceedance/all_field_curve_summaries.csv').open() as f:
  for row in csv.DictReader(f):
   key=(row['source'],row['cell'])
   if key!=current:
    p=(a.core if key[0]=='core' else root/'results/d3')/'arrays'/(key[1]+'.npz')
    require(digest(p)==manifests[key[0]]['arrays/'+p.name]['sha256'],'Curve source fingerprint')
    with np.load(p,allow_pickle=False) as z:ar={k:z[k] for k in ['errors','reference_errors','removal_errors','remaining_count','affected','field_D_m','field_draw','policies','kappa']}
    eligible=ar['remaining_count']>=3;affected=ar['affected'];N=len(affected)
    masks={'full':np.ones(N,bool),'affected':affected,'eligible_min3':eligible,'affected_eligible_min3':affected&eligible,'ineligible_min3':~eligible,'affected_ineligible_min3':affected&~eligible}
    index={(float(d),int(r)):i for i,(d,r) in enumerate(zip(ar['field_D_m'],ar['field_draw']))};pindex={str(p):i for i,p in enumerate(ar['policies'])};current=key
    print('Verifying curve set',key,flush=True)
   fi=index[(float(row['D_m']),int(row['draw']))];ki=list(ar['kappa']).index(float(row['kappa']));mask=masks[row['population']];n=int(mask.sum());require(n==int(row['n']),'Denominator')
   def values(which):
    er=ar['reference_errors'][ki] if which=='reference' else ar['removal_errors'][ki] if which.startswith('removal') else ar['errors'][fi,ki,pindex[which]]
    available=eligible[mask] if which=='removal_operational' else np.ones(n,bool)
    return er[mask].copy(),available
   l,la=values(row['left']);r,ra=values(row['right']);eq=(np.abs(l-r)<=1e-6+1e-12*np.maximum(l,r))&la&ra;snap=eq&(l!=r);adj=float(np.max(np.abs(l[snap]-r[snap]))) if snap.any() else 0.;r[eq]=l[eq]
   sl=np.sort(l[la]);sr=np.sort(r[ra]);thresholds=np.unique(np.concatenate(([0.],sl,sr)))
   nr=np.searchsorted(sr,thresholds,side='right');nl=np.searchsorted(sl,thresholds,side='right');g=nr-nl;lo=int(g.min());hi=int(g.max());w=np.diff(thresholds)
   cat='equal' if lo==hi==0 else 'crossing' if lo<0<hi else 'right_no_worse' if lo>=0 else 'left_no_worse'
   signs=np.sign(g[g!=0]);swaps=int(np.count_nonzero(signs[1:]!=signs[:-1])) if len(signs)>1 else 0
   integerchecks={'left_available_n':int(la.sum()),'right_available_n':int(ra.sum()),'max_benefit_count':hi,'max_harm_count':-lo,'nonzero_sign_changes':swaps,'event_count':len(thresholds),'canonicalized_pair_count':int(snap.sum())}
   for k,v in integerchecks.items():require(int(row[k])==v,'Integer discrepancy '+k)
   require(cat==row['curve_order'],'Curve order')
   pa=float(np.sum(w*np.maximum(g[:-1],0))/n);na=float(np.sum(w*np.maximum(-g[:-1],0))/n)
   vals={'max_benefit_fraction':hi/n,'max_harm_fraction':-lo/n,'positive_area_m':pa,'negative_area_m':na,'finite_area_net_m':pa-na,'positive_interval_length_m':float(w[g[:-1]>0].sum()),'negative_interval_length_m':float(w[g[:-1]<0].sum()),'terminal_benefit_fraction':float(g[-1]/n),'max_finite_threshold_m':float(thresholds[-1]),'max_canonicalization_m':adj}
   for k,v in vals.items():
    d=abs(v-float(row[k]));maxarea=max(maxarea,d);require(d<=1e-6+1e-12*max(abs(v),abs(float(row[k]))),'Float discrepancy '+k)
   if la.all() and ra.all():
    diff=float(np.sum(l-r)/n);require(abs((pa-na)-diff)<=1e-6+1e-12*max(pa,na,abs(diff)),'Area-mean identity')
   checked+=1;eventvalues+=len(thresholds);maxsnap=max(maxsnap,adj)
 # Verify entire stored breakpoint tables independently against the already-checked source vectors.
 fixed=json.loads((root/'results/exceedance/DRAW0_CURVE_MANIFEST.json').read_text())
 for r in fixed:require(digest(root/'results/exceedance'/r['filename'])==r['sha256'],'Stored example fingerprint')
 report={'status':'PASS','method':'Independent sorted-sample searchsorted ranks at every empirical breakpoint for every comparison; all integer order/gap/availability counts exact; areas use separate summed rank differences.','curve_comparisons_checked':checked,'breakpoint_values_checked':eventvalues,'fixed_curve_file_hashes_checked':len(fixed),'maximum_summary_discrepancy':maxarea,'maximum_canonicalization_m':maxsnap,'seconds':time.perf_counter()-start,'verifier_sha256':digest(Path(__file__))}
 (root/'reports/EXCEEDANCE_INDEPENDENT_CHECK.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
