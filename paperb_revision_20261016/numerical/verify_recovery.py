#!/usr/bin/env python3
"""Independent formula-level check of recovered candidates, without optimization."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from recover_candidates import ROOT,OLD,sha,write_json,verify_lock

def main(partial=False):
    verify_lock()
    reg=dict(np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False))
    expected=dict(np.load(ROOT/'inputs/EXPECTED_PRIMARY.npz',allow_pickle=False))
    size=len(reg['input_id']);seen=np.zeros(size,np.int16)
    maxj=0.;maxglobalj=0.;maxpos=0.;maxoriginalj=0.;totalc=0;outputs={};all_selected=np.full((size,2),np.nan)
    all_j=np.full(size,np.nan);all_diameter=np.full(size,np.nan);counts=np.zeros(size,np.int16)
    for path in sorted((ROOT/'candidates').glob('*.npz')):
        rec=json.loads((ROOT/'receipts'/(path.stem+'.json')).read_text())
        if rec['status']!='COMPLETE' or sha(path)!=rec['output_sha256']:raise AssertionError('Invalid candidate checkpoint')
        outputs[path.name]=sha(path)
        with np.load(path,allow_pickle=False) as archive:
            z={key:archive[key] for key in archive.files}
            for k,uid in enumerate(z['input_id']):
                uid=int(uid);seen[uid]+=1;m=int(reg['receiver_count'][uid]);valid=z['candidate_valid'][k]
                if valid.sum()!=z['candidate_count'][k]:raise AssertionError('Candidate count mismatch')
                a=reg['anchors_m'][uid,:m];origin=a.mean(axis=0);local_a=a-origin
                pos=z['candidate_local_position_m'][k,valid]
                distance=np.sqrt(np.sum((pos[:,None,:]-local_a[None,:,:])**2,axis=2))
                residual=reg['rss_dbm'][uid,:m]-reg['intercepts_dbm'][uid,:m]+47*np.log10(distance+1.)
                objective=np.sum(residual*residual,axis=1)
                diff=float(np.max(np.abs(objective-z['candidate_objective_db2'][k,valid])))
                maxj=max(maxj,diff)
                if diff>1e-8:raise AssertionError(f'Objective formula discrepancy input{uid}: {diff}')
                if not np.array_equal(pos+origin,z['candidate_position_m'][k,valid]):raise AssertionError('Coordinate transform')
                global_pos=z['candidate_position_m'][k,valid]
                global_distance=np.sqrt(np.sum((global_pos[:,None,:]-a[None,:,:])**2,axis=2))
                global_residual=reg['rss_dbm'][uid,:m]-reg['intercepts_dbm'][uid,:m]+47*np.log10(global_distance+1.)
                global_objective=np.sum(global_residual*global_residual,axis=1)
                global_diff=float(np.max(np.abs(global_objective-z['candidate_objective_db2'][k,valid])))
                maxglobalj=max(maxglobalj,global_diff)
                # The local-to-absolute-coordinate addition rounds near 6e6 m.
                # Verify its observed objective effect against the exact residual
                # difference identity, with a rounding allowance for reduction.
                dr=np.abs(global_residual-residual)
                bound=np.sum(2*np.abs(residual)*dr+dr*dr,axis=1)
                allowance=1e-9+1e-12*np.maximum(np.abs(objective),np.abs(global_objective))
                if np.any(np.abs(global_objective-objective)>bound+allowance):raise AssertionError('Global objective consistency')
                slot=int(z['selected_candidate_slot'][k])
                if not z['candidate_valid'][k,slot] or z['candidate_kind'][k,slot]!=2:raise AssertionError('Incumbent slot')
                if not np.array_equal(z['candidate_position_m'][k,slot],z['selected_position_m'][k]):raise AssertionError('Incumbent position')
                if abs(z['candidate_objective_db2'][k,slot]-z['selected_objective_db2'][k])>1e-8:raise AssertionError('Incumbent objective')
                if z['selected_objective_db2'][k]>np.min(z['candidate_objective_db2'][k,valid])+1e-8:raise AssertionError('Not minimum retained candidate')
                dp=float(np.linalg.norm(z['selected_position_m'][k]-expected['position_m'][uid]));dj=abs(float(z['selected_objective_db2'][k]-expected['objective_db2'][uid]))
                maxpos=max(maxpos,dp);maxoriginalj=max(maxoriginalj,dj)
                if dp>1e-6 or dj>1e-8:raise AssertionError('Primary changed')
                totalc+=int(valid.sum());counts[uid]=int(valid.sum());all_selected[uid]=z['selected_position_m'][k];all_j[uid]=z['selected_objective_db2'][k]
                keep=valid & (z['candidate_objective_db2'][k]<=np.min(z['candidate_objective_db2'][k,valid])+0.01)
                p=z['candidate_local_position_m'][k,keep]
                all_diameter[uid]=float(np.linalg.norm(p[:,None]-p[None,:],axis=2).max())
    if np.any(seen>1):raise AssertionError('Duplicate global input recovery')
    if not partial and not np.all(seen==1):raise AssertionError('Incomplete global input recovery')
    block_counts={};max_mapped_difference=0.0
    for path in sorted((ROOT/'mappings').glob('*.npz')):
        with np.load(path,allow_pickle=False) as mapping,np.load(OLD/'results/arrays'/path.name,allow_pickle=False) as old:
            uid=mapping['input_id'];available=seen[uid]==1
            if np.any(available):
                dp=np.linalg.norm(all_selected[uid][available]-old['nlls_position_m'][available],axis=-1)
                dj=np.abs(all_j[uid][available]-old['nlls_objective_db2'][available])
                max_mapped_difference=max(max_mapped_difference,float(dp.max()))
                if np.any(dp>1e-6) or np.any(dj>1e-8):raise AssertionError('Mapped original state changed')
            block_counts[path.stem]={'recovered_states':int(available.sum()),'scheduled_states':int(uid.size)}
    result={'status':'PARTIAL_CHECK_PASS' if partial else 'COMPLETE_CHECK_PASS',
        'method':'Independent vectorized RSS residual formula at captured exact local coordinates; no solver execution.',
        'unique_inputs':size,'recovered_unique_inputs':int((seen==1).sum()),'retained_candidates':totalc,
        'max_formula_objective_difference_db2':maxj,'max_original_position_difference_m':maxpos,
        'max_absolute_coordinate_objective_difference_db2':maxglobalj,
        'max_original_objective_difference_db2':maxoriginalj,'max_mapped_original_position_difference_m':max_mapped_difference,
        'states':block_counts,'candidate_shards_sha256':outputs,
        'recovery_lock_sha256':sha(ROOT/'protocol/RECOVERY_LOCK.json'),
        'verification_script_sha256':sha(__file__),
        'full_pool_diameter_above_1m_unique_inputs':int(np.nansum(all_diameter>1)),
        'full_pool_diameter_max_m':float(np.nanmax(all_diameter))}
    write_json(ROOT/'receipts'/('INDEPENDENT_PARTIAL_CHECK.json' if partial else 'INDEPENDENT_RECOVERY_CHECK.json'),result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('states','candidate_shards_sha256')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');a=parser.parse_args();main(a.partial)
