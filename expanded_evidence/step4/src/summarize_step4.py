#!/usr/bin/env python3
"""Complete grid summaries and all pre-existing model-pair rank comparisons.
Illustrative extracts are descriptive, selected after complete-grid examination.
No selected model or outcome is excluded from the underlying registers.
"""
from pathlib import Path
import argparse,json,itertools
import numpy as np
import pandas as pd
from model import js

def compact(group,keycols,valuecols):
 rows=[]
 for keys,g in group.groupby(keycols,sort=True,dropna=False):
  if not isinstance(keys,tuple):keys=(keys,)
  rec=dict(zip(keycols,keys));rec['fields']=len(g)
  for col in valuecols:
   v=g[col].to_numpy(float);rec[col+'_median']=float(np.median(v));rec[col+'_min']=float(v.min());rec[col+'_max']=float(v.max());rec[col+'_positive_n']=int(np.sum(v>1e-6));rec[col+'_negative_n']=int(np.sum(v< -1e-6));rec[col+'_numeric_tie_n']=int(np.sum(np.abs(v)<=1e-6))
  rows.append(rec)
 return pd.DataFrame(rows)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();r=args.root;out=r/'results/synthesis';out.mkdir(exist_ok=True)
 a=pd.read_csv(r/'results/real/arm_summaries.csv');p=pd.read_csv(r/'results/real/paired_contrasts.csv');s=pd.read_csv(r/'results/c2/paired_contrasts.csv');sa=pd.read_csv(r/'results/c2/arm_summaries.csv')
 vals=['p50_benefit_m','p90_benefit_m','p95_benefit_m'];keys=['map','k','D_m','kappa','right_policy','population']
 real=compact(p[p.D_m>0],keys,vals);real.to_csv(out/'real_paired_grid_summary.csv',index=False)
 syn=compact(s[s.D_over_L>0],['layout','condition','target_count','remaining_count','pattern','weak_db','D_over_L','kappa','right_policy'],vals);syn.to_csv(out/'synthetic_paired_grid_summary.csv',index=False)
 arm=a[a.D_m>0].groupby(['map','k','D_m','kappa','policy','population'],as_index=False)[['p50_m','p90_m','p95_m','p50_change_pct','target_mass_p50','removal_distance_p50_m','removal_distance_p95_m']].median();arm.to_csv(out/'real_arm_grid_medians.csv',index=False)
 # Exhaustively list model-pair ordering under frozen versus unrestricted calibration.
 rr=[]
 for (mapname,k,D,pop),g in a[(a.D_m>0)&a.policy.isin(['frozen','unrestricted'])].groupby(['map','k','D_m','population']):
  for metric in ['p50_m','p90_m','p95_m']:
   t=g.pivot(index='draw',columns=['kappa','policy'],values=metric)
   for ka,kb in itertools.combinations(sorted(g.kappa.unique()),2):
    f=t[(ka,'frozen')]-t[(kb,'frozen')];u=t[(ka,'unrestricted')]-t[(kb,'unrestricted')]
    for draw in t.index:
     eps=1e-6;ff=float(f.loc[draw]);uu=float(u.loc[draw]);rr.append({'map':mapname,'k':k,'D_m':D,'population':pop,'metric':metric,'kappa_a':ka,'kappa_b':kb,'draw':int(draw),'frozen_a_minus_b_m':ff,'refitted_a_minus_b_m':uu,'strict_order_reversal':bool((ff>eps and uu< -eps) or(ff< -eps and uu>eps))})
 rank=pd.DataFrame(rr);rank.to_csv(out/'all_model_pair_rankings.csv',index=False)
 rg=rank.groupby(['map','k','D_m','population','metric','kappa_a','kappa_b'],as_index=False).agg(fields=('draw','size'),reversed_fields=('strict_order_reversal','sum'),frozen_a_minus_b_median=('frozen_a_minus_b_m','median'),refitted_a_minus_b_median=('refitted_a_minus_b_m','median'));rg.to_csv(out/'ranking_reversal_summary.csv',index=False)
 fits=pd.read_csv(r/'results/real/intercept_fits.csv');fit_summary=fits.groupby('D_m',as_index=False).agg(rows=('delta_db','size'),min_shift_db=('delta_db','min'),max_shift_db=('delta_db','max'),negative_shifts=('delta_db',lambda v:int((v< -1e-9).sum())),positive_shifts=('delta_db',lambda v:int((v>1e-9).sum())));fit_summary.to_csv(out/'intercept_shift_direction_summary.csv',index=False)
 # Descriptive examples chosen from the full registered grid; no newly selected cutoff.
 table=arm[(arm.D_m==5000)&(arm.k==2)&(arm.population=='full')&(arm.kappa.isin([1.,4.7]))&(arm.policy.isin(['frozen','unrestricted','bounded10']))]
 table.to_csv(out/'illustrative_5km_two_target_policies.csv',index=False)
 tails=real[(real['map']=='recovered29')&(real.kappa==.5)&(real.D_m==5000)&(real.population=='full')&(real.right_policy=='unrestricted')]
 tails.to_csv(out/'illustrative_median_tail_reversal.csv',index=False)
 rankfocus=rg[(rg['map']=='official32_minus71')&(rg.k==2)&(rg.D_m==5000)&(rg.population=='full')&(rg.metric=='p50_m')&(rg.kappa_a==2)&(rg.kappa_b==4.7)]
 rankfocus.to_csv(out/'illustrative_weight_ranking_reversal.csv',index=False)
 js(out/'INTERPRETATION_STATUS.json',{'completed':['finite synthetic noisy/model-mismatch study','new matched real weighting/calibration/magnitude core','all model-pair ranking comparisons on fixed original native populations'],'inference':'Illustrative examples are post-analysis selections from a complete scheduled grid, not outcome-blind validations. No algorithm recommendation, significant p-value, independent deployment or automatic novelty claim.','pending':['six receiver calibration-strata validation','full empirical error-exceedance/coverage decision synthesis','optional real spatial holdout if needed by eventual claim','three journal-method comparisons and final literature distinction','integrated manuscript/supplement rewrite and later separately versioned release']})
 print('Synthesis complete',len(real),'real cells;',len(syn),'synthetic cells;',len(rank),'model pair-field comparisons')
if __name__=='__main__':main()
