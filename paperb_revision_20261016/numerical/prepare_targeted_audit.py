#!/usr/bin/env python3
"""Prepare bounded targeted audit schedule; never invokes a numerical solver."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from recover_candidates import ROOT,OLD,sha,write_json,verify_lock

def base_selection():
    verify_lock()
    with np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False) as f:
        hashes=f['input_sha256'];counts=f['receiver_count']
    mandatory={};coverage_groups={};flag_states=[]
    for p in sorted((ROOT/'mappings').glob('*.npz')):
        with np.load(p,allow_pickle=False) as f, np.load(OLD/'results/arrays'/p.name,allow_pickle=False) as z:
            mapping=f['input_id'];bad=(z['nlls_competitive_diameter_m']>1.0)|(z['nlls_local_converged']<z['nlls_local_runs'])
            for fi,pi,qi in zip(*np.where(bad)):
                uid=int(mapping[fi,pi,qi]);counter=int(mapping[fi,1-pi,qi]);zero=int(mapping[0,pi,qi])
                reason={'block':p.stem,'field':int(fi),'policy':int(pi),'query':int(qi),'source_row':int(f['source_rows'][qi]),
                    'input_id':uid,'counterpart_input_id':counter,'zero_input_id':zero,
                    'diameter_m':float(z['nlls_competitive_diameter_m'][fi,pi,qi]),
                    'some_local_unconverged':bool(z['nlls_local_converged'][fi,pi,qi]<z['nlls_local_runs'][fi,pi,qi])}
                flag_states.append(reason)
                for key,tag in ((uid,'original_flag'),(counter,'paired_policy'),(zero,'own_zero')):
                    mandatory.setdefault(key,set()).add(tag)
            for pi in (0,1):
                for uid in np.unique(mapping[:,pi,:]):
                    group=(int(counts[uid]),pi)
                    coverage_groups.setdefault(group,set()).add(int(uid))
    coverage={}
    for (count,policy),uids in sorted(coverage_groups.items()):
        ordered=sorted(uids,key=lambda uid:(hashlib.sha256(('paperb_revision_audit_coverage_v1:'+str(hashes[uid])).encode()).hexdigest(),uid))
        coverage[f'receivers{count}_policy{policy}']=ordered[:2]
    coverage_ids=set(uid for group in coverage.values() for uid in group)
    fixed=sorted(set(mandatory)|coverage_ids)
    if len(fixed)>900:raise AssertionError('Mandatory and fixed coverage exceed900')
    result={'status':'FIXED_BASE_SELECTION_BEFORE_STRONGER_AUDITS','original_flagged_stored_states':len(flag_states),
        'original_flagged_states':flag_states,'mandatory_input_ids':sorted(mandatory),
        'mandatory_tags':{str(uid):sorted(tags) for uid,tags in mandatory.items()},
        'coverage_rule':'Two smallest SHA256(paperb_revision_audit_coverage_v1:<numerical input digest>) per receiver-count/policy stratum; independent of outputs, may overlap targeted cases.',
        'coverage_strata':coverage,'coverage_input_ids':sorted(coverage_ids),'fixed_union_input_ids':fixed,
        'maximum_unique_audits':900,'remaining_capacity':900-len(fixed),
        'new_flag_rule':'Full recovered valid-candidate diameter>1m at0.01dB2 band; descending diameter, then input digest; add only within remaining capacity. Retain overflow explicitly.',
        'primary_predictions_unchanged':True,'recovery_lock_sha256':sha(ROOT/'protocol/RECOVERY_LOCK.json')}
    dest=ROOT/'protocol/AUDIT_BASE_SELECTION.json'
    if dest.exists():
        if json.loads(dest.read_text())!=result:raise RuntimeError('Existing base selection differs')
    else:write_json(dest,result)
    print(json.dumps({k:v for k,v in result.items() if k in ('original_flagged_stored_states','remaining_capacity','maximum_unique_audits') }|{'mandatory_unique':len(mandatory),'coverage_unique':len(coverage_ids),'fixed_union':len(fixed)}))

def complete_selection():
    verify_lock()
    for name in ('PILOT_RECEIPT.json','RUN_RECEIPT.json'):
        rec=json.loads((ROOT/'receipts'/name).read_text())
        if rec['status']!='COMPLETE':raise RuntimeError('Recovery not complete')
    base=json.loads((ROOT/'protocol/AUDIT_BASE_SELECTION.json').read_text())
    with np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False) as f:hashes=f['input_sha256'];total=len(hashes)
    diameters=np.full(total,np.nan);seen=np.zeros(total,int);bindings={}
    for p in sorted((ROOT/'candidates').glob('*.npz')):
        receipt=json.loads((ROOT/'receipts'/(p.stem+'.json')).read_text())
        if sha(p)!=receipt['output_sha256']:raise RuntimeError('Changed recovered candidate shard')
        bindings[p.name]=sha(p)
        with np.load(p,allow_pickle=False) as z:
            for k,uid in enumerate(z['input_id']):
                valid=z['candidate_valid'][k];j=z['candidate_objective_db2'][k]
                keep=valid & (j<=np.min(j[valid])+0.01)
                points=z['candidate_local_position_m'][k,keep]
                diameters[uid]=float(np.linalg.norm(points[:,None]-points[None,:],axis=2).max());seen[uid]+=1
    if not np.all(seen==1):raise AssertionError('Candidate completeness/uniqueness failure')
    fixed=set(base['fixed_union_input_ids'])
    new=sorted((int(uid) for uid in np.where(diameters>1.0)[0] if int(uid) not in fixed),
        key=lambda uid:(-float(diameters[uid]),str(hashes[uid]),uid))
    admitted=new[:base['remaining_capacity']];overflow=new[base['remaining_capacity']:]
    selected=sorted(fixed|set(admitted))
    result={'status':'SCHEDULE_PREPARED_STRONG_AUDITS_NOT_RUN','selected_input_ids':selected,
        'mandatory_input_ids':base['mandatory_input_ids'],'coverage_input_ids':base['coverage_input_ids'],
        'newly_admitted_input_ids':admitted,'overflow_input_ids':overflow,
        'recovered_diameters_m':{str(uid):float(diameters[uid]) for uid in selected},
        'candidate_shards_sha256':bindings,'base_selection_sha256':sha(ROOT/'protocol/AUDIT_BASE_SELECTION.json'),
        'audit_budget':{'first_max_splits':30000,'single_escalation_max_splits':100000,'objective_gap_db2':0.01,'max_unique_inputs':900},
        'escalation':'Original primary any-local-unconverged OR objective improvement>max(1e-4,1e-6*(1+Jprimary))dB2 OR incumbent shift>1m; preserve all widely separated candidates independently of escalation.',
        'scope':'Found-candidate diagnostics and numerically guarded objective bounds; not global proof, positional uniqueness or population failure-rate sample.',
        'primary_outputs_replaced':False}
    write_json(ROOT/'protocol/TARGETED_AUDIT_SCHEDULE.json',result)
    print(json.dumps({'selected':len(selected),'mandatory':len(base['mandatory_input_ids']),'new_admitted':len(admitted),'overflow':len(overflow),'strong_audits_run':False}))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['base','complete']);a=ap.parse_args()
    base_selection() if a.action=='base' else complete_selection()
