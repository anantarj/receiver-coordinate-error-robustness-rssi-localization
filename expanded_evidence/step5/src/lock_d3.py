#!/usr/bin/env python3
"""Resolve a previously written calibration-only target rule and lock D3.
Does not compute evaluation predictions or inspect evaluation outcome arrays.
"""
from __future__ import annotations
import argparse, csv, datetime, json, sys, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/step4'))
from step2_raw_helpers import Archive,load_raw,CSV_SHA,ARCHIVE_SHA
from model import js,sha,need

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--csv',type=Path,required=True);ap.add_argument('--archive',type=Path,required=True)
 a=ap.parse_args();pd=ROOT/'protocol';need(not (pd/'D3_LOCK.json').exists(),'Already locked')
 rule=json.loads((pd/'D3_SELECTION_RULE.json').read_text())
 start=time.perf_counter();ar=Archive(a.archive);raw=load_raw(a.csv)
 cal=np.array(ar.js('reproduction_inputs/results/rc5/populations/calibration_ordered_source_rows.json'),int)
 need(np.array_equal(cal,np.array(raw['source_order'][:16612])),'Calibration identity')
 coords=ar.js('reproduction_inputs/maps/official32_minus71.json')
 counts={int(g):int(raw['valid'][cal,int(g)-1].sum()) for g in coords}
 eligible=sorted([g for g,n in counts.items() if n>=10],key=lambda g:(-counts[g],g))
 groups=np.array_split(np.array(eligible,int),3);selected=[];allrows=[];issues=[]
 for lab,group in zip(['upper','middle','lower'],groups):
  m=len(group);idx=[(m-1)//3,2*(m-1)//3] if m>=2 else []
  if len(set(idx))<2 and m>=2:idx=[0,m-1]
  if m<2:issues.append({'stratum':lab,'count':m,'action':'no replacement'})
  for j,g in enumerate(group):
   row={'receiver_id':int(g),'calibration_receptions':counts[int(g)],'rank_one_based':eligible.index(int(g))+1,'stratum':lab,'stratum_size':m,'within_stratum_index_zero':j,'selected':j in idx}
   allrows.append(row)
   if j in idx:selected.append(row)
 with (pd/'D3_TRAINING_PARTICIPATION_REGISTER.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
 corepath=ROOT/'vendor/step4/REAL_CORE_REGISTRY.json';core=json.loads(corepath.read_text())
 need(len(selected)==6,'Six targets not available; preserve register and report')
 reg={'registry_id':'PAPERB-D3-20261008-v1','map':'official32_minus71','n_fit':4.7,'target_receivers':[r['receiver_id'] for r in selected],'target_records':selected,'D_m':[0,1000,5000],'draws':list(range(32)),'kappa':[1.,4.7],'policies':core['policies'],'bounds_db':[10,30],'directions_by_draw_receiver':{r:{str(g):core['directions_by_draw_receiver'][r][str(g)] for g in eligible} for r in map(str,range(32))},'direction_source_sha256':sha(corepath),'selection_rule_sha256':sha(pd/'D3_SELECTION_RULE.json'),'training_register_sha256':sha(pd/'D3_TRAINING_PARTICIPATION_REGISTER.csv'),'calibration_count':len(cal),'eligible_receivers':len(eligible),'eligibility_issues':issues,'raw_csv_sha256':CSV_SHA,'upstream_sha256':ARCHIVE_SHA,'selection':'Original native evaluation rows and raw-RSSI ranked maximum-ten selection remain fixed. No refill, receiver correction, or outcome-based target substitution.','inference':'Descriptive paired analysis. Receiver strata not independently randomized populations. Empty touched subsets retained as empty, not substituted.','quantiles':[.5,.9,.95],'quantile_method':'linear','tolerance':{'absolute_m':1e-6,'relative':1e-12,'weights':1e-12},'resource_ceiling':{'seconds_per_run':300,'max_output_bytes':600000000},'external_preregistration':False}
 js(pd/'D3_REGISTRY.json',reg)
 js(pd/'D3_LOCK.json',{'status':'LOCKED_BEFORE_NEW_D3_OUTCOMES','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'registry_sha256':sha(pd/'D3_REGISTRY.json'),'selection_rule_sha256':sha(pd/'D3_SELECTION_RULE.json'),'training_register_sha256':sha(pd/'D3_TRAINING_PARTICIPATION_REGISTER.csv'),'scope':'Local lock after historical/core outcomes were known; not external preregistration.'})
 js(ROOT/'reports/D3_LOCK_RECEIPT.json',{'seconds':time.perf_counter()-start,'selected_receivers':selected,'calibration_only_selection':True,'evaluation_data_used_to_choose_targets':False,'consumed_archive_members':ar.consumed})
 print(json.dumps(selected,indent=2));print('D3 locked; no new D3 outcome calculated.')
if __name__=='__main__':main()
