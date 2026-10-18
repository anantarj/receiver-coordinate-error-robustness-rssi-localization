#!/usr/bin/env python3
"""Bind completed input preparation and analysis rules before primary outcomes."""
from pathlib import Path
import datetime,hashlib,json
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def js(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def audit_key(row):return hashlib.sha256(f'paperb_numerical_audit_v1:{int(row)}'.encode()).hexdigest()

def main():
    destination=ROOT/'protocol/EXECUTION_LOCK.json'
    assert not destination.exists(),'Do not silently replace an existing execution lock'
    assert not list((ROOT/'results').rglob('*.npz')),'Scientific outcome arrays exist before lock'
    registry=json.loads((ROOT/'inputs/INPUT_REGISTRY.json').read_text())
    assert len(registry['blocks'])==18
    review=json.loads((ROOT/'receipts/INPUT_REVIEW.json').read_text())
    assert review.get('status')=='PASS','Independent input review must pass'
    selections=[];counts={};cells=0
    for block in registry['blocks']:
        with np.load(ROOT/block['path'],allow_pickle=False) as b:
            rows=b['source_rows'];ids=b['selected_ids'];F=len(b['field_D_m']);Q=len(rows)
            expectedF=25 if block['study']=='study1' else 9
            expectedQ=512 if block['study']=='study1' else 500
            assert F==expectedF and Q==expectedQ
            both=np.any(ids==14,axis=1)&np.any(ids==69,axis=1)
            fallback=np.any(ids==14,axis=1) if block['study']=='study1' else np.any(np.isin(ids,[14,69]),axis=1)
            candidates=np.flatnonzero(both if both.any() else fallback)
            assert len(candidates)>0
            qi=min(candidates,key=lambda i:(audit_key(rows[i]),int(rows[i])))
            selections.append({'block':block['block_id'],'query_index':int(qi),'source_row':int(rows[qi]),'kind':'exposed',
                               'exposure_rule':'both14and69' if both.any() else 'declared_fallback',
                               'selected_receiver_ids':ids[qi][ids[qi]>0].tolist()})
            cells+=2*F-1
            if block['study']=='study1' or block['budget']=='all':
                candidates=np.flatnonzero(~np.any(np.isin(ids,[14,69]),axis=1));assert len(candidates)>0
                qi=min(candidates,key=lambda i:(audit_key(rows[i]),int(rows[i])))
                selections.append({'block':block['block_id'],'query_index':int(qi),'source_row':int(rows[qi]),'kind':'unexposed_control',
                                   'exposure_rule':'neither14nor69','selected_receiver_ids':ids[qi][ids[qi]>0].tolist()});cells+=1
            counts[block['block_id']]={'query_count':Q,'unique_field_policy_states':2*F-1,
                                      'scheduled_estimates_per_estimator':Q*(2*F-1)}
    assert cells==376
    js(ROOT/'protocol/AUDIT_SELECTION.json',{'status':'FIXED_BEFORE_PRIMARY_OUTCOMES','expected_cells':cells,
       'query_hash':'SHA256 UTF8(paperb_numerical_audit_v1:<zero-based-source-row>)',
       'exposed_rule':'Prefer first hash-ordered sampled row selecting both14and69; if absent, study1requires14,study2anytarget.',
       'zero_policy':'One zero state only; no artificial frozen/refit replication.',
       'initial_splits':30000,'escalated_splits':100000,'objective_gap_tolerance_db2':.01,
       'escalation_rule':'Any primary local start unconverged OR objective improvement>max(1e-4,1e-6*(1+J_primary)) dB^2 OR position shift>1m.',
       'retention':'Both audit stages retained; never replace primary outputs. Unresolved numerical gap remains unresolved.',
       'selections':selections})
    js(ROOT/'protocol/ANALYSIS_SPECIFICATION.json',{
       'primary_map':'official32_minus71','R29_scope':'Historical sensitivity only; not independent map validation.',
       'estimators':['WCL_kappa4.7','fixed_multistart_RSS_NLLS'],
       'comparison':['within-row frozen/refit on identical field','each state vs own budget-specific unperturbed baseline',
                     'WCL vs NLLS ordering on all-four-state common finite rows','10vsall on samefold/query/geometry'],
       'reporting_populations':['full fixed query sample including unexposed','field-specific selected-target subset'],
       'quantiles':{'probabilities':[.5,.9,.95],'method':'linear','quantile_difference':'within field before descriptive direction aggregation'},
       'metrics':['absolute P50/P90/P95,mean,max','difference of error quantiles','median and mean paired message difference',
                  'help/harm/tie with counts and denominators','direct frozen prediction displacement from own zero baseline',
                  'additional refit displacement from frozen','net refitted displacement from own zero baseline',
                  'fraction with refitted displacement smaller than frozen displacement','input and finite-output availability',
                  'local convergence/exhaustion/failure and competitive endpoint diagnostics'],
       'numeric_tie':'1e-6m +1e-12*max(abs(left),abs(right))',
       'finite_policy':'Arm metrics explicit finite denominator; paired metrics on common finite rows with missing counts. No failed row silent omission.',
       'population_coverage':'Full heldout-region eligible counts separately from sampled-query performance; no imputation to unsampled messages.',
       'aggregation':'Descriptive medians/min/max over four coupled directions. Calibration repetitions reported separately; all-budget calculated once.',
       'inference':'No pooled independent-message p-values or confidence claims. Repeated message-condition entries are not sample size.',
       'thresholds':'Complete empirical curves reconstructable from retained error arrays; no outcome-selected application threshold.',
       'completion':'All planned conditions accounted for with negative/null/failed outcomes; no required favorable sign or reversal.',
       'block_counts':counts,'total_estimates_per_estimator':sum(v['scheduled_estimates_per_estimator'] for v in counts.values())})
    paths=[]
    paths.extend(p for p in (ROOT/'inputs').rglob('*') if p.is_file())
    paths.extend(ROOT/'src'/name for name in ['prepare_studies.py','rss_nlls_production.py','run_studies.py','run_numerical_audits.py','analyze_studies.py','lock_execution.py'])
    paths.extend(ROOT/'protocol'/name for name in ['AUDIT_SELECTION.json','ANALYSIS_SPECIFICATION.json'])
    paths.extend(ROOT/'receipts'/name for name in ['INPUT_REVIEW.json','MAP_RECOVERY.json'])
    bound={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}
    js(destination,{'status':'LOCKED_BEFORE_NEW_CALIBRATION_EFFECT_COMPUTATIONS','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'knowledge_state':'Historical WCL results and reference-only computation pilot known. New NLLS calibration contrasts and spatial-budget outcomes not evaluated.',
       'registration_scope':'Local execution specification, not external preregistration or an unseen independent campaign.',
       'raw_csv_sha256':registry['raw_csv_sha256'],'bound_files':bound,
       'hardware_policy':'All fixed local starts run; six worker processes affect scheduling only; no wall-clock inclusion or stopping.',
       'computed_count_note':'Duplicate zero arms and exact-identical solver inputs can be reused; all scheduled states remain recorded.'})
    print(json.dumps({'lock_sha256':sha(destination),'bound_files':len(bound),'audit_cells':cells,'total_estimates_per_estimator':sum(v['scheduled_estimates_per_estimator'] for v in counts.values())}))

if __name__=='__main__':main()
