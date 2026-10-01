#!/usr/bin/env python3
"""Bounded paired WCL extension. Imports unchanged, SHA-256-pinned kernels.

Run bridge first, inspect BRIDGE_STATUS.json, then run extension. No raw source
measurements are included in this packet. Existing output directories are never
overwritten. This is a post-RC8 extension, not a retrospective preregistration.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
import time
from types import SimpleNamespace
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pyproj

CSV_SHA = '870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446'
MAPS = ('recovered29', 'official32_minus71')
REFS = {'recovered29': 597.6726773741443, 'official32_minus71': 593.7425223089783}


def digest(p: Path) -> str:
    hh = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            hh.update(block)
    return hh.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def save_csv(path: Path, rows: list[dict]) -> None:
    require(bool(rows), f'No rows for {path}')
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def extracted_function(text: str, name: str, env: dict, first_line: int | None = None):
    matches = [n for n in ast.walk(ast.parse(text))
               if isinstance(n, ast.FunctionDef) and n.name == name and (first_line is None or n.lineno == first_line)]
    require(len(matches) == 1, f'Expected exactly one canonical {name}; got {len(matches)}')
    node = matches[0]
    # Compiling the original AST retains the complete function body; no source
    # replacement or rewritten scientific kernel is used.
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, '<pinned-canonical-function>', 'exec'), env)
    return env[name], {'function': name, 'first_line': node.lineno,
                       'last_line': node.end_lineno,
                       'source_sha256': hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest()}


def load_inputs(root: Path, csvpath: Path, protocol: dict):
    expected = protocol['immutable_inputs']
    paths = {
        'harness': root/'code/baseline_001_e123_pairfallback_040926.py',
        'evaluator': root/'code/deltamesh_antwerp_eval_v10_fixed_080826.py',
        'calibration_rows': root/'results/rc5/populations/calibration_ordered_source_rows.json',
        'R29_map': root/'maps/recovered29.json',
        'O32_minus71_map': root/'maps/official32_minus71.json',
        'R29_rows': root/'results/rc5/populations/recovered29_ordered_source_rows.json',
        'O32_minus71_rows': root/'results/rc5/populations/official32_minus71_ordered_source_rows.json',
    }
    require(digest(csvpath) == CSV_SHA, 'Wrong original CSV bytes')
    for name, path in paths.items():
        require(digest(path) == expected[name]['sha256'], f'Input hash mismatch: {name}')
    sys.path.insert(0, str(root/'code'))
    import baseline_001_e123_pairfallback_040926 as h
    import deltamesh_antwerp_eval_v10_fixed_080826 as ev
    t = time.perf_counter()
    msgs = ev.load_antwerp_csv(str(csvpath), min_gws=3)
    print(f'Canonical CSV load: {time.perf_counter()-t:.2f}s', flush=True)
    frame = pd.read_csv(csvpath)
    cols = [c for c in frame if str(c).strip().lower().startswith('bs ')]
    values = frame[cols].to_numpy(float)
    ids = np.flatnonzero((np.isfinite(values) & (values >= -150) & (values <= -20)).sum(axis=1) >= 3)
    require(len(msgs) == len(ids) == 55375, 'Working population mismatch')
    require(all(np.isfinite([m.x, m.y]).all() for m in msgs), 'Nonfinite transmitter position')
    lookup = {int(i): m for i, m in zip(ids, msgs)}
    order = list(map(int, ids)); random.Random(1).shuffle(order)
    calids = json.loads(paths['calibration_rows'].read_text())
    require(order[:16612] == calids, 'Calibration order mismatch')
    cal = [lookup[i] for i in calids]
    calkeys = {h.mkey(m) for m in cal}
    configurations = {}
    for name in MAPS:
        raw = json.loads((root/'maps'/f'{name}.json').read_text())
        coords = {g: np.array(raw[g], float) for g in sorted(raw, key=int)}
        rowids = json.loads((root/'results/rc5/populations'/f'{name}_ordered_source_rows.json').read_text())
        EV = [lookup[i] for i in rowids]
        pool = [lookup[i] for i in order[16612:] if sum(r.gid in coords for r in lookup[i].receptions) >= 3]
        selected = random.Random(9).sample(pool, min(2500, len(pool)))
        recreated = [m for m in selected if h.mkey(m) not in calkeys]
        require(len(EV) == 2498 and [h.mkey(m) for m in EV] == [h.mkey(m) for m in recreated],
                f'Evaluation order mismatch: {name}')
        require(not set(rowids).intersection(calids), f'Row overlap: {name}')
        require(not any(h.mkey(m) in calkeys for m in EV), f'Content overlap: {name}')
        a0 = h.fit_a0(cal, coords, 4.7)
        require(set(a0) == set(coords), f'Uncalibrated receivers: {name}')
        rxsets = [sorted([r for r in m.receptions if r.gid in coords and r.gid in a0],
                         key=lambda r: -r.rssi)[:10] for m in EV]
        require(all(len(rx) >= 3 for rx in rxsets), f'Thin selected set: {name}')
        counts = {g: 0 for g in coords}
        for rx in rxsets:
            for r in rx: counts[r.gid] += 1
        ranked = sorted(counts, key=lambda g: (-counts[g], int(g)))
        require(ranked[:2] == ['14', '69'], f'Target rank changed: {name}')
        configurations[name] = dict(name=name, coords=coords, rowids=rowids, EV=EV,
            cal=cal, a0=a0, rxsets=rxsets, ranked=ranked, counts=counts,
            truth=np.array([[m.x, m.y] for m in EV], float))
    return h, ev, configurations, paths


def score(h, ev, c: dict, coords: dict, a0: dict):
    predictions = np.empty((2498, 2), float)
    weights = np.zeros((2498, 10), float)
    selected_ids = np.full((2498, 10), -1, np.int16)
    raw_rssi = np.full((2498, 10), np.nan, float)
    for q, m in enumerate(c['EV']):
        rx = sorted([r for r in m.receptions if r.gid in coords and r.gid in a0],
                    key=lambda r: -r.rssi)[:10]
        require([(r.gid, r.rssi) for r in rx] == [(r.gid, r.rssi) for r in c['rxsets'][q]],
                f'Selection mismatch, message {q}')
        xy = np.vstack([coords[r.gid] for r in rx])
        raw = np.array([r.rssi for r in rx], float)
        corrected = raw - np.array([a0[r.gid] for r in rx], float)
        predictions[q] = h.wcl(ev, xy, corrected)
        ww = np.power(10.0, corrected / 10.0)
        total = float(np.sum(ww))
        require(np.isfinite(ww).all() and total > 0, 'Nonpositive/nonfinite WCL weights')
        ww /= total
        weights[q, :len(rx)] = ww
        selected_ids[q, :len(rx)] = [int(r.gid) for r in rx]
        raw_rssi[q, :len(rx)] = raw
        independent = np.array([float(np.sum(ww * xy[:, j])) for j in range(2)])
        require(np.allclose(independent, predictions[q], rtol=0, atol=5e-9), 'Weight identity mismatch')
    errors = np.linalg.norm(predictions-c['truth'], axis=1)
    require(np.isfinite(predictions).all() and np.isfinite(errors).all(), 'Nonfinite score')
    return dict(predictions=predictions, errors=errors, weights=weights,
                selected_ids=selected_ids, raw_rssi=raw_rssi)


def quantiles(v: np.ndarray) -> dict:
    return dict(median=float(np.median(v)), q25=float(np.quantile(v, .25)),
                q75=float(np.quantile(v, .75)), minimum=float(np.min(v)), maximum=float(np.max(v)))


def run(args) -> None:
    root, csvpath = args.source_root.resolve(), args.csv.resolve()
    protocol_dir = args.protocol_dir.resolve()
    protocol = json.loads((protocol_dir/'PROTOCOL.json').read_text())
    fields = json.loads((protocol_dir/'DIRECTION_REGISTER.json').read_text())['cases']
    freeze = json.loads((protocol_dir/'FREEZE.json').read_text())
    for name, sha in freeze['files'].items():
        checkpath = protocol_dir/name if name != '../run_paired_wcl_extension.py' else Path(__file__).resolve()
        require(digest(checkpath) == sha, f'Frozen execution object changed: {name}')
    require(len(fields) == 128, 'Invalid direction register size')
    if args.phase == 'extension':
        require(args.bridge is not None, '--bridge status path is required')
        bridge = json.loads(args.bridge.read_text())
        require(bridge['status'] == 'BRIDGE_PASS', 'Bridge has not passed')
        require(bridge['freeze_sha256'] == digest(protocol_dir/'FREEZE.json'), 'Bridge/protocol mismatch')
    output = args.output.resolve()
    require(not output.exists(), f'Refusing to overwrite {output}')
    output.mkdir(parents=True)
    (output/'pairs').mkdir()
    save_json(output/'RUN_STATUS.json', {'status': 'RUNNING', 'phase': args.phase, 'started_at': stamp(),
        'freeze_sha256': digest(protocol_dir/'FREEZE.json'), 'complete_pairs': 0})
    t0 = time.perf_counter()
    try:
        h, ev, configs, paths = load_inputs(root, csvpath, protocol)
        source = paths['harness'].read_text()
        build, build_receipt = extracted_function(source, 'build', {'np': np})
        save_json(output/'ENVIRONMENT.json', {'python': sys.version, 'platform': platform.platform(),
            'numpy': np.__version__, 'pandas': pd.__version__, 'pyproj': pyproj.__version__,
            'canonical_harness': digest(paths['harness']), 'canonical_evaluator': digest(paths['evaluator']),
            'source_csv': digest(csvpath), 'driver': digest(Path(__file__)),
            'source_function_extraction': build_receipt, 'protocol_freeze': freeze})
        baseline_checks = []
        for name, c in configs.items():
            reference = score(h, ev, c, c['coords'], c['a0']); c['reference'] = reference
            med = float(np.median(reference['errors'])); c['M0'] = med
            require(abs(med-REFS[name]) <= 1e-6, f'Baseline mismatch: {name}')
            neutrality = []
            for label, targets, disp in [('empty', set(), 5000.0), ('all_zero', set(c['coords']), 0.0)]:
                mp = build(c['coords'], targets, disp, 1)
                for arm, a0 in [('refit', h.fit_a0(c['cal'], mp, 4.7)), ('frozen', c['a0'])]:
                    sc = score(h, ev, c, mp, a0)
                    require(np.array_equal(reference['predictions'], sc['predictions']), f'Neutrality failed: {name}/{label}/{arm}')
                    neutrality.append(f'{label}/{arm}:exact')
            np.savez_compressed(output/f'{name}_reference.npz', **reference,
                truth=c['truth'], source_rows=np.array(c['rowids'], np.int64),
                calibration_source_rows=np.array(json.loads(paths['calibration_rows'].read_text()), np.int64))
            save_json(output/f'{name}_reference.json', {'map': name, 'baseline_median_m': med,
                'intercepts': c['a0'], 'selection_counts': c['counts'], 'rank_order': c['ranked'],
                'map': name, 'coordinates': {g: v.tolist() for g, v in c['coords'].items()},
                'source_row_sha256': digest(root/'results/rc5/populations'/f'{name}_ordered_source_rows.json')})
            baseline_checks.append({'map': name, 'baseline_median_m': med, 'match_at_1e_6_m': True,
                'neutrality': neutrality, 'calibration_n': len(c['cal']), 'evaluation_n': len(c['EV'])})
        rows = []
        chosen = [f for f in fields if f['historical_R29_bridge']] if args.phase == 'bridge' else fields
        require(len(chosen) == (4 if args.phase == 'bridge' else 128), 'Case count mismatch')
        for field in chosen:
            name, k, draw = field['map'], field['k'], field['draw']
            c = configs[name]; targets = set(c['ranked'][:k])
            require(targets == set(field['offsets']), 'Field target mismatch')
            original_map = {g: v.copy() for g, v in c['coords'].items()}
            perturbed = build(c['coords'], targets, 5000.0, field['seed'])
            for g in c['coords']:
                require(np.array_equal(c['coords'][g], original_map[g]), 'Reference map mutated')
                if g in targets:
                    off = field['offsets'][g]
                    want = c['coords'][g] + np.array([off['dx_m'], off['dy_m']])
                    require(np.array_equal(perturbed[g], want), f'Frozen field mismatch: {name}/{k}/{draw}/{g}')
                    require(abs(np.linalg.norm(perturbed[g]-c['coords'][g])-5000) < 2e-9, 'Magnitude mismatch')
                else:
                    require(np.array_equal(perturbed[g], c['coords'][g]), 'Nontarget coordinate changed')
            refit_a0 = h.fit_a0(c['cal'], perturbed, 4.7)
            require(set(refit_a0) == set(c['a0']), 'Calibrated set changed')
            for g in c['coords']:
                if g not in targets: require(refit_a0[g] == c['a0'][g], 'Nontarget intercept changed')
            frozen = score(h, ev, c, perturbed, c['a0'])
            refit = score(h, ev, c, perturbed, refit_a0)
            target_slots = np.isin(c['reference']['selected_ids'], [int(g) for g in targets])
            touched = target_slots.any(axis=1)
            clean_counts = (c['reference']['selected_ids'] >= 0).sum(axis=1) - target_slots.sum(axis=1)
            require(clean_counts.min() >= 1, 'No remaining clean receiver')
            for arm in (refit, frozen):
                require(np.array_equal(arm['predictions'][~touched], c['reference']['predictions'][~touched]), 'Untouched prediction changed')
                require(np.array_equal(arm['selected_ids'], c['reference']['selected_ids']), 'Selected IDs changed')
            require(np.array_equal(frozen['weights'], c['reference']['weights']), 'Frozen weights changed')
            target_f = np.sum(frozen['weights']*target_slots, axis=1)
            target_r = np.sum(refit['weights']*target_slots, axis=1)
            mf, mr = float(np.median(frozen['errors'])), float(np.median(refit['errors']))
            tf, tr = float(np.median(frozen['errors'][touched])), float(np.median(refit['errors'][touched]))
            caseid = f'{name}_top{k}_r{draw:02d}'
            outnpz = {f'{arm}_{key}': sc[key] for arm,sc in [('refit',refit),('frozen',frozen)]
                      for key in ('predictions','errors','weights')}
            outnpz.update(touched=touched, selected_clean_count=clean_counts,
                refit_target_weight_mass=target_r, frozen_target_weight_mass=target_f,
                map_coordinates=np.array(list(perturbed.values())), map_receiver_ids=np.array(list(map(int,perturbed))))
            np.savez_compressed(output/'pairs'/f'{caseid}.npz', **outnpz)
            metadata = {'case': caseid, 'field': field, 'reference_a0': c['a0'], 'refit_a0': refit_a0,
                'array_sha256': digest(output/'pairs'/f'{caseid}.npz'),
                'scope': 'New assistant-runtime execution; historical cases are bridge reruns, not independent validation.'}
            if args.phase == 'bridge':
                env = dict(np=np, cal=c['cal'], n=4.7, EV=c['EV'], args=SimpleNamespace(max_gws=10),
                    fit_a0=h.fit_a0, wcl=h.wcl, lattice=h.lattice, ev=ev, a0_true=c['a0'])
                score_old, receipt_s = extracted_function(source, 'score', env, first_line=2457)
                fixed_old, receipt_f = extracted_function(source, 'wcl_fixed', env)
                old_mr = float(score_old(perturbed, want=('wcl',))[0])
                old_mf = float(fixed_old(perturbed))
                require(abs(old_mr-mr) < 1e-9 and abs(old_mf-mf) < 1e-9, 'Original scorer bridge mismatch')
                metadata.update(canonical_refit=old_mr, canonical_frozen=old_mf,
                    original_score_extraction=receipt_s, original_fixed_extraction=receipt_f)
            save_json(output/'pairs'/f'{caseid}.json', metadata)
            row = dict(case=caseid, map=name, k=k, draw=draw, seed=field['seed'],
                historical_bridge=field['historical_R29_bridge'], baseline_m=c['M0'],
                refit_m=mr, frozen_m=mf, delta_m=mf-mr,
                refit_pct=100*(mr/c['M0']-1), frozen_pct=100*(mf/c['M0']-1), delta_pp=100*(mf-mr)/c['M0'],
                touched_n=int(touched.sum()), untouched_n=int((~touched).sum()),
                touched_refit_m=tr, touched_frozen_m=tf, touched_delta_m=tf-tr,
                reference_touched_m=float(np.median(c['reference']['errors'][touched])),
                touched_refit_target_weight_median=float(np.median(target_r[touched])),
                touched_frozen_target_weight_median=float(np.median(target_f[touched])),
                min_remaining_clean=int(clean_counts.min()),
                all_untouched_predictions_exact=True, array_sha256=metadata['array_sha256'])
            rows.append(row)
            save_csv(output/'paired_results.csv', rows)
            save_json(output/'RUN_STATUS.json', {'status':'RUNNING', 'phase':args.phase,
                'complete_pairs':len(rows),'planned_pairs':len(chosen),'freeze_sha256':digest(protocol_dir/'FREEZE.json')})
            print(f'{len(rows):3d}/{len(chosen)} {caseid} refit={mr:.6f} frozen={mf:.6f} delta={mf-mr:+.6f}', flush=True)
        result = dict(status='BRIDGE_PASS' if args.phase=='bridge' else 'COMPLETE', phase=args.phase,
            completed_at=stamp(), elapsed_s=time.perf_counter()-t0, complete_pairs=len(rows),
            planned_pairs=len(chosen), baseline_checks=baseline_checks,
            freeze_sha256=digest(protocol_dir/'FREEZE.json'), csv_sha256=CSV_SHA,
            preserved_inputs={name: digest(path) == protocol['immutable_inputs'][name]['sha256'] for name,path in paths.items()})
        if args.phase == 'bridge':
            printed = []
            for k, exp_r, exp_f in [(1,'3.5','29.3'),(2,'1.5','117.0')]:
                rr = [r for r in rows if r['k']==k]
                mr=float(np.median([r['refit_m'] for r in rr])); mf=float(np.median([r['frozen_m'] for r in rr]))
                sr=f'{100*(mr/REFS["recovered29"]-1):.1f}';sf=f'{100*(mf/REFS["recovered29"]-1):.1f}'
                require(sr==exp_r and sf==exp_f, 'Printed historical bridge mismatch')
                printed.append(dict(k=k,refit_pct=sr,frozen_pct=sf,expected_refit=exp_r,expected_frozen=exp_f))
            result['historical_printed_parity']=printed
            save_json(output/'BRIDGE_STATUS.json',result)
        else:
            summaries=[]
            for name in MAPS:
                for k in [1,2]:
                    rr=[r for r in rows if r['map']==name and r['k']==k]
                    require(len(rr)==32 and {r['draw'] for r in rr}==set(range(32)), 'Incomplete cell')
                    dd=np.array([r['delta_m'] for r in rr]); tt=np.array([r['touched_delta_m'] for r in rr])
                    summary=dict(map=name,k=k,n_pairs=len(rr),
                        positive=int((dd>0).sum()),zero=int((dd==0).sum()),negative=int((dd<0).sum()),
                        delta_m=quantiles(dd),delta_pp=quantiles(dd*100/REFS[name]),
                        touched_delta_m=quantiles(tt),touched_n=rr[0]['touched_n'],
                        refit_m=quantiles(np.array([r['refit_m'] for r in rr])),
                        frozen_m=quantiles(np.array([r['frozen_m'] for r in rr])),
                        refit_pct=quantiles(np.array([r['refit_pct'] for r in rr])),
                        frozen_pct=quantiles(np.array([r['frozen_pct'] for r in rr])),
                        difference_of_arm_medians_m=float(np.median([r['frozen_m'] for r in rr])-np.median([r['refit_m'] for r in rr])))
                    summaries.append(summary)
            result['summaries']=summaries
        require(all(result['preserved_inputs'].values()), 'Source mutated during execution')
        save_json(output/'RUN_STATUS.json',result)
        print(json.dumps(result,indent=2),flush=True)
    except BaseException as exc:
        save_json(output/'FAILURE.json',{'status':'FAILED_DO_NOT_REPORT_AS_COMPLETE', 'error':repr(exc), 'when':stamp()})
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--csv',type=Path,required=True)
    p.add_argument('--protocol-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase',choices=['bridge','extension'],required=True)
    p.add_argument('--bridge',type=Path)
    run(p.parse_args())

if __name__=='__main__':
    main()
