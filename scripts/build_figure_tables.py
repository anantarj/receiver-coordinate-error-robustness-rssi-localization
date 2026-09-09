#!/usr/bin/env python3
"""Parse figure inputs from preserved run logs; never execute localization or impute results."""
from pathlib import Path
import re, json, hashlib, csv
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
LOGS=ROOT/'results/base_logs'; OUT=ROOT/'results/figure_data'
METHODS=['WCL','ABS','DIFF','Min-Max']
NUM=r'[-+]?\d+(?:\.\d+)?'
def lines(name):return (LOGS/name).read_text(encoding='utf-8').splitlines()
def source(name,no):return {'source_file':'results/base_logs/'+name,'source_line':no}
def save(name,rows,expected):
    if len(rows)!=expected:raise ValueError(f'{name}: parsed {len(rows)} != expected {expected}')
    df=pd.DataFrame(rows);df.to_csv(OUT/name,index=False);return df

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 load=[]
 for d,name in [(250,'diffrepair_e1_d250.txt'),(500,'diffrepair_e1_d500_dr32.txt'),(1000,'diffrepair_e1_d1000.txt'),(2500,'diffrepair_e1_d2500.txt'),(10000,'diffrepair_e1_d10000.txt')]:
  for no,line in enumerate(lines(name),1):
   m=re.match(r'^\s*(\d+)\s+(\d+)%\s+(.*)',line)
   if not m:continue
   pairs=re.findall(r'(\d+(?:\.\d+)?)m\s+('+NUM+r')%',m[3])
   if len(pairs)!=4:continue
   for method,(meters,pct) in zip(METHODS,pairs):load.append(dict(D_m=d,f=int(m[1]),fraction_pct_reported=int(m[2]),fraction_pct_exact=100*int(m[1])/29,method=method,median_m=float(meters),effect_pct=float(pct),draws=32 if d==500 else 8,**source(name,no)))
 save('paperb_load_surface.csv',load,120)
 exposure=[];matched=[];name='diffrepair_e2b_k14_dir8.txt'
 for no,line in enumerate(lines(name),1):
  m=re.match(r'^\s*(\d+)(top|bottom|random)\s+('+NUM+r')\s+(.*)',line)
  if m:
   pairs=re.findall(r'(\d+)m\s+('+NUM+r')%',m[4])
   if len(pairs)!=4:raise ValueError('exposure parse')
   for method,(meters,pct) in zip(METHODS,pairs):exposure.append(dict(k=int(m[1]),arm=m[2],selection_share=float(m[3]),method=method,median_m=float(meters),effect_pct=float(pct),draws=8,**source(name,no)))
  m=re.match(r'^\s*(0\.\d+)\s+(\d+)\s+(\d+)-(\d+)\s+('+NUM+r')%\s+('+NUM+r')-('+NUM+r')\s+('+NUM+r')%\s+('+NUM+r')%\s+('+NUM+r')%',line)
  if m:matched.append(dict(S_bin=float(m[1]),n_subsets=int(m[2]),k_min=int(m[3]),k_max=int(m[4]),WCL_med_pct=float(m[5]),WCL_min_pct=float(m[6]),WCL_max_pct=float(m[7]),ABS_med_pct=float(m[8]),DIFF_med_pct=float(m[9]),MinMax_med_pct=float(m[10]),**source(name,no)))
 save('paperb_exposure_5km_w10.csv',exposure,168);save('paperb_matched_exposure.csv',matched,5)
 ablation=[];name='e2f_a0truth.txt';inblock=False
 for no,line in enumerate(lines(name),1):
  if '(8) A0-FROM-TRUTH' in line:inblock=True
  if inblock:
   m=re.match(r'^\s*(\d+)\s+('+NUM+r')%\s+('+NUM+r')%\s*$',line)
   if m:ablation.append(dict(k=int(m[1]),refit_pct=float(m[2]),frozen_pct=float(m[3]),**source(name,no)))
 save('paperb_a0_ablation.csv',ablation,4)
 spatial=[];angle=[];name='diffrepair_e3b_angles.txt';currentD=None
 for no,line in enumerate(lines(name),1):
  m=re.match(r'^\s*(\d+)m(iso x8 med|iso|coherent|inward|outward)\s+(.*)',line)
  if m:
   pairs=re.findall(r'(\d+)m\s+('+NUM+r')%',m[3])
   if len(pairs)==4:
    for method,(meters,pct) in zip(METHODS,pairs):spatial.append(dict(D_m=int(m[1]),family=m[2],method=method,median_m=float(meters),effect_pct=float(pct),draws=8 if m[2]=='iso x8 med' else 1,**source(name,no)))
  m=re.search(r'D = (\d+) m:\s+angle',line)
  if m:currentD=int(m[1])
  m=re.match(r'^\s*(\d+)°\s+(.*)',line)
  if m and currentD:
   pairs=re.findall(r'(\d+)m\s+('+NUM+r')%',m[2])
   if len(pairs)==4:
    for method,(meters,pct) in zip(METHODS,pairs):angle.append(dict(D_m=currentD,angle_deg=int(m[1]),method=method,median_m=float(meters),effect_pct=float(pct),**source(name,no)))
 save('paperb_spatial_families.csv',spatial,120);save('paperb_coherent_angles.csv',angle,144)
 affine=[];cluster=[];name='diffrepair_e5_affine.txt';last=None
 for no,line in enumerate(lines(name),1):
  m=re.match(r'^\s*(rot|scale)\s+('+NUM+r')°?\s+\(med\s+(\d+)m\)\s+(.*)',line)
  if m:
   pairs=re.findall(r'(\d+)m\s+('+NUM+r')%',m[4]);last=[]
   for method,(meters,pct) in zip(METHODS,pairs):
    row=dict(transform=m[1],parameter=float(m[2]),displacement_m=float(m[3]),method=method,median_m=float(meters),effect_pct=float(pct),matched_WCL_pct=None,comparison_draws=4,**source(name,no));affine.append(row);last.append(row)
  m=re.search(r'matched-iso @\d+m: WCL \d+m \(('+NUM+r')%, range (\d+)-(\d+)\)',line)
  if m and last:
   for row in last:row['matched_WCL_pct']=float(m[1]);row['matched_WCL_lo_m']=float(m[2]);row['matched_WCL_hi_m']=float(m[3]);row['matched_source_line']=no
  m=re.search(r'm=(\d+): clustered WCL (\d+) m \(('+NUM+r')%, range (\d+)-(\d+), (\d+) draws\) vs random-\d+ (\d+) m \(('+NUM+r')%, range (\d+)-(\d+), (\d+) draws\)',line)
  if m:cluster.append(dict(m=int(m[1]),clustered_m=float(m[2]),clustered_pct=float(m[3]),clustered_lo_m=float(m[4]),clustered_hi_m=float(m[5]),draws=int(m[6]),random_m=float(m[7]),random_pct=float(m[8]),random_lo_m=float(m[9]),random_hi_m=float(m[10]),**source(name,no)))
 save('paperb_affine.csv',affine,32);save('paperb_clustered.csv',cluster,2)
 mixed=[];name='diffrepair_e6_twopop.txt'
 for no,line in enumerate(lines(name),1):
  m=re.match(r'^\s*(\d+)\s+('+NUM+r')%\s+('+NUM+r')%\s+('+NUM+r')\s+gaps: ABS ('+NUM+r') DIFF ('+NUM+r') MinMax ('+NUM+r')',line)
  if m:mixed.append(dict(k=int(m[1]),two_pop_WCL_pct=float(m[2]),pure_WCL_pct=float(m[3]),WCL_gap_pp=float(m[4]),ABS_gap_pp=float(m[5]),DIFF_gap_pp=float(m[6]),MinMax_gap_pp=float(m[7]),draws=4,**source(name,no)))
 save('paperb_twopop.csv',mixed,4)
 tails=[];name='e7_tails.txt'
 for no,line in enumerate(lines(name),1):
  m=re.match(r'^\s*(reference|f=24% @D|f=100% @D|top-6 @D|top-7 @D)\s+(\d+)m\s+(\d+)m\s+(\d+)m\s+(\d+)m\s+(\d+)\s*$',line)
  if m:tails.append(dict(condition=m[1],P50_m=int(m[2]),P75_m=int(m[3]),P90_m=int(m[4]),P95_m=int(m[5]),pooled_evaluations=int(m[6]),unique_messages=2498,**source(name,no)))
 save('paperb_tails.csv',tails,5)
 coverage=pd.read_csv(ROOT/'results/b9c_summary/paperb_coverage.csv');coverage.to_csv(OUT/'paperb_coverage.csv',index=False)
 # Preserve complete stable-rank tables under both manuscript-facing names.
 for suffix in ['w10','w5']:
  name='paperb_exposure_rank_stability_'+suffix+'.txt';t=(ROOT/'results/b9c_summary'/name).read_text().splitlines();rows=[]
  for no,line in enumerate(t,1):
   if ' vs ' in line:
    p=line.split(',');rows.append(dict(comparison=p[0],spearman=float(p[1]),top7_overlap=p[2],jaccard=float(p[3]),source_file='results/b9c_summary/'+name,source_line=no))
  save('paperb_rank_stability_'+suffix+'.csv',rows,6)
 # Explicitly document mixed replication, rounded source precision and older log semantics.
 manifest=[]
 for p in sorted(LOGS.glob('*')):
  manifest.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
 (OUT/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('Parsed figure inputs:',len(list(OUT.glob('*.csv'))),'tables. No localization or inference rerun.')
if __name__=='__main__':main()
