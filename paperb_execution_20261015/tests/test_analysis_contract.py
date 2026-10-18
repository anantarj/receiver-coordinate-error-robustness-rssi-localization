"""Synthetic-only checks of descriptive estimands and failure accounting."""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from analyze_studies import analyze_block, budget_comparisons, direction_ranges, paired_change, stats


def fixture():
    q, f = 4, 3
    b = {'source_rows': np.arange(q), 'query_xy_m': np.zeros((q, 2)),
         'selected_ids': np.array([[1, 2, 3], [1, 2, 3], [1, 2, 3], [2, 3, 4]]),
         'selected_mask': np.ones((q, 3), bool),
         'query_rssi_dbm': np.zeros((q, 3)),
         'reference_anchors_m': np.zeros((4, 2)),
         'field_anchors_m': np.zeros((f, 4, 2)),
         'field_D_m': np.array([0., 100., 100.]), 'field_draw': np.array([-1, 0, 1]),
         'field_target_count': np.array([0, 1, 1]),
         'field_target_mask': np.array([[False] * 4, [True, False, False, False], [True, False, False, False]]),
         'reference_intercepts_dbm': np.zeros(4),
         'field_refit_intercepts_dbm': np.array([[0.] * 4, [1., 0., 0., 0.], [1., 0., 0., 0.]])}
    pos = np.zeros((f, 2, q, 2)); pos[:, :, :, 0] = [.5, .5, .5, 2.]
    wcl = pos.copy(); nlls = pos.copy()
    wcl[1:, 0, :3, 0] = [1., 2., 100.]
    wcl[1:, 1, :3, 0] = [0., 98., 99.]
    nlls[1:, 0, :3, 0] = [4., 3., 2.]
    nlls[1:, 1, :3, 0] = [0., 0., 0.]
    nlls[2, 1, 1] = np.nan
    r = {k: b[k].copy() for k in ('source_rows', 'field_D_m', 'field_draw', 'field_target_count')}
    r.update({'query_indices': np.arange(q), 'wcl_position_m': wcl, 'nlls_position_m': nlls,
              'nlls_finite': np.isfinite(nlls).all(axis=-1),
              'nlls_status': np.where(np.isfinite(nlls).all(axis=-1), 'finite', 'synthetic_failure'),
              'nlls_local_failed': np.zeros((f, 2, q), int),
              'nlls_local_exhausted': np.zeros((f, 2, q), int),
              'wcl_target_mass': np.zeros((f, 2, q)),
              'wcl_effective_weight_count': np.ones((f, 2, q))})
    m = {'identity': {'study': 1, 'map': 'synthetic', 'fold': None, 'budget': 'all', 'replicate': None},
         'population': {'eligible_n': 40, 'sample_n': 4}}
    return b, r, m


def run():
    checks = []
    def check(name, value):
        assert value, name
        checks.append({'name': name, 'pass': True})
    d = paired_change(np.array([1., 2., 100.]), np.array([0., 98., 99.]))
    check('difference_of_medians_is_distinct_from_median_paired_difference',
          d['p50_quantile_difference'] == -96. and d['paired_difference_p50'] == 1.)
    check('paired_help_harm_denominators', d['help_count'] == 2 and d['harm_count'] == 1 and d['tie_count'] == 0)
    t = paired_change(np.array([1., 1.]), np.array([1. + 1e-7, 1. - 1e-7]))
    check('numerical_ties', t['tie_count'] == 2)
    check('empty_population_retained', stats(np.array([]))['p95'] is None)
    b, r, m = fixture(); out = analyze_block('fixture', b, r, m)
    check('zero_and_unexposed_controls', all(c['pass'] for c in out['checks']))
    row = next(x for x in out['effects'] if x['method'] == 'nlls' and x['field_index'] == 2 and x['population'] == 'selected_target_affected')
    check('nonfinite_pair_explicitly_retained', row['scheduled_n'] == 3 and row['finite_frozen_refit_pairs_n'] == 2 and row['missing_frozen_refit_pairs_n'] == 1 and row['frozen_only_finite_n'] == 1)
    row = next(x for x in out['effects'] if x['method'] == 'wcl' and x['field_index'] == 1 and x['population'] == 'selected_target_affected')
    check('own_baseline_movement', row['direct_geometry_m_p50'] == 1.5 and row['additional_refit_m_p50'] == 1. and row['net_refit_m_p50'] == 97.5)
    check('affected_population_is_selected_target_identity', row['scheduled_n'] == 3)
    rr = next(x for x in out['rankings'] if x['quantile'] == 'p50' and x['field_index'] == 1 and x['population'] == 'selected_target_affected')
    check('same_four_arm_population_ranking_reversal', rr['strict_reversal'] and rr['frozen_ordering'] == 'wcl_lower' and rr['refit_ordering'] == 'nlls_lower')
    mm = {'identity': {'study': 2, 'map': 'synthetic', 'fold': 'SW', 'budget': 10, 'replicate': 0}}
    am = {'identity': {'study': 2, 'map': 'synthetic', 'fold': 'SW', 'budget': 'all', 'replicate': None}}
    ar = {k: v.copy() for k, v in r.items()}
    ar['wcl_position_m'][0, :, :3, 0] = 10.
    rows, effects = budget_comparisons([('limited', b, r, mm), ('all', b, ar, am)])
    row = next(x for x in rows if x['method'] == 'wcl' and x['field_index'] == 1 and x['population'] == 'selected_target_affected' and x['policy'] == 'frozen')
    check('budget_own_baselines_not_reused_across_contexts', row['limited_own_zero_error_m_p50'] == .5 and row['all_own_zero_error_m_p50'] == 10. and row['limited_minus_all_error_penalty_m_p50'] == 9.5)
    keys = ['study', 'map', 'fold', 'budget', 'replicate', 'target_ids', 'D_m', 'population', 'method']
    ranges = direction_ranges(out['effects'], keys, ['direct_geometry_m_p50'])
    check('directions_descriptive_not_pooled', len(ranges) == 4 and all(x['direction_count'] == 2 for x in ranges))
    with tempfile.TemporaryDirectory(prefix='paperb_analysis_fixture_') as tmp:
        temp = Path(tmp)
        for d in ('inputs/blocks', 'results/arrays', 'results/shards', 'protocol', 'receipts'):
            (temp / d).mkdir(parents=True)
        bound = {}; outputs = {}
        for name, pred, meta in [('limited', r, mm), ('all', ar, am)]:
            inp = temp / 'inputs/blocks' / (name + '.npz'); np.savez(inp, **b)
            met = inp.with_suffix('.json'); met.write_text(json.dumps(meta))
            result = temp / 'results/arrays' / (name + '.npz'); np.savez(result, **pred)
            for path in (inp, met):
                bound[str(path.relative_to(temp))] = hashlib.sha256(path.read_bytes()).hexdigest()
            outputs[result.name] = hashlib.sha256(result.read_bytes()).hexdigest()
        lock = temp / 'protocol/EXECUTION_LOCK.json'; lock.write_text(json.dumps({'bound_files': bound}))
        primary = {'status': 'COMPLETE', 'lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
                   'blocks': 2, 'output_arrays': outputs, 'exceptions': 0}
        (temp / 'receipts/PRIMARY_RUN_RECEIPT.json').write_text(json.dumps(primary))
        proc = subprocess.run([sys.executable, str(ROOT / 'src/analyze_studies.py'), '--root', str(temp)],
                              capture_output=True, text=True)
        check('full_analysis_cli_synthetic_only', proc.returncode == 0)
        summary = json.loads((temp / 'results/analysis/SUMMARY.json').read_text())
        check('complete_outputs_and_unique_population_context', summary['status'] == 'COMPLETE'
              and summary['tables']['population_availability']['rows'] == 1
              and summary['tables']['budget_comparisons']['rows'] == 20)
    record = {'status': 'PASS', 'scope': 'Synthetic estimand and failure-accounting tests only; no scientific outcomes loaded.',
              'analysis_sha256': hashlib.sha256((ROOT / 'src/analyze_studies.py').read_bytes()).hexdigest(),
              'checks': checks}
    dest = ROOT / 'receipts/ANALYSIS_CONTRACT_AUDIT.json'; dest.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    run()
