#!/usr/bin/env python3
"""Descriptive analysis of every locked Paper B matched-study result.

No scientific outcomes are selected by sign, convergence, or effect size. Each
conditional numerical statistic carries its scheduled and finite denominator.
Quantile contrasts and quantiles of row-paired differences are separate outputs.
No pooled inference, confidence interval, or significance test is performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('wcl', 'nlls')
POLICIES = ('frozen', 'refit')
ATOL_M = 1e-6
RTOL = 1e-12
Q_LEVELS = (('p50', .5), ('p90', .9), ('p95', .95))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_npz(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def native(value):
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [native(v) for v in value]
    if isinstance(value, np.ndarray):
        return native(value.tolist())
    if isinstance(value, np.generic):
        return native(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(native(value), indent=2, allow_nan=False) + '\n')


def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows([{k: native(v) for k, v in row.items()} for row in rows])


def stats(values, prefix=''):
    x = np.asarray(values, float)
    if x.ndim != 1 or not np.isfinite(x).all():
        raise ValueError('Statistic receives a nonfinite or non-vector input')
    out = {prefix + 'n': int(len(x))}
    if len(x):
        out.update({prefix + name: float(np.quantile(x, q, method='linear'))
                    for name, q in Q_LEVELS})
        out.update({prefix + 'mean': float(x.mean()), prefix + 'min': float(x.min()),
                    prefix + 'max': float(x.max())})
    else:
        out.update({prefix + k: None for k in ('p50', 'p90', 'p95', 'mean', 'min', 'max')})
    return out


def paired_change(a, b, prefix=''):
    """Positive a-b is a benefit from moving from a to b; finite pairs only."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.ndim != 1 or not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError('Paired change requires matched finite vectors')
    diff = a - b
    tol = ATOL_M + RTOL * np.maximum(np.abs(a), np.abs(b))
    out = stats(diff, prefix + 'paired_difference_')
    out.update({prefix + 'help_count': int(np.sum(diff > tol)),
                prefix + 'harm_count': int(np.sum(diff < -tol)),
                prefix + 'tie_count': int(np.sum(np.abs(diff) <= tol))})
    for label in ('help', 'harm', 'tie'):
        out[prefix + label + '_fraction_of_finite_pairs'] = (
            out[prefix + label + '_count'] / len(a) if len(a) else None)
    for label, q in Q_LEVELS:
        out[prefix + label + '_quantile_difference'] = (
            float(np.quantile(a, q, method='linear') - np.quantile(b, q, method='linear'))
            if len(a) else None)
    return out


def norm(x):
    return np.linalg.norm(x, axis=-1)


def category(a, b):
    if a is None or b is None:
        return 'not_estimable'
    tolerance = ATOL_M + RTOL * max(abs(a), abs(b))
    return 'wcl_lower' if a < b - tolerance else 'nlls_lower' if b < a - tolerance else 'numerical_tie'


def identity(meta):
    """Canonical block metadata; populated by the input builder, never filename parsing."""
    meta = meta.get('identity', meta)
    required = ('study', 'map', 'fold', 'budget', 'replicate')
    missing = [k for k in required if k not in meta]
    if missing:
        raise ValueError('Block metadata missing canonical keys: ' + ','.join(missing))
    return {k: meta[k] for k in required}


def field_identity(b, fi):
    targets = np.flatnonzero(np.asarray(b['field_target_mask'][fi], bool)) + 1
    if len(targets) != int(b['field_target_count'][fi]):
        raise ValueError('Target mask/count mismatch')
    return {'field_index': int(fi), 'D_m': float(b['field_D_m'][fi]),
            'draw': int(b['field_draw'][fi]), 'target_ids': ','.join(map(str, targets)),
            'target_count': len(targets)}


def zero_index(b):
    zero = np.flatnonzero(np.asarray(b['field_D_m']) == 0)
    if len(zero) != 1:
        raise ValueError('Exactly one baseline field required per calibration context')
    return int(zero[0])


def selected_exposure(b, fi):
    ids = np.asarray(b['selected_ids'], int)
    mask = np.asarray(b['selected_mask'], bool)
    return np.sum(np.asarray(b['field_target_mask'][fi], bool)[np.maximum(ids - 1, 0)] & mask, axis=1)


def check_record(checks, name, passed, **details):
    checks.append({'check': name, 'pass': bool(passed), **native(details)})


def analyze_block(name, b, r, meta):
    base = {'block': name, **identity(meta)}
    q = len(b['source_rows']); f = len(b['field_D_m']); z = zero_index(b)
    if not np.array_equal(r['source_rows'], b['source_rows']):
        raise ValueError(name + ': mismatched source rows')
    if not np.array_equal(r['query_indices'], np.arange(q)):
        raise ValueError(name + ': result query indices are not the complete ordered cohort')
    truth = np.asarray(b['query_xy_m'], float)
    if truth.shape != (q, 2) or not np.isfinite(truth).all():
        raise ValueError(name + ': invalid query references')
    for key in ('field_D_m', 'field_draw', 'field_target_count'):
        if not np.array_equal(r[key], b[key]):
            raise ValueError(name + ': result field metadata mismatch: ' + key)
    arms, effects, rankings, controls, diagnostics, checks, availability = [], [], [], [], [], [], []
    predictions = {}; errors = {}; finite = {}
    for method in METHODS:
        predictions[method] = np.asarray(r[method + '_position_m'])
        if predictions[method].shape != (f, 2, q, 2):
            raise ValueError(name + ': invalid prediction array shape')
        errors[method] = norm(predictions[method] - truth[None, None, :, :])
        finite[method] = np.isfinite(predictions[method]).all(axis=-1)
        if method == 'nlls':
            check_record(checks, name + ':nlls_finite_flag',
                         np.array_equal(finite[method], r['nlls_finite']))
        zero_pair = finite[method][z, 0] & finite[method][z, 1]
        same_finite = np.array_equal(finite[method][z, 0], finite[method][z, 1])
        zero_delta = norm(predictions[method][z, 0, zero_pair] - predictions[method][z, 1, zero_pair])
        check_record(checks, name + ':' + method + ':zero_policy_identity',
                     same_finite and bool(np.all(zero_delta <= ATOL_M)),
                     scheduled=q, finite_pairs=int(zero_pair.sum()),
                     maximum_difference_m=float(zero_delta.max()) if len(zero_delta) else None)
    for fi in range(f):
        field = {**base, **field_identity(b, fi)}
        exposure = selected_exposure(b, fi)
        declared_sample_exposure = meta.get('population', {}).get('sample_selected_target_exposure', {}).get(field['target_ids'])
        if declared_sample_exposure is not None:
            observed_exposure = {str(k): int(np.sum(exposure == k)) for k in range(field['target_count'] + 1)}
            check_record(checks, name + ':predeclared_sample_exposure_field_' + str(fi),
                         observed_exposure == declared_sample_exposure,
                         observed=observed_exposure, declared=declared_sample_exposure)
        if 'fields' in meta:
            declared = meta['fields'][fi]
            expected_targets = [int(v) for v in field['target_ids'].split(',')] if field['target_ids'] else []
            check_record(checks, name + ':metadata_field_' + str(fi),
                         int(declared['field_index']) == fi and float(declared['D_m']) == field['D_m']
                         and int(declared['draw']) == field['draw'] and list(declared['target_ids']) == expected_targets)
        for exposed in range(int(field['target_count']) + 1):
            availability.append({**field, 'selected_target_count': exposed,
                                 'sampled_count': int(np.sum(exposure == exposed)), 'sampled_denominator': q})
        populations = [('full_sample', np.ones(q, bool))]
        if fi != z:
            populations.append(('selected_target_affected', exposure > 0))
        if fi != z:
            intercept_diff = b['field_refit_intercepts_dbm'][fi] - b['reference_intercepts_dbm']
            untargeted = ~np.asarray(b['field_target_mask'][fi], bool)
            supported = np.isfinite(b['reference_intercepts_dbm'])
            check_record(checks, name + ':untargeted_intercepts_field_' + str(fi),
                         bool(np.all(intercept_diff[untargeted & supported] == 0)))
        for population, subset in populations:
            ident = {**field, 'population': population, 'scheduled_n': int(subset.sum())}
            for method in METHODS:
                pred, err, fin = predictions[method], errors[method], finite[method]
                for pi, policy in enumerate(POLICIES):
                    good = subset & fin[fi, pi]
                    row = {**ident, 'method': method, 'policy': policy,
                           'finite_n': int(good.sum()), 'nonfinite_n': int((subset & ~fin[fi, pi]).sum()),
                           'finite_fraction_of_scheduled': float(good.sum() / subset.sum()) if subset.any() else None,
                           **stats(err[fi, pi, good], 'error_m_')}
                    arms.append(row)
                    if method == 'wcl':
                        diagnostics.append({**ident, 'policy': policy,
                                            **stats(r['wcl_target_mass'][fi, pi, good], 'target_mass_'),
                                            **stats(r['wcl_effective_weight_count'][fi, pi, good], 'effective_weight_count_')})
                if fi == z:
                    continue
                pair = subset & fin[fi, 0] & fin[fi, 1]
                triple = pair & fin[z, 0]
                effect = {**ident, 'method': method,
                          'finite_frozen_refit_pairs_n': int(pair.sum()),
                          'missing_frozen_refit_pairs_n': int(subset.sum() - pair.sum()),
                          'frozen_only_finite_n': int((subset & fin[fi, 0] & ~fin[fi, 1]).sum()),
                          'refit_only_finite_n': int((subset & ~fin[fi, 0] & fin[fi, 1]).sum()),
                          'neither_finite_n': int((subset & ~fin[fi, 0] & ~fin[fi, 1]).sum()),
                          'finite_zero_frozen_refit_triples_n': int(triple.sum()),
                          'missing_zero_frozen_refit_triples_n': int(subset.sum() - triple.sum()),
                          **paired_change(err[fi, 0, pair], err[fi, 1, pair], 'refit_error_benefit_m_'),
                          **stats(err[z, 0, triple], 'own_zero_error_m_')}
                p0, pf, pr = pred[z, 0, triple], pred[fi, 0, triple], pred[fi, 1, triple]
                direct, extra, net = norm(pf - p0), norm(pr - pf), norm(pr - p0)
                effect.update(stats(direct, 'direct_geometry_m_'))
                effect.update(stats(extra, 'additional_refit_m_'))
                effect.update(stats(net, 'net_refit_m_'))
                effect.update(paired_change(direct, net, 'refit_sensitivity_reduction_m_'))
                effect.update(paired_change(err[fi, 0, triple], err[z, 0, triple], 'frozen_error_penalty_vs_own_zero_m_'))
                effect.update(paired_change(err[fi, 1, triple], err[z, 0, triple], 'refit_error_penalty_vs_own_zero_m_'))
                # For these two penalty quantities, positive means worse than zero;
                # help/harm labels are omitted to prevent reversed interpretation.
                for key in list(effect):
                    if ('error_penalty_vs_own_zero' in key and any(x in key for x in ('help_', 'harm_', 'tie_'))):
                        del effect[key]
                effects.append(effect)
            if fi != z and str(base['study']) in ('1', 'study1', 'study_1'):
                common = subset & finite['wcl'][fi].all(axis=0) & finite['nlls'][fi].all(axis=0)
                for qname, quantile in Q_LEVELS:
                    if qname == 'p90':
                        continue
                    rr = {**ident, 'quantile': qname, 'common_four_arm_finite_n': int(common.sum()),
                          'missing_from_common_four_arm_n': int(subset.sum() - common.sum())}
                    for pi, policy in enumerate(POLICIES):
                        a = float(np.quantile(errors['wcl'][fi, pi, common], quantile, method='linear')) if common.any() else None
                        c = float(np.quantile(errors['nlls'][fi, pi, common], quantile, method='linear')) if common.any() else None
                        rr[policy + '_wcl_error_m'] = a; rr[policy + '_nlls_error_m'] = c
                        rr[policy + '_wcl_minus_nlls_m'] = a - c if a is not None else None
                        rr[policy + '_ordering'] = category(a, c)
                    rr['strict_reversal'] = {rr['frozen_ordering'], rr['refit_ordering']} == {'wcl_lower', 'nlls_lower'}
                    rr['ordering_changed_including_tie'] = rr['frozen_ordering'] != rr['refit_ordering']
                    rankings.append(rr)
        if fi != z:
            unexposed = exposure == 0
            for method in METHODS:
                pred, fin = predictions[method], finite[method]
                for pi, policy in enumerate(POLICIES):
                    same_finite = np.array_equal(fin[fi, pi, unexposed], fin[z, 0, unexposed])
                    good = unexposed & fin[fi, pi] & fin[z, 0]
                    delta = norm(pred[fi, pi, good] - pred[z, 0, good])
                    okay = same_finite and bool(np.all(delta <= ATOL_M))
                    controls.append({**field, 'method': method, 'policy': policy,
                                     'unexposed_scheduled_n': int(unexposed.sum()), 'finite_pairs_n': int(good.sum()),
                                     'finite_status_unchanged': same_finite,
                                     'maximum_position_difference_m': float(delta.max()) if len(delta) else None,
                                     'pass': okay})
                    check_record(checks, name + ':' + method + ':' + policy + ':unexposed_field_' + str(fi), okay)
    status = dict(Counter(np.asarray(r['nlls_status']).ravel().tolist()))
    result = {'arms': arms, 'effects': effects, 'rankings': rankings, 'controls': controls,
              'wcl_diagnostics': diagnostics, 'checks': checks, 'exposure': availability}
    result['block_summary'] = {**base, 'sampled_queries': q, 'fields_including_baseline': f,
                               'scheduled_method_policy_entries': f * 2 * q * 2,
                               'nlls_status_counts': status,
                               'nlls_local_start_failed_total': int(r['nlls_local_failed'].sum()),
                               'nlls_local_start_budget_exhausted_total': int(r['nlls_local_exhausted'].sum()),
                               'full_population_metadata': meta.get('population', {}),
                               'all_block_metadata': meta}
    return result


def budget_comparisons(blocks):
    rows, effects = [], []
    study2 = [(name, b, r, identity(m)) for name, b, r, m in blocks
              if str(identity(m)['study']) in ('2', 'study2', 'study_2')]
    all_blocks = {}
    for name, b, r, m in study2:
        if str(m['budget']).lower() == 'all':
            key = (str(m['map']), str(m['fold']))
            if key in all_blocks:
                raise ValueError('All-budget block duplicated for context ' + str(key))
            all_blocks[key] = (name, b, r, m)
    for name, b, r, m in study2:
        if str(m['budget']).lower() == 'all':
            continue
        if str(m['budget']) != '10':
            raise ValueError('Unexpected limited budget')
        aname, ab, ar, am = all_blocks[(str(m['map']), str(m['fold']))]
        for key in ('source_rows', 'selected_ids', 'selected_mask', 'query_xy_m', 'query_rssi_dbm',
                    'reference_anchors_m', 'field_anchors_m', 'field_D_m', 'field_draw', 'field_target_mask'):
            if not np.array_equal(b[key], ab[key], equal_nan=True):
                raise ValueError('Budget matching failure: ' + name + ':' + key)
        z, az = zero_index(b), zero_index(ab)
        truth = b['query_xy_m']; q = len(truth)
        for fi in range(len(b['field_D_m'])):
            exposure = selected_exposure(b, fi)
            populations = [('full_sample', np.ones(q, bool))]
            if fi != z:
                populations.append(('selected_target_affected', exposure > 0))
            for population, subset in populations:
                ident = {**identity(m), 'limited_block': name, 'all_block': aname,
                         **field_identity(b, fi), 'population': population, 'scheduled_n': int(subset.sum())}
                for method in METHODS:
                    lp, ap = r[method + '_position_m'], ar[method + '_position_m']
                    le, ae = norm(lp - truth[None, None]), norm(ap - truth[None, None])
                    lf, af = np.isfinite(lp).all(axis=-1), np.isfinite(ap).all(axis=-1)
                    for pi, policy in enumerate(POLICIES):
                        pair = subset & lf[fi, pi] & af[fi, pi]
                        quad = pair & lf[z, 0] & af[az, 0]
                        row = {**ident, 'method': method, 'policy': policy,
                               'finite_budget_pairs_n': int(pair.sum()),
                               'missing_budget_pairs_n': int(subset.sum() - pair.sum()),
                               'finite_budget_and_own_zero_quadruples_n': int(quad.sum()),
                               **stats(le[fi, pi, pair], 'limited_error_m_'),
                               **stats(ae[fi, pi, pair], 'all_error_m_'),
                               **paired_change(le[fi, pi, pair], ae[fi, pi, pair], 'all_budget_error_benefit_m_'),
                               **stats(le[z, 0, quad], 'limited_own_zero_error_m_'),
                               **stats(ae[az, 0, quad], 'all_own_zero_error_m_'),
                               **stats(le[fi, pi, quad] - le[z, 0, quad], 'limited_paired_error_penalty_m_'),
                               **stats(ae[fi, pi, quad] - ae[az, 0, quad], 'all_paired_error_penalty_m_'),
                               **stats((le[fi, pi, quad] - le[z, 0, quad]) - (ae[fi, pi, quad] - ae[az, 0, quad]),
                                       'limited_minus_all_error_penalty_m_')}
                        rows.append(row)
                    if fi != z:
                        common = subset & lf[fi].all(axis=0) & af[fi].all(axis=0)
                        row = {**ident, 'method': method, 'common_four_arm_finite_n': int(common.sum()),
                               'missing_from_common_four_arm_n': int(subset.sum() - common.sum()),
                               **stats(le[fi, 0, common] - le[fi, 1, common], 'limited_refit_error_benefit_m_'),
                               **stats(ae[fi, 0, common] - ae[fi, 1, common], 'all_refit_error_benefit_m_'),
                               **stats((ae[fi, 0, common] - ae[fi, 1, common]) - (le[fi, 0, common] - le[fi, 1, common]),
                                       'all_minus_limited_refit_error_benefit_m_')}
                        for label, quantile in Q_LEVELS:
                            for budget, err in [('limited', le), ('all', ae)]:
                                row[budget + '_' + label + '_refit_quantile_benefit_m'] = (
                                    float(np.quantile(err[fi, 0, common], quantile) - np.quantile(err[fi, 1, common], quantile))
                                    if common.any() else None)
                        effects.append(row)
    return rows, effects


def population_table(blocks):
    """One row per eligibility context; limited fits do not duplicate populations."""
    groups = {}
    for name, b, r, metadata in blocks:
        ident = identity(metadata)
        key = tuple(ident[k] for k in ('study', 'map', 'fold'))
        population = metadata.get('population', {})
        if key in groups:
            if groups[key]['_population'] != population:
                raise ValueError('Eligibility population changed across calibration budgets: ' + str(key))
            groups[key]['calibration_context_blocks'] += ',' + name
            continue
        row = {k: ident[k] for k in ('study', 'map', 'fold')}
        row.update({'calibration_context_blocks': name, '_population': population})
        row.update({k: v for k, v in population.items() if isinstance(v, (str, int, float, bool)) or v is None})
        denominator = population.get('test_denominator_n')
        if denominator is not None:
            for quantity in ('eligible_before_duplicate_filter_n', 'eligible_n'):
                numerator = population.get(quantity)
                row[quantity + '_fraction_of_full_test_denominator'] = (
                    numerator / denominator if numerator is not None and denominator else None)
        row['interpretation'] = 'Exact input-population counts; sampled errors and numerical delivery are reported separately.'
        groups[key] = row
    return [{k: v for k, v in row.items() if k != '_population'} for row in groups.values()]


def population_exposure_table(blocks):
    seen = set(); rows = []
    for name, b, r, metadata in blocks:
        ident = identity(metadata)
        key = tuple(ident[k] for k in ('study', 'map', 'fold'))
        if key in seen:
            continue
        seen.add(key); pop = metadata.get('population', {})
        for scope, dict_key, denom_key in [
                ('complete_eligible_pool', 'full_eligible_selected_target_exposure', 'eligible_n'),
                ('fixed_sample', 'sample_selected_target_exposure', 'sample_n')]:
            denominator = pop.get(denom_key)
            for target_ids, counts in pop.get(dict_key, {}).items():
                if denominator is None or sum(counts.values()) != denominator:
                    raise ValueError('Population exposure accounting mismatch: ' + name + ':' + scope)
                for selected_count, count in counts.items():
                    rows.append({k: ident[k] for k in ('study', 'map', 'fold')} | {
                        'scope': scope, 'target_ids': target_ids,
                        'selected_target_count': int(selected_count), 'count': int(count),
                        'denominator': int(denominator),
                        'fraction': count / denominator if denominator else None})
    return rows


def calibration_cost_table(blocks):
    rows = []
    for name, b, r, metadata in blocks:
        row = {'block': name, **identity(metadata)}
        row.update({k: v for k, v in metadata.get('calibration_cost', {}).items()
                    if isinstance(v, (str, int, float, bool)) or v is None})
        if 'cal_receiver_ids' in b:
            row['calibrated_receiver_count'] = len(b['cal_receiver_ids'])
        rows.append(row)
    return rows


def direction_ranges(rows, keys, metrics):
    groups = defaultdict(list)
    for row in rows:
        if row['D_m'] > 0:
            groups[tuple(row.get(k) for k in keys)].append(row)
    output = []
    for values, group in sorted(groups.items(), key=lambda item: str(item[0])):
        row = dict(zip(keys, values)); draws = [int(g['draw']) for g in group]
        if len(draws) != len(set(draws)):
            raise ValueError('Directions duplicated within a descriptive summary group')
        row.update({'direction_count': len(group), 'directions': ','.join(map(str, sorted(draws))),
                    'aggregation': 'descriptive median and range across specified fields; not independent replications'})
        for metric in metrics:
            values = [float(g[metric]) for g in group if g.get(metric) is not None]
            row[metric + '_estimable_directions'] = len(values)
            for suffix, fun in [('median', np.median), ('min', np.min), ('max', np.max)]:
                row[metric + '_direction_' + suffix] = float(fun(values)) if values else None
        output.append(row)
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=ROOT)
    ap.add_argument('--metadata', type=Path)
    args = ap.parse_args(); root = args.root.resolve()
    receipt_path = root / 'receipts/PRIMARY_RUN_RECEIPT.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('status') != 'COMPLETE':
        raise ValueError('Complete primary receipt required before analysis')
    lock_path = root / 'protocol/EXECUTION_LOCK.json'
    if sha(lock_path) != receipt['lock_sha256']:
        raise ValueError('Primary lock identity changed')
    lock = json.loads(lock_path.read_text())
    for name, digest in lock['bound_files'].items():
        if sha(root / name) != digest:
            raise ValueError('Bound input/code changed: ' + name)
    metadata_path = args.metadata
    metadata = json.loads(metadata_path.read_text()) if metadata_path else None
    if metadata is not None:
        metadata = metadata['blocks'] if 'blocks' in metadata else metadata
    metadata_hashes = {}
    blocks = []; combined = defaultdict(list); summaries = []
    inputs = sorted((root / 'inputs/blocks').glob('*.npz'))
    if len(inputs) != receipt['blocks'] or len(inputs) != len(receipt['output_arrays']):
        raise ValueError('Primary block count is incomplete')
    for path in inputs:
        result_path = root / 'results/arrays' / path.name
        if sha(result_path) != receipt['output_arrays'][path.name]:
            raise ValueError('Result array changed: ' + path.name)
        if metadata is None:
            meta_path = path.with_suffix('.json')
            meta = json.loads(meta_path.read_text())
            metadata_hashes[str(meta_path.relative_to(root))] = sha(meta_path)
        else:
            if path.stem not in metadata:
                raise ValueError('Missing explicit block metadata: ' + path.stem)
            meta = metadata[path.stem]
            metadata_hashes[str(metadata_path)] = sha(metadata_path)
        b, r = read_npz(path), read_npz(result_path)
        block = analyze_block(path.stem, b, r, meta)
        summaries.append(block.pop('block_summary'))
        for key, rows in block.items():
            combined[key].extend(rows)
        blocks.append((path.stem, b, r, meta))
    combined['budget_comparisons'], combined['budget_calibration_effects'] = budget_comparisons(blocks)
    combined['population_availability'] = population_table(blocks)
    combined['population_exposure'] = population_exposure_table(blocks)
    combined['calibration_costs'] = calibration_cost_table(blocks)
    keys = ['study', 'map', 'fold', 'budget', 'replicate', 'target_ids', 'D_m', 'population', 'method']
    combined['effect_direction_ranges'] = direction_ranges(combined['effects'], keys, [
        'refit_error_benefit_m_p50_quantile_difference', 'refit_error_benefit_m_p95_quantile_difference',
        'refit_error_benefit_m_paired_difference_p50', 'refit_error_benefit_m_paired_difference_mean',
        'refit_error_benefit_m_help_fraction_of_finite_pairs', 'refit_error_benefit_m_harm_fraction_of_finite_pairs',
        'direct_geometry_m_p50', 'additional_refit_m_p50', 'net_refit_m_p50',
        'refit_sensitivity_reduction_m_help_fraction_of_finite_pairs'])
    combined['arm_direction_ranges'] = direction_ranges(combined['arms'], keys + ['policy'], [
        'error_m_p50', 'error_m_p90', 'error_m_p95', 'error_m_mean', 'error_m_max', 'finite_n'])
    combined['budget_direction_ranges'] = direction_ranges(combined['budget_comparisons'], keys + ['policy'], [
        'all_budget_error_benefit_m_p50_quantile_difference', 'all_budget_error_benefit_m_p95_quantile_difference',
        'all_budget_error_benefit_m_paired_difference_p50', 'limited_minus_all_error_penalty_m_p50'])
    out = root / 'results/analysis'; out.mkdir(parents=True, exist_ok=True)
    for name, rows in combined.items():
        write_csv(out / (name.upper() + '.csv'), rows)
    exceptions = []
    for path in sorted((root / 'results/shards').glob('*.json')):
        shard = json.loads(path.read_text())
        exceptions.extend([{'block': shard['block'], **e} for e in shard.get('exceptions', [])])
    failed = [row for row in combined['checks'] if not row['pass']]
    ranking_tally = defaultdict(Counter)
    for row in combined['rankings']:
        group = (row['map'], row['population'], row['quantile'])
        ranking_tally[group]['specified_fields'] += 1
        ranking_tally[group]['strict_reversals'] += int(row['strict_reversal'])
        ranking_tally[group]['ordering_changes_including_tie'] += int(row['ordering_changed_including_tie'])
        ranking_tally[group]['unestimable_fields'] += int(row['frozen_ordering'] == 'not_estimable' or row['refit_ordering'] == 'not_estimable')
    summary = {
        'status': 'COMPLETE_WITH_CHECK_FAILURES' if failed else 'COMPLETE',
        'analysis_code_sha256': sha(__file__), 'primary_receipt_sha256': sha(receipt_path),
        'execution_lock_sha256': sha(lock_path), 'block_metadata_sha256': metadata_hashes,
        'quantile_method': 'numpy.quantile linear interpolation',
        'numerical_tie_tolerance': {'absolute_m': ATOL_M, 'relative': RTOL, 'formula': '1e-6 + 1e-12 * max(abs(a),abs(b))'},
        'estimands': {
            'absolute_error': 'Euclidean distance from prediction to recorded query reference; finite-arm conditional distribution.',
            'refit_error_benefit': 'e_frozen - e_refit on finite paired predictions. Positive means lower error under refit.',
            'quantile_difference': 'Q(e_frozen) - Q(e_refit) on the identical finite paired population.',
            'median_paired_difference': 'median(e_frozen - e_refit), separately calculated; generally differs from the difference of medians.',
            'direct_geometry': 'norm(x_frozen - x_own_zero)',
            'additional_refit': 'norm(x_refit - x_frozen)',
            'net_refit': 'norm(x_refit - x_own_zero); these magnitudes are not additive.',
            'affected_population': 'Selected receiver list intersects field target set; fixed from input identities, never fitted weights or results.',
            'all_budget_error_benefit': 'e_10 - e_all on matched source rows and finite budget pairs.',
            'own_zero_penalty': 'e_condition - e_own_zero within each budget; positive means worse error than its own zero-map baseline.'},
        'inference_limits': [
            'All reported field, direction, fold and calibration-realization ranges are descriptive.',
            'Repeated messages, directions, overlapping calibration pools, and limited-budget realizations are not independent deployments.',
            'All-budget fits are retained once per fold; pairwise contrasts against three limited fits do not create three independent all-budget experiments.',
            'Full held-out population eligibility is distinct from sampled-cohort numerical delivery and error distributions.',
            'Every finite-mask exclusion is accompanied by the scheduled/finite count; failures remain in original arrays and exception records.',
            'Primary finite-algorithm outputs are not replaced with numerical audit results; no global optimality claim is made.'],
        'blocks': summaries,
        'checks': {'total': len(combined['checks']), 'failed': failed},
        'exceptions': exceptions,
        'exception_count_matches_primary_receipt': len(exceptions) == receipt['exceptions'],
        'ranking_summary': [{'map': k[0], 'population': k[1], 'quantile': k[2], **dict(v)} for k, v in ranking_tally.items()],
        'tables': {k: {'rows': len(v), 'filename': k.upper() + '.csv', 'sha256': sha(out / (k.upper() + '.csv'))} for k, v in combined.items()},
        'ecdf_reconstruction': 'Every empirical error/exceedance curve is reconstructable from retained prediction arrays and input reference positions. No independent pooled ECDF is asserted.',
        'figure_proposals': [
            'Matched frozen/refit error and displacement panels by estimator, magnitude and target set; display the four specified directions.',
            'Spatial-fold calibration-budget panels displaying each limited-budget realization, the one all-budget fit, and each own-zero baseline.',
            'WCL target-weight mass versus prediction movement as mechanism evidence; label as descriptive, not causal regression.']}
    write_json(out / 'SUMMARY.json', summary)
    print(json.dumps({'status': summary['status'], 'blocks': len(blocks), 'check_failures': len(failed),
                      'tables': len(combined), 'output': str(out)}, indent=2))
    if failed or not summary['exception_count_matches_primary_receipt']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
