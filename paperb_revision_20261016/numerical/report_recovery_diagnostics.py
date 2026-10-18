#!/usr/bin/env python3
"""Report all recovered pool diagnostics with stored-state and input denominators."""
import csv
import json
from pathlib import Path
import numpy as np
from recover_candidates import ROOT,OLD,sha,write_json,save_npz

BANDS=(.01,.001,.0001)
THRESHOLDS=(1.,10.,100.,1000.)

def main():
    reg=dict(np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False));u=len(reg['input_id'])
    diameter=np.full((len(BANDS),u),np.nan);minimum=np.full(u,np.nan);rawcount=np.zeros(u,np.int16);seen=np.zeros(u,np.int16)
    for p in sorted((ROOT/'candidates').glob('*.npz')):
        with np.load(p,allow_pickle=False) as f:z={k:f[k] for k in ('input_id','candidate_valid','candidate_objective_db2','candidate_local_position_m')}
        for k,uid in enumerate(z['input_id']):
            valid=z['candidate_valid'][k];j=z['candidate_objective_db2'][k];low=float(np.min(j[valid]));minimum[uid]=low;rawcount[uid]=int(valid.sum());seen[uid]+=1
            for bi,band in enumerate(BANDS):
                points=z['candidate_local_position_m'][k,valid&(j<=low+band)]
                diameter[bi,uid]=float(np.linalg.norm(points[:,None]-points[None,:],axis=2).max())
    if not np.all(seen==1):raise AssertionError('Incomplete/duplicate candidate inputs')
    save_npz(ROOT/'results/RECOVERED_POOL_DIAGNOSTICS.npz',input_id=reg['input_id'],bands_db2=np.asarray(BANDS),diameter_m=diameter,minimum_objective_db2=minimum,raw_candidate_count=rawcount)
    summary=[];flagged=[];global_count={};global_rows={};global_ids={};global_n=0
    for p in sorted((ROOT/'mappings').glob('*.npz')):
        with np.load(p,allow_pickle=False) as f:m={k:f[k] for k in f.files}
        with np.load(OLD/'results/arrays'/p.name,allow_pickle=False) as f:z={k:f[k] for k in ('nlls_competitive_diameter_m','nlls_local_runs','nlls_local_converged','nlls_status','nlls_objective_db2')}
        uid=m['input_id'];global_n+=uid.size;allrows=np.broadcast_to(m['source_rows'][None,None,:],uid.shape)
        for bi,band in enumerate(BANDS):
            d=diameter[bi,uid]
            for threshold in THRESHOLDS:
                chosen=d>threshold;key=(band,threshold)
                rows=set(map(int,allrows[chosen]));inputs=set(map(int,uid[chosen]))
                global_count[key]=global_count.get(key,0)+int(chosen.sum());global_rows.setdefault(key,set()).update(rows);global_ids.setdefault(key,set()).update(inputs)
                summary.append({'block':p.stem,'band_db2':band,'threshold_m':threshold,'stored_states':int(chosen.sum()),'scheduled_stored_states':int(uid.size),'distinct_source_rows':len(rows),'distinct_numerical_inputs':len(inputs),'maximum_diameter_m':float(d.max())})
        bad=(z['nlls_competitive_diameter_m']>1)|(z['nlls_local_converged']<z['nlls_local_runs'])|(diameter[0,uid]>1)
        for fi,pi,qi in zip(*np.where(bad)):
            key=int(uid[fi,pi,qi])
            flagged.append({'block':p.stem,'field_index':int(fi),'policy':'frozen' if pi==0 else 'refit','query_index':int(qi),'source_row':int(m['source_rows'][qi]),'input_id':key,
                'D_m':float(m['field_D_m'][fi]),'draw':int(m['field_draw'][fi]),'target_count':int(m['field_target_count'][fi]),'selected_receiver_count':int(reg['receiver_count'][key]),
                'status':str(z['nlls_status'][fi,pi,qi]),'local_runs':int(z['nlls_local_runs'][fi,pi,qi]),'local_converged':int(z['nlls_local_converged'][fi,pi,qi]),
                'selected_objective_db2':float(z['nlls_objective_db2'][fi,pi,qi]),'original_endpoint_diameter_m':float(z['nlls_competitive_diameter_m'][fi,pi,qi]),
                'full_pool_diameter_001_db2_m':float(diameter[0,key]),'full_pool_diameter_0001_db2_m':float(diameter[1,key]),'full_pool_diameter_00001_db2_m':float(diameter[2,key])})
    global_summary=[]
    for key,count in sorted(global_count.items(),reverse=True):
        band,threshold=key;bi=BANDS.index(band)
        global_summary.append({'block':'ALL_STORED_CONTEXTS','band_db2':band,'threshold_m':threshold,'stored_states':count,'scheduled_stored_states':global_n,'distinct_source_rows':len(global_rows[key]),'distinct_numerical_inputs':len(global_ids[key]),'maximum_diameter_m':float(diameter[bi].max())})
    for name,rows in [('RECOVERED_DIAGNOSTIC_DISTRIBUTION.csv',summary+global_summary),('ALL_FLAGGED_STATE_REGISTER.csv',flagged)]:
        with (ROOT/'results'/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    rec={'status':'COMPLETE','scope':'Stored-state counts include repeated inputs/messages and are not independent failure probabilities.',
        'global_unique_inputs':u,'stored_states':global_n,'retained_candidates':int(rawcount.sum()),'flagged_state_register_rows':len(flagged),
        'global_summary':global_summary,'script_sha256':sha(__file__),
        'outputs_sha256':{p.name:sha(p) for p in (ROOT/'results').glob('RECOVERED_*')},
        'flagged_register_sha256':sha(ROOT/'results/ALL_FLAGGED_STATE_REGISTER.csv')}
    write_json(ROOT/'receipts/RECOVERED_DIAGNOSTIC_REPORT.json',rec)
    print(json.dumps({'flagged_rows':len(flagged),'global_summary':global_summary}))

if __name__=='__main__':main()
