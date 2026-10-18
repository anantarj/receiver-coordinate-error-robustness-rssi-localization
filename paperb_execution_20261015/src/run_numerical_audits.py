#!/usr/bin/env python3
"""Run locked numerical spot checks without altering primary study outputs.

Audit rows are selected by exposure and source-ID hash before scientific runs.
Every exposed row receives all paired states, with the duplicate zero-policy
entry computed once. Unexposed controls receive one zero-map audit. This runner
does not read query-reference coordinates or calculate localization errors.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from rss_nlls_production import audit

ROOT = Path(__file__).resolve().parents[1]
INITIAL_SPLITS = 30000
ESCALATED_SPLITS = 100000
OBJECTIVE_GAP_TOLERANCE_DB2 = 0.01
IMPROVEMENT_ABSOLUTE_THRESHOLD_DB2 = 1e-4
IMPROVEMENT_RELATIVE_FACTOR = 1e-6
POSITION_SHIFT_THRESHOLD_M = 1.0
_CACHE = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def verify_lock(path):
    lock = json.loads(Path(path).read_text())
    required = ('src/run_numerical_audits.py', 'src/rss_nlls_production.py',
                'protocol/AUDIT_SELECTION.json')
    for name in required:
        if name not in lock['bound_files']:
            raise ValueError('Audit execution lock does not bind ' + name)
    for name, digest in lock['bound_files'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('Lock mismatch: ' + name)
    return lock


def load_block(block):
    if block not in _CACHE:
        paths = (ROOT / 'inputs/blocks' / f'{block}.npz',
                 ROOT / 'results/arrays' / f'{block}.npz')
        # Only explicitly necessary arrays are accessed. In particular, query
        # reference coordinates are neither loaded nor given to the optimizer.
        input_keys = ('source_rows', 'selected_ids', 'selected_mask',
                      'query_rssi_dbm', 'field_D_m', 'field_draw',
                      'field_target_count', 'field_anchors_m',
                      'reference_intercepts_dbm', 'field_refit_intercepts_dbm')
        output_keys = ('source_rows', 'nlls_position_m', 'nlls_objective_db2',
                       'nlls_local_runs', 'nlls_local_converged', 'nlls_finite')
        with np.load(paths[0], allow_pickle=False) as f:
            inputs = {key: f[key] for key in input_keys}
        with np.load(paths[1], allow_pickle=False) as f:
            outputs = {key: f[key] for key in output_keys}
        if not np.array_equal(inputs['source_rows'], outputs['source_rows']):
            raise ValueError('Primary source-row mismatch: ' + block)
        _CACHE[block] = inputs, outputs
    return _CACHE[block]


def run_cell(spec):
    began = time.monotonic()
    cell_id = spec['cell_id']
    destination = ROOT / 'results/numerical_audits/cells' / f'{cell_id}.json'
    if destination.exists():
        prior = json.loads(destination.read_text())
        if prior.get('specification') != spec:
            raise ValueError('Changed checkpoint specification: ' + cell_id)
        if prior.get('status') not in ('COMPLETE', 'PRIMARY_NONFINITE', 'AUDIT_EXCEPTION'):
            raise ValueError('Unrecognized checkpoint status: ' + cell_id)
        return prior

    inputs, outputs = load_block(spec['block'])
    qi, fi, pi = spec['query_index'], spec['field_index'], spec['policy_index']
    if int(inputs['source_rows'][qi]) != spec['source_row']:
        raise ValueError('Audit source ID does not match input query index')
    mask = inputs['selected_mask'][qi].astype(bool)
    receiver_ids = inputs['selected_ids'][qi][mask].astype(int)
    lookup = receiver_ids - 1
    anchors = inputs['field_anchors_m'][fi][lookup]
    rss = inputs['query_rssi_dbm'][qi][mask]
    fitted = (inputs['reference_intercepts_dbm'] if pi == 0
              else inputs['field_refit_intercepts_dbm'][fi])[lookup]
    index = fi, pi, qi
    position = outputs['nlls_position_m'][index]
    objective = float(outputs['nlls_objective_db2'][index])
    runs = int(outputs['nlls_local_runs'][index])
    converged = int(outputs['nlls_local_converged'][index])
    record = {
        'specification': spec,
        'selected_receiver_ids': receiver_ids.tolist(),
        'field_D_m': float(inputs['field_D_m'][fi]),
        'field_draw': int(inputs['field_draw'][fi]),
        'field_target_count': int(inputs['field_target_count'][fi]),
        'policy': ('frozen', 'receiver_specific_refit')[pi],
        'primary_local_runs': runs,
        'primary_local_runs_converged': converged,
        'primary_output_changed': False,
        'initial_audit': None,
        'escalated_audit': None,
        'escalation_triggered_by': [],
        'final_audit_stage': None,
        'localization_errors_scored': False,
    }
    finite = bool(outputs['nlls_finite'][index]) and np.isfinite(position).all() and math.isfinite(objective)
    if not finite:
        record['status'] = 'PRIMARY_NONFINITE'
        record['reason'] = 'The bound audit requires a finite incumbent; original failure retained.'
        record['elapsed_seconds'] = time.monotonic() - began
        write_json(destination, record)
        return record

    primary = {'position_m': position.tolist(), 'objective_db2': objective}
    threshold = max(IMPROVEMENT_ABSOLUTE_THRESHOLD_DB2,
                    IMPROVEMENT_RELATIVE_FACTOR * (1.0 + objective))
    record['primary_position_m'] = primary['position_m']
    record['primary_objective_db2'] = objective
    record['objective_improvement_escalation_threshold_db2'] = threshold
    try:
        initial = audit(anchors, rss, fitted, primary, n=4.7, d0=1.0,
                        max_splits=INITIAL_SPLITS,
                        objective_tolerance_db2=OBJECTIVE_GAP_TOLERANCE_DB2)
        record['initial_audit'] = initial
        mismatch = abs(initial['primary_objective_recomputed_db2'] - objective)
        record['primary_objective_recomputation_difference_db2'] = mismatch
        if mismatch > max(1e-8, 1e-9 * (1.0 + abs(objective))):
            raise ValueError('Recomputed primary objective disagrees with retained primary output')
        triggers = []
        if converged < runs:
            triggers.append('any_primary_local_start_unconverged')
        if initial['objective_improvement_db2'] > threshold:
            triggers.append('objective_improvement_above_threshold')
        if initial['position_shift_m'] > POSITION_SHIFT_THRESHOLD_M:
            triggers.append('position_shift_above_1m')
        record['escalation_triggered_by'] = triggers
        if triggers:
            stronger = audit(anchors, rss, fitted, primary, n=4.7, d0=1.0,
                             max_splits=ESCALATED_SPLITS,
                             objective_tolerance_db2=OBJECTIVE_GAP_TOLERANCE_DB2)
            record['escalated_audit'] = stronger
            # The stronger deterministic search includes the entire initial
            # prefix, or reaches the same gap termination. Keep both receipts.
            if stronger['audit_objective_db2'] > initial['audit_objective_db2'] + max(1e-9, 1e-10 * (1 + objective)):
                raise ArithmeticError('Escalated search unexpectedly lost its earlier incumbent')
            record['final_audit_stage'] = 'escalated_audit'
        else:
            record['final_audit_stage'] = 'initial_audit'
        record['status'] = 'COMPLETE'
    except Exception as exc:
        # A scheduled failure is an explicit output, not grounds to replace or
        # silently omit the associated primary scientific result.
        record['status'] = 'AUDIT_EXCEPTION'
        record['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
    record['elapsed_seconds'] = time.monotonic() - began
    write_json(destination, record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--lock', type=Path, default=ROOT / 'protocol/EXECUTION_LOCK.json')
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError('workers must be positive')
    began = time.monotonic()
    verify_lock(args.lock)
    selection_path = ROOT / 'protocol/AUDIT_SELECTION.json'
    selection = json.loads(selection_path.read_text())
    selections = selection['selections']
    primary_receipt_path = ROOT / 'receipts/PRIMARY_RUN_RECEIPT.json'
    primary_receipt = json.loads(primary_receipt_path.read_text())
    if primary_receipt.get('status') != 'COMPLETE':
        raise ValueError('Primary study must be complete before numerical auditing')
    if primary_receipt.get('lock_sha256') != sha(args.lock):
        raise ValueError('Primary study used a different execution lock')

    provenance = {
        'lock_sha256': sha(args.lock),
        'selection_sha256': sha(selection_path),
        'runner_sha256': sha(__file__),
        'solver_sha256': sha(ROOT / 'src/rss_nlls_production.py'),
        'primary_receipt_sha256': sha(primary_receipt_path),
    }
    block_hashes = {}
    specs = []
    for selected in selections:
        block = selected['block']
        if Path(block).name != block or block.endswith('.npz'):
            raise ValueError('block must be an NPZ basename without its extension')
        if selected['kind'] not in ('exposed', 'unexposed_control'):
            raise ValueError('Unknown audit selection kind')
        input_path = ROOT / 'inputs/blocks' / f'{block}.npz'
        output_path = ROOT / 'results/arrays' / f'{block}.npz'
        input_hash, output_hash = sha(input_path), sha(output_path)
        if output_hash != primary_receipt['output_arrays'][output_path.name]:
            raise ValueError('Changed primary array: ' + block)
        block_hashes[block] = (input_hash, output_hash)
        with np.load(input_path, allow_pickle=False) as inputs:
            qi = int(selected['query_index'])
            source = int(selected['source_row'])
            if int(inputs['source_rows'][qi]) != source:
                raise ValueError('Selected row/index mismatch: ' + block)
            fields = np.asarray(inputs['field_D_m'])
        zero = np.flatnonzero(fields == 0)
        if len(zero) != 1:
            raise ValueError('Exactly one zero-map field expected in each block')
        active_fields = range(len(fields)) if selected['kind'] == 'exposed' else zero.tolist()
        for fi in active_fields:
            policies = (0,) if fields[fi] == 0 else (0, 1)
            for pi in policies:
                specs.append({
                    'cell_id': f'{block}__q{qi:04d}_f{fi:03d}_p{pi}',
                    'block': block, 'query_index': qi, 'source_row': source,
                    'kind': selected['kind'], 'field_index': int(fi),
                    'policy_index': pi, 'provenance': provenance,
                    'input_sha256': input_hash, 'primary_array_sha256': output_hash,
                })
    if len({spec['cell_id'] for spec in specs}) != len(specs):
        raise ValueError('Duplicate audit cell identities')
    if 'expected_cells' in selection and len(specs) != int(selection['expected_cells']):
        raise ValueError('Audit cell count differs from locked selection')
    write_json(ROOT / 'receipts/NUMERICAL_AUDIT_SCHEDULE.json', {
        'status': 'READY', 'provenance': provenance,
        'cells': len(specs), 'exposed_cells': sum(s['kind'] == 'exposed' for s in specs),
        'unexposed_control_cells': sum(s['kind'] == 'unexposed_control' for s in specs),
        'initial_splits': INITIAL_SPLITS, 'escalated_splits': ESCALATED_SPLITS,
        'objective_gap_tolerance_db2': OBJECTIVE_GAP_TOLERANCE_DB2,
        'objective_improvement_threshold': 'max(1e-4,1e-6*(1+J_primary)) dB^2',
        'position_shift_threshold_m': POSITION_SHIFT_THRESHOLD_M,
        'other_trigger': 'any primary local start unconverged',
        'cell_ids': [spec['cell_id'] for spec in specs],
    })
    records = []
    with cf.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_cell, spec): spec for spec in specs}
        for future in cf.as_completed(futures):
            result = future.result()
            records.append(result)
            progress = {
                'completed_cells': len(records), 'scheduled_cells': len(specs),
                'last_cell': result['specification']['cell_id'],
                'last_status': result['status'],
                'elapsed_seconds': time.monotonic() - began,
            }
            write_json(ROOT / 'receipts/NUMERICAL_AUDIT_PROGRESS.json', progress)
            print(json.dumps(progress), flush=True)

    verify_lock(args.lock)
    for block, (input_hash, output_hash) in block_hashes.items():
        if sha(ROOT / 'inputs/blocks' / f'{block}.npz') != input_hash:
            raise ValueError('Input changed during auditing: ' + block)
        if sha(ROOT / 'results/arrays' / f'{block}.npz') != output_hash:
            raise ValueError('Primary result changed during auditing: ' + block)
    complete = [r for r in records if r['status'] == 'COMPLETE']
    final_results = [r[r['final_audit_stage']] for r in complete]
    receipt = {
        'status': 'COMPLETE', 'provenance': provenance,
        'scheduled_cells': len(specs), 'recorded_cells': len(records),
        'completed_audits': len(complete),
        'primary_nonfinite': sum(r['status'] == 'PRIMARY_NONFINITE' for r in records),
        'audit_exceptions': sum(r['status'] == 'AUDIT_EXCEPTION' for r in records),
        'escalated_cells': sum(bool(r['escalation_triggered_by']) for r in records),
        'final_numerical_objective_gap_met': sum(r['objective_gap_met_numerically'] for r in final_results),
        'final_unresolved_objective_gaps': sum(not r['objective_gap_met_numerically'] for r in final_results),
        'primary_output_arrays_verified_unchanged': True,
        'localization_errors_scored': False,
        'elapsed_seconds': time.monotonic() - began,
        'cell_outputs': {
            spec['cell_id']: sha(ROOT / 'results/numerical_audits/cells' / f"{spec['cell_id']}.json")
            for spec in sorted(specs, key=lambda item: item['cell_id'])
        },
        'interpretation': [
            'Audit rows are exposure-conditioned diagnostics, not a failure-rate sample.',
            'Primary finite-algorithm outputs remain unchanged.',
            'Unresolved objective gaps are retained even if no escalation condition fires.',
            'Numerical objective tolerance does not certify positional uniqueness or accuracy.',
        ],
    }
    write_json(ROOT / 'receipts/NUMERICAL_AUDIT_RECEIPT.json', receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != 'cell_outputs'}), flush=True)


if __name__ == '__main__':
    main()
