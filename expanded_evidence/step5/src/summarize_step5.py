#!/usr/bin/env python3
"""Deterministic summaries of all D3 and complete-curve outcomes.
Selections for compact tables are structural (all six targets, original weighting,
5 km) rather than based on favorable signs. The maximal curve-harm example is
explicitly post-analysis and remains accompanied by full population summaries.
"""
import argparse,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/step4'))
from model import js,need

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();r=a.root
 need(not a.out.exists(),'Fresh out');a.out.mkdir(parents=True)
 d=pd.read_csv(r/'results/d3/paired_contrasts.csv');d=d[d.D_m>0]
 keys=['map','receiver_id','stratum','D_m','kappa','right_policy','population']
 rows=[]
 for key,g in d.groupby(keys,sort=True):
  row=dict(zip(keys,key));row.update(n=int(g.n.iloc[0]),fields=len(g))
  for q in [50,90,95]:
   v=g[f'p{q}_benefit_m'].to_numpy();row.update({f'p{q}_median_benefit_m':float(np.median(v)),f'p{q}_min_benefit_m':float(v.min()),f'p{q}_max_benefit_m':float(v.max()),f'p{q}_favorable_fields':int((v>1e-6).sum()),f'p{q}_adverse_fields':int((v< -1e-6).sum()),f'p{q}_numeric_tie_fields':int((np.abs(v)<=1e-6).sum())})
  frac=g.right_harm_n.to_numpy()/g.n.to_numpy();row.update(median_harmed_fraction=float(np.median(frac)),min_harmed_fraction=float(frac.min()),max_harmed_fraction=float(frac.max()))
  rows.append(row)
 pd.DataFrame(rows).to_csv(a.out/'D3_ALL_TARGET_SUMMARIES.csv',index=False)
 s=pd.DataFrame(rows);sel=s[(s.D_m==5000)&(s.kappa==4.7)&(s.right_policy=='unrestricted')&(s.population.isin(['full','affected']))]
 sel.to_csv(a.out/'D3_5KM_ORIGINAL_WEIGHTING.csv',index=False)
 fits=pd.read_csv(r/'results/d3/intercept_fits.csv');x=fits[fits.D_m>0];fit_summary=x.groupby(['receiver_id','stratum','D_m']).agg(fields=('delta_db','size'),min_delta_db=('delta_db','min'),median_delta_db=('delta_db','median'),max_delta_db=('delta_db','max'),negative_delta_fields=('delta_db',lambda v:int((v<0).sum())),positive_delta_fields=('delta_db',lambda v:int((v>0).sum())))
 fit_summary.to_csv(a.out/'D3_CALIBRATION_SHIFTS.csv')
 e=pd.read_csv(r/'results/exceedance/all_field_curve_summaries.csv')
 keys=['source','cell','receiver_id','stratum','D_m','kappa','population','left','right'];summary=[]
 for key,g in e.groupby(keys,sort=True):
  row=dict(zip(keys,key));row.update(fields=len(g),n=int(g.n.iloc[0]))
  for name in ['equal','crossing','right_no_worse','left_no_worse']:row[name+'_fields']=int((g.curve_order==name).sum())
  for col in ['max_benefit_fraction','max_harm_fraction','positive_area_m','negative_area_m','terminal_benefit_fraction']:
   row['median_'+col]=float(g[col].median());row['largest_'+col]=float(g[col].max());row['smallest_'+col]=float(g[col].min())
  summary.append(row)
 es=pd.DataFrame(summary);es.to_csv(a.out/'ALL_CURVE_ORDER_SUMMARIES.csv',index=False)
 hist=es[(es.source=='core')&(es.D_m==5000)&(es.kappa==4.7)&(es.population=='full')&(es.left=='frozen')&(es.right=='unrestricted')]
 hist.to_csv(a.out/'ORIGINAL_WEIGHTING_5KM_CURVE_BOUNDARIES.csv',index=False)
 refs=pd.read_csv(r/'results/d3/references_and_coverage.csv');refs[(refs.kappa==4.7)&refs.population.isin(['full','affected'])].to_csv(a.out/'D3_COVERAGE.csv',index=False)
 selection=pd.read_csv(r/'protocol/D3_TRAINING_PARTICIPATION_REGISTER.csv');selection[selection.selected].merge(refs[(refs.kappa==4.7)&(refs.population=='affected')][['receiver_id','n','removal_coverage']],on='receiver_id').to_csv(a.out/'SELECTED_TARGETS_AND_EXPOSURE.csv',index=False)
 cc=e[(e.source=='core')&(e.population=='full')&(e.left=='frozen')&(e.right=='unrestricted')&(e.D_m==5000)&(e.kappa==4.7)]
 extreme=cc.loc[cc.max_harm_fraction.idxmax()].to_dict()
 cc2=e[(e.source=='core')&(e.population=='full')&(e.left=='frozen')&(e.right=='unrestricted')]
 dd=e[(e.source=='d3')&(e.population=='full')&(e.left=='frozen')&(e.right=='unrestricted')]
 def orders(df):return {k:int(v) for k,v in df.groupby('curve_order').size().items()}
 js(a.out/'SCIENTIFIC_SUMMARY.json',{'D3_targets':[int(v) for v in json.loads((r/'protocol/D3_REGISTRY.json').read_text())['target_receivers']],'core_all_full_curve_orders':orders(cc2),'d3_all_full_curve_orders':orders(dd),'core_original_5km_full_curve_orders':orders(cc),'post_analysis_maximum_harm_example_original_weighting_5km':extreme,'example_selection':'Maximum gap across all 128 original-weighting 5km new-core fields; diagnostic selected after complete-curve analysis, not a preregistered case or typical effect.','numerical_order':'Roundoff-aligned empirical curves; not population stochastic dominance. Exact counts and gap magnitude, not just crossing frequency, must be reported.','scope':'D3 and complete real-data empirical error/availability comparison. No new synthetic/holdout/other-estimator study.','conditional_holdout':'Not run; no out-of-region or cross-deployment claim planned from this block.','literature':'Telles full journal methods remain unresolved; original thesis and bounded source-specific citations can support only inspected content; no purchase/contact/public action.'})
 print('Step5 synthesis complete',len(rows),len(summary))
if __name__=='__main__':main()
