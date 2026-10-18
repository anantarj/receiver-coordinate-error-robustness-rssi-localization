"""Separate calibration-effect and movement claims from estimator-ranking claims."""
import argparse,json
from collections import Counter
import pandas as pd
from common import HERE,sign,bounds_sign,writej,sha

KEYS=['block','field_index','population','quantile','band_db2']

def run():
    ap=argparse.ArgumentParser();ap.add_argument('--enhanced',action='store_true');args=ap.parse_args()
    p=HERE/('results/candidates_enhanced' if args.enhanced else 'results/candidates')
    effect=pd.read_csv(p/'CALIBRATION_EFFECT_ENVELOPES.csv');witness=pd.read_csv(p/'EXPLICIT_BRANCH_WITNESSES.csv')
    ranking=pd.read_csv(p/'RANKING_ENVELOPES.csv');move=pd.read_csv(p/'BASELINE_MOVEMENT_ENVELOPES.csv')
    wg={key:g for key,g in witness.groupby(KEYS,dropna=False)}
    lookup={tuple(row[k] for k in KEYS):row for _,row in ranking.iterrows()}
    rows=[]
    for _,row in effect.iterrows():
        key=tuple(row[k] for k in KEYS);rr=lookup[key]
        base=row.to_dict();primary=sign(rr.frozen_primary_nlls_m,rr.refit_primary_nlls_m)
        interval_sign=bounds_sign(row.found_pool_lower_m,row.found_pool_upper_m)
        witnesses=wg[key]
        changed=[]
        for _,w in witnesses.iterrows():
            if sign(w.frozen_nlls_m,w.refit_nlls_m)!=primary:changed.append(w)
        if bool(row.identical_policy_numerical_inputs):category='invariant_zero_by_identical_inputs'
        elif interval_sign in ['positive','negative','numerical_tie']:category='invariant_sign_over_found_pools'
        elif any(str(w.rule).startswith('truth_independent') for w in changed):category='branch_sensitive_demonstrated_truth_independent_rule'
        elif any(w.exact_input_consistency_conflict_ids==0 for w in changed):category='branch_sensitive_demonstrated_consistent_reference_scored_assignment'
        elif changed:category='unresolved_with_unconstrained_sign_change_only'
        else:category='unresolved_without_prescribed_sign_change_witness'
        base.update({'primary_sign':primary,'pool_interval_sign':interval_sign,'effect_classification':category,'sign_change_witnesses':len(changed),'truth_independent_sign_change_witnesses':sum(str(w.rule).startswith('truth_independent') for w in changed)})
        rows.append(base)
    effect=pd.DataFrame(rows);effect.to_csv(p/'CALIBRATION_EFFECT_CLASSIFICATIONS.csv',index=False)
    movement=[]
    for key,g in move.groupby(KEYS,dropna=False):
        by={r.movement:r for _,r in g.iterrows()};a,b=by['direct_geometry'],by['net_refit']
        lo=a.consistent_input_pair_lower_m-b.consistent_input_pair_upper_m
        hi=a.consistent_input_pair_upper_m-b.consistent_input_pair_lower_m
        row={k:a[k] for k in a.index if k not in ['movement','primary_movement_m','consistent_input_pair_lower_m','consistent_input_pair_upper_m','unconstrained_pool_pair_upper_m','same_input_pair_count','interpretation']}
        row.update({'primary_direct_minus_net_m':a.primary_movement_m-b.primary_movement_m,'found_pool_lower_m':lo,'found_pool_upper_m':hi,'envelope_sign':bounds_sign(lo,hi),'interpretation':'Difference of movement quantiles; both movements allow their own baseline pool. Shared-baseline/global input constraints can make conservative extrema unattainable; unresolved is not demonstrated branch sensitivity.'})
        movement.append(row)
    pd.DataFrame(movement).to_csv(p/'MOVEMENT_REDUCTION_ENVELOPES.csv',index=False)
    summary={'status':'COMPLETE','pool_scope':'enhanced targeted overlay' if args.enhanced else 'primary recovered pools','effect_classification_by_band':{str(b):dict(Counter(g.effect_classification)) for b,g in effect.groupby('band_db2')},'files':{name:sha(p/name) for name in ['CALIBRATION_EFFECT_CLASSIFICATIONS.csv','MOVEMENT_REDUCTION_ENVELOPES.csv']}}
    writej(p/'CONSEQUENCE_CLASSIFICATION_SUMMARY.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':run()
