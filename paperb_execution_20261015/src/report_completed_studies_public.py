#!/usr/bin/env python3
"""Generate scientific figures and descriptive tables; submission prose excluded.

Requires the complete locked analysis. This script does not change primary
predictions, recompute calibration, replace numerically audited estimates, or
choose a favourable subset of fields. Its outputs are reporting artifacts.
"""
from pathlib import Path
import csv
import json
from collections import defaultdict
import hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / 'results/analysis'
OUT = ROOT / 'results/report'


def load_csv(name):
    with (A / name).open(newline='') as stream:
        return list(csv.DictReader(stream))


def val(row, key):
    s = row.get(key, '')
    return float(s) if s not in ('', None) else None


def selected(rows, **criteria):
    return [r for r in rows if all(str(r[k]) == str(v) for k, v in criteria.items())]


def median_range(values):
    values = [float(x) for x in values if x is not None]
    return {'n': len(values), 'median': float(np.median(values)) if values else None,
            'min': min(values) if values else None, 'max': max(values) if values else None}


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader(); writer.writerows(rows)


def fmt(x, digits=1):
    return '--' if x is None else f'{float(x):.{digits}f}'


def tex(s):
    return str(s).replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')


def rangetext(s, digits=1):
    return fmt(s['median'], digits) + ' [' + fmt(s['min'], digits) + ', ' + fmt(s['max'], digits) + ']'


def base_table(arms, study):
    rows = []
    for r in selected(arms, study=study, D_m='0.0', policy='frozen', population='full_sample'):
        row = {k: r[k] for k in ('block', 'study', 'map', 'fold', 'budget', 'replicate', 'method', 'scheduled_n', 'finite_n')}
        row.update({'P50_m': val(r, 'error_m_p50'), 'P90_m': val(r, 'error_m_p90'),
                    'P95_m': val(r, 'error_m_p95'), 'mean_m': val(r, 'error_m_mean'), 'max_m': val(r, 'error_m_max')})
        rows.append(row)
    return rows


def main():
    summary = json.loads((A / 'SUMMARY.json').read_text())
    if summary['status'] != 'COMPLETE' or summary['checks']['failed']:
        raise RuntimeError('Complete passing analysis required')
    for table in summary['tables'].values():
        if hashlib.sha256((A / table['filename']).read_bytes()).hexdigest() != table['sha256']:
            raise RuntimeError('Analysis table identity changed: ' + table['filename'])
    numerical_receipt = json.loads((ROOT / 'receipts/NUMERICAL_AUDIT_RECEIPT.json').read_text())
    numerical = json.loads((ROOT / 'receipts/INDEPENDENT_NUMERICAL_AUDIT_INTERPRETATION.json').read_text())
    if numerical_receipt['status'] != 'COMPLETE' or numerical['status'] != 'PASS':
        raise RuntimeError('Completed independent numerical audit required for final reporting')
    OUT.mkdir(parents=True, exist_ok=True)
    arms, effects = load_csv('ARMS.csv'), load_csv('EFFECTS.csv')
    rankings, costs = load_csv('RANKINGS.csv'), load_csv('CALIBRATION_COSTS.csv')
    budgets = load_csv('BUDGET_COMPARISONS.csv')
    baseline1, baseline2 = base_table(arms, 'study1'), base_table(arms, 'study2')
    write_csv(OUT / 'STUDY1_BASELINES.csv', baseline1)
    write_csv(OUT / 'STUDY2_BASELINES.csv', baseline2)
    figdata = []
    for method in ('wcl', 'nlls'):
        for policy in ('frozen', 'refit'):
            for d in (0., 100., 1000., 5000.):
                rows = selected(arms, study='study1', map='official32_minus71', population='full_sample',
                                method=method, policy=policy, D_m=str(d))
                if d > 0:
                    rows = selected(rows, target_ids='14,69')
                assert len(rows) == (1 if d == 0 else 4)
                for metric in ('p50', 'p95'):
                    stat = median_range([val(r, 'error_m_' + metric) for r in rows])
                    figdata.append({'method': method, 'policy': policy, 'D_m': d, 'error_quantile': metric,
                                    'specified_fields_n': len(rows), 'field_median_m': stat['median'],
                                    'field_min_m': stat['min'], 'field_max_m': stat['max'],
                                    'scheduled_queries_per_field': 512,
                                    'minimum_finite_queries': min(int(r['finite_n']) for r in rows)})
    write_csv(OUT / 'TRANSFER_FIGURE_DATA.csv', figdata)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42, 'ps.fonttype': 42})
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.7), layout='constrained')
    colors = {'wcl': '#1764a3', 'nlls': '#be4b23'}
    for ax, metric, title in zip(axes, ('p50', 'p95'), ('Median error', '95th-percentile error')):
        for method in ('wcl', 'nlls'):
            for policy in ('frozen', 'refit'):
                rows = [r for r in figdata if r['method'] == method and r['policy'] == policy and r['error_quantile'] == metric]
                rows.sort(key=lambda r: r['D_m']); x = np.arange(4)
                y = [r['field_median_m'] for r in rows]
                lo = [r['field_min_m'] for r in rows]; hi = [r['field_max_m'] for r in rows]
                label = ('WCL' if method == 'wcl' else 'RSS-NLS') + ', ' + policy
                ax.plot(x, y, color=colors[method], linestyle='--' if policy == 'frozen' else '-',
                        marker='o' if policy == 'frozen' else 's', markersize=4, linewidth=1.6, label=label)
                ax.fill_between(x, lo, hi, color=colors[method], alpha=.11 if policy == 'frozen' else .20,
                                linewidth=0, hatch='//' if policy == 'frozen' else None)
        ax.set_title(title); ax.set_xticks(np.arange(4), ['0', '100', '1000', '5000'])
        ax.set_xlabel('Coordinate displacement (m; discrete conditions)'); ax.set_ylabel('Position error (m)')
        ax.grid(axis='y', alpha=.2); ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False, loc='upper left', fontsize=8)
    fig.savefig(OUT / 'calibration_transfer_results.pdf')
    fig.savefig(OUT / 'calibration_transfer_results.png', dpi=200)
    plt.close(fig)
    foldtable = []
    for b in baseline2:
        for policy in ('frozen', 'refit'):
            row = {k: b[k] for k in ('block', 'fold', 'budget', 'replicate', 'method')}
            row.update({'policy': policy, 'own_zero_P50_m': b['P50_m'], 'own_zero_P95_m': b['P95_m']})
            for d in (1000., 5000.):
                rr = selected(arms, block=b['block'], method=b['method'], policy=policy,
                              population='full_sample', D_m=str(d))
                assert len(rr) == 4
                for metric in ('p50', 'p95'):
                    ss = median_range([val(r, 'error_m_' + metric) for r in rr])
                    for k in ('median', 'min', 'max'):
                        row[f'D{int(d)}_{metric}_direction_{k}_m'] = ss[k]
            foldtable.append(row)
    write_csv(OUT / 'BUDGET_FOLD_TABLE.csv', foldtable)
    interpreted = {'status': 'DESCRIPTIVE_RESULTS_PRIMARY_FINITE_ALGORITHM',
                   'primary_run': json.loads((ROOT / 'receipts/PRIMARY_RUN_RECEIPT.json').read_text()),
                   'study1_baselines': baseline1, 'study2_baselines': baseline2,
                   'study1_rankings': summary['ranking_summary'],
                   'study1_effects': [], 'study2_effects': [], 'study2_budget_comparisons': [],
                   'numerical_audit_status': 'COMPLETE; independent integrity and interpretation PASS; primary predictions retained.',
                   'numerical_audit': numerical}
    for study, destination in [('study1', 'study1_effects'), ('study2', 'study2_effects')]:
        grouped = defaultdict(list)
        for r in selected(effects, study=study):
            key = tuple(r[k] for k in ('map', 'fold', 'budget', 'replicate', 'target_ids', 'D_m', 'population', 'method'))
            grouped[key].append(r)
        for key, rows in grouped.items():
            item = dict(zip(('map', 'fold', 'budget', 'replicate', 'target_ids', 'D_m', 'population', 'method'), key))
            for metric in ('refit_error_benefit_m_p50_quantile_difference', 'refit_error_benefit_m_p95_quantile_difference',
                           'refit_error_benefit_m_paired_difference_p50', 'refit_error_benefit_m_paired_difference_mean',
                           'refit_error_benefit_m_help_fraction_of_finite_pairs', 'refit_error_benefit_m_harm_fraction_of_finite_pairs',
                           'direct_geometry_m_p50', 'net_refit_m_p50', 'refit_sensitivity_reduction_m_help_fraction_of_finite_pairs'):
                item[metric] = median_range([val(r, metric) for r in rows])
            item['specified_fields_n'] = len(rows)
            item['p50_refit_benefit_positive_fields'] = sum(val(r, 'refit_error_benefit_m_p50_quantile_difference') > 0 for r in rows)
            item['p95_refit_benefit_positive_fields'] = sum(val(r, 'refit_error_benefit_m_p95_quantile_difference') > 0 for r in rows)
            interpreted[destination].append(item)
    for fold in ('SW', 'SE', 'NW', 'NE'):
        for method in ('wcl', 'nlls'):
            for d in ('1000.0', '5000.0'):
                for policy in ('frozen', 'refit'):
                    rr = selected(budgets, fold=fold, method=method, D_m=d, policy=policy, population='full_sample')
                    assert len(rr) == 12
                    interpreted['study2_budget_comparisons'].append({'fold': fold, 'method': method, 'D_m': float(d),
                        'policy': policy, 'specified_direction_and_fit_pairs_n': 12,
                        'p50_all_budget_benefit_m': median_range([val(r, 'all_budget_error_benefit_m_p50_quantile_difference') for r in rr]),
                        'p95_all_budget_benefit_m': median_range([val(r, 'all_budget_error_benefit_m_p95_quantile_difference') for r in rr]),
                        'interpretation': 'Descriptive range over four directions and three limited-fit contrasts; common all-fit reused, not independent replication.'})
    (OUT / 'COMPUTED_INTERPRETATION.json').write_text(json.dumps(interpreted, indent=2) + '\n')

    print(json.dumps({'status':'PUBLIC_REPORT_CREATED','scope':'Figures and machine-readable tables only; no submission prose.'}))

if __name__ == '__main__':
    main()
