#!/usr/bin/env python3
"""Summarize locked targeted-audit outputs, without calling an optimizer."""
from pathlib import Path
import csv
import json
from collections import Counter
import numpy as np
from recover_candidates import ROOT, sha, write_json
from run_targeted_audits import check_lock


def main():
    check_lock()
    schedule = json.loads((ROOT/'protocol/TARGETED_AUDIT_SCHEDULE.json').read_text())
    reg = dict(np.load(ROOT/'inputs/UNIQUE_INPUTS.npz', allow_pickle=False))
    expected = dict(np.load(ROOT/'inputs/EXPECTED_PRIMARY.npz', allow_pickle=False))
    contexts = {}
    for p in sorted((ROOT/'mappings').glob('*.npz')):
        z = dict(np.load(p, allow_pickle=False))
        for f, policy, q in np.argwhere(np.isin(z['input_id'], schedule['selected_input_ids'])):
            uid = int(z['input_id'][f,policy,q])
            contexts.setdefault(uid, []).append(dict(block=p.stem, field_index=int(f),
                policy=('frozen','refit')[policy], query_index=int(q), source_row=int(z['source_rows'][q]),
                D_m=float(z['field_D_m'][f]), draw=int(z['field_draw'][f]),
                target_count=int(z['field_target_count'][f])))
    rows=[]; global_delta=0.; reasons=Counter(); best_not_last=0
    for uid in schedule['selected_input_ids']:
        r=json.loads((ROOT/'targeted_audits'/f'input_{uid:06d}_receipt.json').read_text())
        if r['status']!='COMPLETE': raise AssertionError('Incomplete audit')
        reasons.update(r['escalation_reasons']); best_not_last+=r['best_stage']!=r['stages']-1
        row={k:r[k] for k in ('input_id','stages','best_stage','best_audit_objective_db2',
             'best_objective_improvement_db2','max_incumbent_shift_m','last_objective_gap_db2',
             'last_objective_gap_met_numerically','total_splits')}
        row.update(primary_objective_db2=float(expected['objective_db2'][uid]),
            primary_status=str(expected['status'][uid]),receiver_count=int(reg['receiver_count'][uid]),
            escalation_reasons='|'.join(r['escalation_reasons']),contexts=json.dumps(contexts[uid],separators=(',',':')))
        rows.append(row)
        m=int(reg['receiver_count'][uid]); a=reg['anchors_m'][uid,:m]
        for stage in range(r['stages']):
            z=dict(np.load(ROOT/'targeted_audits'/f'input_{uid:06d}_stage{stage}.npz',allow_pickle=False))
            points=z['candidate_position_m']
            d=np.sqrt(np.sum((points[:,None]-a[None])**2,axis=2))
            residual=reg['rss_dbm'][uid,:m]-reg['intercepts_dbm'][uid,:m]+47*np.log10(d+1.)
            j=np.sum(residual*residual,axis=1)
            global_delta=max(global_delta,float(np.max(np.abs(j-z['candidate_objective_db2']))))
    out=ROOT/'results/TARGETED_AUDIT_STATE_REGISTER.csv'
    with out.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    maximum=lambda key:max(rows,key=lambda x:x[key])
    result=dict(status='COMPLETE_DESCRIPTIVE_REPORT',audits=len(rows),
        escalation_reason_counts=dict(reasons),best_stage_not_last_stage=best_not_last,
        shift_above_m={str(t):sum(r['max_incumbent_shift_m']>t for r in rows) for t in (1e-3,.01,.1,1.,10.,100.)},
        objective_improvement_above_db2={str(t):sum(r['best_objective_improvement_db2']>t for r in rows) for t in (1e-6,1e-4,1e-3,.01)},
        last_gap_met=sum(r['last_objective_gap_met_numerically'] for r in rows),
        last_gap_quantiles_db2={str(q):float(np.quantile([r['last_objective_gap_db2'] for r in rows],q)) for q in (0,.5,.9,.95,1)},
        max_shift=maximum('max_incumbent_shift_m'),max_improvement=maximum('best_objective_improvement_db2'),
        max_last_gap=maximum('last_objective_gap_db2'),
        maximum_absolute_coordinate_objective_recompute_difference_db2=global_delta,
        global_formula='sum_i (RSS_i-A_i+47log10(norm(absolute_position-absolute_anchor)+1))^2',
        absolute_coordinate_note='Local-objective formula is independently verified separately; absolute UTM addition rounds coordinates and is reported, not substituted.',
        original_outputs_replaced=False,script_sha256=sha(__file__),csv_sha256=sha(out))
    write_json(ROOT/'receipts/TARGETED_AUDIT_DESCRIPTIVE_REPORT.json',result)
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
