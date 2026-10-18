"""Descriptive reporting of the completed locked finite-diagnostic sweep."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

P=Path(__file__).resolve().parent
d=pd.read_csv(P/'FINITE_FIELD_SUMMARIES.csv')
metrics=['target_grid_variation_db2_p50','target_variation_upper_bound_db2_p50',
         'original_zero_map_nlls_target_gradient_norm_db2_per_m_p50',
         'original_zero_map_nlls_target_penalty_db2_p50']
rows=[]
for (t,D,policy),g in d[d.D_m>0].groupby(['target_count','D_m','policy']):
    entry={'target_count':int(t),'D_m':float(D),'policy':policy,
           'fields':len(g),'exposed_queries_per_field':int(g.exposed_queries.iloc[0])}
    for c in metrics:
        for suffix,fn in [('direction_median',np.median),('direction_min',np.min),('direction_max',np.max)]:
            entry[c+'_'+suffix]=float(fn(g[c]))
    rows.append(entry)
pd.DataFrame(rows).to_csv(P/'FINITE_DIRECTION_SUMMARIES.csv',index=False)
f=d[(d.policy=='frozen')&(d.D_m>0)].set_index('field_index')
r=d[(d.policy=='refit')&(d.D_m>0)].set_index('field_index')
a=np.load(P/'FINITE_POINT_DIAGNOSTICS.npz')
info={'aggregation':'Within each field: median over target-exposed rows. Then median and range over the four fields; no pooling as independent replications.',
      'refit_lowers_field_median_count_of_24':{c:int((r[c]<f[c]).sum()) for c in metrics},
      'outside_K_field_query_positions':{str(name):int(np.count_nonzero(~a['candidate_inside_K'][:,:,j])) for j,name in enumerate(a['candidate_names'])},
      'undefined_target_derivative_states':int(a['target_derivative_undefined'].sum()),
      'undefined_unchanged_derivative_states':int(a['unchanged_derivative_undefined'].sum()),
      'region_span_m':(a['region_upper_m']-a['region_lower_m']).tolist(),
      'global_optimum_or_position_certificate':False,
      'new_optimizer_calls':0}
(P/'FINITE_INTERPRETATION.json').write_text(json.dumps(info,indent=2)+'\n')
def value(t,D,p,key):
    return next(x[key] for x in rows if x['target_count']==t and x['D_m']==D and x['policy']==p)
gkey='original_zero_map_nlls_target_gradient_norm_db2_per_m_p50_direction_median'
pkey='original_zero_map_nlls_target_penalty_db2_p50_direction_median'
vkey='target_grid_variation_db2_p50_direction_median'
report=f'''FINITE CALIBRATION-MECHANISM DIAGNOSTICS — 16 OCTOBER 2026

Status: completed diagnostic follow-up; no original output or estimator changed.
Scope: primary catalogue-map Study 1, 512 original held-out messages, all 24
positive fields and the zero reference, frozen/refit. There are 25,600 stored
field/policy/query rows, including the two identical zero-policy arms. New
optimization calls: zero. Positive one-target fields expose 207 queries;
two-target fields expose 371. Unexposed rows remain explicit controls.

The candidate region K is the bounding rectangle of calibration-reference
positions, expanded by 1 km on every side. It was fixed before diagnostic
computation and does not use localization outcomes or query-reference positions.
Its sides span {info['region_span_m'][0]:.3f} by {info['region_span_m'][1]:.3f} m.
The grid is 21 by 21, with endpoints included. Its objective range is a sampled
range, not the exact supremum. Receiver-distance interval formulas give a
separate analytical upper bound, evaluated in float64 without directed-rounding
certification. Wide bounds are retained; neither the region nor grid was tuned.

RESULTS

At the same original zero-map NLLS candidate positions, refitting reduces the
field median targeted-gradient norm in 22 of the 24 positive fields. In the
two-target 5-km conditions, the median across four field medians changes from
{value(2,5000.,'frozen',gkey):.5f} to {value(2,5000.,'refit',gkey):.5f} dB^2/m.
The corresponding targeted squared-residual contribution changes from
{value(2,5000.,'frozen',pkey):.2f} to {value(2,5000.,'refit',pkey):.2f} dB^2.
These comparisons evaluate both policies at exactly the same candidate points;
they do not attribute a changed point's geometric Jacobian to intercept fitting.

The broad-region result is different. Refitting lowers the field median sampled
target-objective variation in only 6/24 positive fields. In the two-target
5-km case, the direction-median sampled variation is
{value(2,5000.,'frozen',vkey):.2f} dB^2 frozen and {value(2,5000.,'refit',vkey):.2f} dB^2 refitted.
These sampled values do not establish the ordering of the exact suprema.
They do demonstrate that the target penalty still varies substantially on
this declared finite region: the observed location-specific gradient reduction
is not evidence of a uniformly constant target objective throughout K.

At 1 km with two targets, direction-median gradient norms are
{value(2,1000.,'frozen',gkey):.5f} and {value(2,1000.,'refit',gkey):.5f} dB^2/m.
All four direction outcomes and all rows are retained rather than interpreting
one aggregate as a monotone finite-displacement law.

There are 44 frozen and 4 refitted field/query primary positions outside K;
all original zero-map positions lie inside. These are repeated field/query
counts, not independent messages or an optimized-algorithm failure rate. The
finite K proposition cannot be applied to an outside position. The three
candidate positions have no receiver-coordinate derivative singularities.

INTERPRETATION

The diagnostics support a finite local residual-weighted-force reduction at
the tested candidate positions, particularly in the severe two-target fields.
They do not establish global positional confinement at 5 km, a small objective
variation over the entire geographic region, a unique solution, or small
absolute localization error. Objective variation and receiver interval bounds
are independent of the selected optimizer branch. Pointwise gradient summaries
remain specific to the retained baseline/frozen/refitted candidate positions
and must accompany the separate candidate-pool sensitivity analysis.

The finite objective lemma requires a known optimization-error bound eta and,
for a positional conclusion, a valid objective-separation/growth condition.
Neither is supplied by these reductions. Independent removal-objective solves
are owned by the baseline/numerical workstream. Distances to a found competitive
removal pool must not be described as distances to all true global minimizers.

ARTIFACTS AND VERIFICATION

FINITE_DIAGNOSTIC_PROTOCOL.json and FINITE_DIAGNOSTIC_LOCK.json bind the inputs,
code, region and schedule before this new reduction. The receipt records zero
optimizer calls, exact control behavior, maximum residual-identity discrepancy
4.62e-14 dB, and recomputed selected-objective discrepancy 5.01e-12 dB^2.
Synthetic derivative, interval-bound and fitting-functional checks are separate
from the mathematical proof. They do not numerically prove its conclusions.

Active full proof: THEORY_EXTENSION_v2.tex. The original THEORY_EXTENSION.tex
is retained because it was protocol-bound; v2 corrects only a units sentence.
ROOT_THEORY_REVIEW.json records an independent root-agent proof read, not
external human peer review. THEORY_MAIN_FRAGMENT.tex provides compact prose
for integration; no manuscript/source file was edited here.

Tables: FINITE_FIELD_QUERY_DIAGNOSTICS.csv, FINITE_FIELD_SUMMARIES.csv,
FINITE_DIRECTION_SUMMARIES.csv. FINITE_POINT_DIAGNOSTICS.npz stores gradients,
target/unchanged objectives, candidate coordinates, region flags and metadata.
All reported direction medians summarize within-field exposed-row medians;
they are descriptive and are not confidence limits or independent-deployment
replications.
'''
(P/'FINITE_MECHANISM_REPORT.txt').write_text(report)
receipt={'producer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'inputs':{x:hashlib.sha256((P/x).read_bytes()).hexdigest() for x in ['FINITE_FIELD_SUMMARIES.csv','FINITE_POINT_DIAGNOSTICS.npz']},
         'outputs':{x:hashlib.sha256((P/x).read_bytes()).hexdigest() for x in ['FINITE_DIRECTION_SUMMARIES.csv','FINITE_INTERPRETATION.json','FINITE_MECHANISM_REPORT.txt']}}
(P/'FINITE_REPORT_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(info))
