#!/usr/bin/env python3
"""Read-only rederivation of RC5 reports from supplied raw outputs; no localization."""
from pathlib import Path
import hashlib,io,json,zipfile
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1]
def main():
 t=pd.read_csv(R/'results/rc5/retained_case_medians.csv');count=0;arrays=0
 arc=R/'results/archives/PAPERB_B9C_REMAINING_AUTHOR_RUN_050926.zip';z=zipfile.ZipFile(arc) if arc.exists() else None
 try:
  for member,rows in t.groupby('member',sort=False):
   data=z.read(member) if z else (R/'author_remaining'/Path(member).relative_to('PAPERB_B9C_REMAINING_AUTHOR_RUN_050926')).read_bytes()
   assert hashlib.sha256(data).hexdigest()==rows.raw_sha256.iloc[0],member
   with np.load(io.BytesIO(data),allow_pickle=False) as x:
    e=x['error_m'];methods=x['methods'].tolist();assert np.isfinite(e).all() and (e>=0).all();assert e.shape==(int(rows.N.iloc[0]),4)
    for _,v in rows.iterrows():
     med=float(np.median(e[:,methods.index(v['method'])]));assert abs(med-v.median_error_m)<1e-7,(member,v['method']);count+=1
   arrays+=1
 finally:
  if z:z.close()
 # Forty reported configurations: rederive each median and effect from its raw array.
 root=R/'results/rc5/matched_exposure';q=pd.read_csv(root/'subset_results.csv');ref=np.load(root/'raw/reference.npz',allow_pickle=False);baseline=np.median(ref['error_m'],axis=0);methods=ref['methods'].tolist()
 for case,rows in q.groupby('case_id',sort=False):
  p=root/'raw'/f'{case}.npz';assert hashlib.sha256(p.read_bytes()).hexdigest()==rows.raw_sha256.iloc[0]
  with np.load(p,allow_pickle=False) as d:
   assert np.array_equal(d['source_row'],ref['source_row']);v=np.median(d['error_m'],axis=0)
   for _,row in rows.iterrows():
    j=methods.index(row['method']);assert abs(v[j]-row.median_error_m)<1e-7;assert abs(100*(v[j]-baseline[j])/baseline[j]-row.change_pct)<1e-7
 old=pd.read_csv(R/'results/figure_data/paperb_matched_exposure.csv');agg=0
 for _,row in old.iterrows():
  g=q[q.bin_center==row.S_bin]
  for name,label in zip(methods,['WCL','ABS','DIFF','MinMax']):
   v=g[g.method==name].change_pct.to_numpy();assert len(v)==8;assert f'{np.median(v):.1f}'==f'{row[label+"_med_pct"]:.1f}';agg+=1
   if name=='WCL':
    assert f'{v.min():.1f}'==f'{row.WCL_min_pct:.1f}';assert f'{v.max():.1f}'==f'{row.WCL_max_pct:.1f}';agg+=2
 assert arrays==442 and count==1768 and agg==30
 print(json.dumps({'status':'PASS','author_arrays_rederived':arrays,'method_medians_checked':count,'same_design_configurations_checked':40,'published_aggregate_fields_checked':agg,'new_localization_run':False},indent=2))
if __name__=='__main__':main()
