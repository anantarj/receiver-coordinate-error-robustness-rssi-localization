#!/usr/bin/env python3
"""Read-only formula and schedule verification of completed targeted audits."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from recover_candidates import ROOT,OLD,sha,write_json,verify_lock
from run_targeted_audits import check_lock

def main():
    check_lock()
    schedule=json.loads((ROOT/'protocol/TARGETED_AUDIT_SCHEDULE.json').read_text())
    run=json.loads((ROOT/'receipts/TARGETED_AUDIT_RECEIPT.json').read_text())
    reg=dict(np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False));expected=dict(np.load(ROOT/'inputs/EXPECTED_PRIMARY.npz',allow_pickle=False))
    ids=schedule['selected_input_ids'];seen=[];max_difference=0.;max_recorded=0.;candidate_count=0;escalated=0;gap_met=0;maximum_improvement=0.;max_shift=0.
    for uid in ids:
        p=ROOT/'targeted_audits'/f'input_{uid:06d}_receipt.json';rec=json.loads(p.read_text())
        if rec['status']!='COMPLETE' or rec['input_id']!=uid:raise AssertionError('Invalid completed audit')
        if run['input_receipts_sha256'][p.name]!=sha(p):raise AssertionError('Changed receipt')
        if rec['stages'] not in (1,2):raise AssertionError('Stage budget')
        escalated+=rec['stages']==2;gap_met+=rec['last_objective_gap_met_numerically'];seen.append(uid)
        maximum_improvement=max(maximum_improvement,rec['best_objective_improvement_db2']);max_shift=max(max_shift,rec['max_incumbent_shift_m'])
        for name,digest in rec['files_sha256'].items():
            if sha(ROOT/'targeted_audits'/name)!=digest:raise AssertionError('Changed audit artifact')
        for stage in range(rec['stages']):
            stem=f'input_{uid:06d}_stage{stage}';meta=json.loads((ROOT/'targeted_audits'/(stem+'.json')).read_text())
            with np.load(ROOT/'targeted_audits'/(stem+'.npz'),allow_pickle=False) as z:
                m=int(reg['receiver_count'][uid]);a=reg['anchors_m'][uid,:m];origin=a.mean(axis=0);points=z['candidate_local_position_m'];local_a=a-origin
                if not np.array_equal(points+origin,z['candidate_position_m']):raise AssertionError('Coordinate transform')
                d=np.sqrt(np.sum((points[:,None]-local_a[None])**2,axis=2))
                r=reg['rss_dbm'][uid,:m]-reg['intercepts_dbm'][uid,:m]+47*np.log10(d+1.)
                objective=np.sum(r*r,axis=1)
                diff=float(np.max(np.abs(objective-z['candidate_objective_db2'])))
                max_difference=max(max_difference,diff)
                recorded=float(np.max(np.abs(z['candidate_objective_db2']-z['candidate_recorded_objective_db2'])))
                max_recorded=max(max_recorded,recorded)
                if diff>1e-8:raise AssertionError('Independent objective mismatch')
                candidate_count+=len(points)
                if len(np.where(z['candidate_kind']==2)[0])!=1 or len(np.where(z['candidate_kind']==4)[0])!=1:raise AssertionError('Incumbent missing')
                primary_pos=z['candidate_position_m'][z['candidate_kind']==2][0]
                if np.linalg.norm(primary_pos-expected['position_m'][uid])>1e-6:raise AssertionError('Original primary changed')
                final_pos=z['candidate_position_m'][z['candidate_kind']==4][0]
                if np.linalg.norm(final_pos-np.asarray(meta['audit_position_m']))>1e-6:raise AssertionError('Final incumbent mismatch')
            if meta['max_splits']!=(30000 if stage==0 else 100000) or meta['splits']>meta['max_splits']:raise AssertionError('Budget exceeded')
            if abs(max(0.,meta['audit_objective_db2']-meta['global_lower_bound_db2'])-meta['objective_gap_db2'])>1e-8:raise AssertionError('Gap inconsistent')
            if meta['primary_result_changed']:raise AssertionError('Primary replacement flag')
        first=json.loads((ROOT/'targeted_audits'/f'input_{uid:06d}_stage0.json').read_text())
        triggered=bool(expected['status'][uid]!='finite_all_local_runs_converged' or
            first['objective_improvement_db2']>max(1e-4,1e-6*(1+float(expected['objective_db2'][uid]))) or first['position_shift_m']>1.)
        if triggered!=(rec['stages']==2):raise AssertionError('Escalation rule mismatch')
    if sorted(seen)!=sorted(ids) or len(set(seen))!=len(ids):raise AssertionError('Schedule incomplete')
    verify_lock()
    result={'status':'COMPLETE_INDEPENDENT_CHECK_PASS','scheduled_and_completed':len(ids),'escalated':int(escalated),'gap_met_numerically':int(gap_met),
        'retained_candidate_entries':candidate_count,'max_formula_objective_difference_db2':max_difference,
        'max_recorded_vs_recomputed_difference_db2':max_recorded,'max_objective_improvement_db2':maximum_improvement,'max_incumbent_shift_m':max_shift,
        'primary_outputs_unchanged':True,'formula':'sum_i (RSS_i-A_i+47log10(distance_m+1))^2, independently vectorized; no optimizer called.',
        'audit_lock_sha256':sha(ROOT/'protocol/TARGETED_AUDIT_LOCK.json'),'verification_script_sha256':sha(__file__)}
    write_json(ROOT/'receipts/INDEPENDENT_TARGETED_AUDIT_CHECK.json',result);print(json.dumps(result))

if __name__=='__main__':main()
