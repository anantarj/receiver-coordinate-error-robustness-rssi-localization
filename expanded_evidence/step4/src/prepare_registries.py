#!/usr/bin/env python3
"""Freeze Step-4 designs before outcome execution. User authorized continuation
while three full-text comparisons remain unresolved; no novelty inference follows.
"""
from pathlib import Path
import argparse, datetime, json, platform, time, sys
import numpy as np
from model import js,sha,npz,fit,weights,centroid,need
from step2_raw_helpers import Archive,load_raw,fit_all,raw_selection,MAPS,CSV_SHA,ARCHIVE_SHA
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--csv',type=Path,required=True);a=ap.parse_args()
    pd=ROOT/'protocol';need(not (pd/'C2_LOCK.json').exists(),'Already locked')
    parent=ROOT/'parents/PAPERB_STEP3_MECHANISM_AND_BOUNDARIES_20261007.zip'
    js(ROOT/'provenance/PARENTS_BEFORE.json',[{'path':str(p),'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in [a.csv,a.archive,parent,ROOT/'planning/PAPERB_RESEARCH_AND_REVISION_PLAN_V4_20261007.md',ROOT/'planning/WRITING_AND_CLAIM_BLUEPRINT.md']])
    # Pilot uses only historical reference geometry/observations and canonical weight power.
    start=time.perf_counter();ar=Archive(a.archive);raw=load_raw(a.csv);cal=np.array(ar.js('reproduction_inputs/results/rc5/populations/calibration_ordered_source_rows.json'),dtype=int)
    budgetcheck=[]
    for name in MAPS:
        coords=ar.js('reproduction_inputs/maps/'+name+'.json');base=ar.js('extension/'+name+'_reference.json');ref=ar.npz('extension/'+name+'_reference.npz')
        aa,counts=fit_all(raw,cal,coords);ids,rx=raw_selection(raw,ref['source_rows'],aa,coords)
        slotxy=np.zeros((*ids.shape,2));av=np.zeros(ids.shape)
        for g,v in coords.items():slotxy[ids==int(g)]=v;av[ids==int(g)]=aa[g]
        st=time.perf_counter()
        for _ in range(30):
            p=weights(rx,av,4.7,valid=ids>=0);pred=centroid(p,slotxy);err=np.linalg.norm(pred-raw['xy'][ref['source_rows']],axis=1);np.quantile(err,[.5,.9,.95])
        budgetcheck.append({'map':name,'30_known_reference_seconds':time.perf_counter()-st,'max_prediction_difference_m':float(np.max(np.abs(pred-ref['predictions']))),'reference_median_m':float(np.median(err))})
        need(np.max(np.abs(pred-ref['predictions']))<1e-6,'Reference bridge')
    common={'n_fit':4.7,'kappa':[.5,1.,2.,4.7],'policies':['frozen','unrestricted','shared_update','bounded10','bounded30'],'shared_update':'median of all fitted-minus-reference receiver updates, added to every original intercept','bounds_db':[10,30],'bounds_scope':'diagnostic fixed caps, not validated physical constraints','quantile_method':'linear','quantiles':[.5,.9,.95],'tolerance':{'absolute_m':1e-6,'relative':1e-12,'weight':1e-12},'inference':'descriptive conditional experiments; no pooled independence, outcome-selected thresholds or p-value screening','knowledge_state':'Historical arrays and Step1-3 findings known; these random realizations are newly generated after this lock; local specification, not external preregistration','full_text_dependency':'prior-art comparison open; computational study authorized to continue without declaring novelty'}
    layouts={
      'spread':{'receivers_m':[[-800,-600],[900,-400],[750,850],[-650,900],[150,-950],[100,600]],'cal_bounds_m':[[-500,500],[-500,500]],'eval_bounds_m':[[-500,500],[-500,500]],'spatial_regime':'same-area independently generated positions'},
      'corridor':{'receivers_m':[[-1000,-80],[-550,120],[-100,-100],[250,80],[600,-120],[1100,100]],'cal_bounds_m':[[-900,900],[-100,100]],'eval_bounds_m':[[-900,900],[-100,100]],'spatial_regime':'same-area corridor positions'},
      'clustered_holdout':{'receivers_m':[[-800,-250],[-680,-180],[-620,-320],[600,450],[880,650],[400,-650]],'cal_bounds_m':[[-700,-100],[-400,400]],'eval_bounds_m':[[100,700],[-400,400]],'spatial_regime':'fixed 200-m easting gap between calibration and evaluation rectangles'}
    }
    synthetic={**common,'registry_id':'PAPERB-C2-20261007-v1','L_m':1000.,'d0_m':1.,'layouts':layouts,'cal_n':400,'eval_n':400,'seeds':list(range(16)),'A_true_dbm':[-30,-32,-29,-31,-33,-28], 'propagation_conditions':[{'name':'matched_noiseless','n_true':4.7,'sigma_db':0.},{'name':'matched_gaussian6','n_true':4.7,'sigma_db':6.},{'name':'mismatched_gaussian6','n_true':3.5,'sigma_db':6.}], 'noise_process':'independent zero-mean Gaussian link noise for each calibration/query record; same standardized draws reused across matched/mismatched noisy conditions','seed_key':'SeedSequence([20261007,4,layout_index,seed,stream]); streams 10 calibration positions,20 evaluation positions,30 calibration normal noise,40 evaluation normal noise,50 receiver-wise angles,60 shared coherent angle', 'selection':'all six always selected; no reception censoring or RSSI clipping; this is a controlled signal model, not a radio-network simulator', 'target_sets':[[0],[0,1,2,3,4],[0,1,2,3,4,5]],'direction_patterns':['coherent','receiverwise'],'D_over_L':[0,.1,.5,1,5,20],'query_support_challenge':{'layout':'spread','targets':[0],'pattern':'receiverwise','untargeted_query_shift_db':-40.,'all_three_propagation_conditions':True,'purpose':'fixed diagnostic signal mismatch relative to calibration; not claimed measured fading distribution'},'symmetry_cancellation':'Retained explicitly in completed C1; random C2 fields need not satisfy symmetry. No outcome-selected cancellation filter.', 'retention':'save every arm error vector; reference weights, removal predictions and generated synthetic observations; compact per-field summaries and checks. Shared-arm errors may be stored explicitly. Per-arm centroids regenerate from saved inputs, fits and registry; not all intermediates retained.','resource_ceiling':{'seconds_per_run':420,'max_output_bytes':1200000000}}
    js(pd/'C2_REGISTRY.json',synthetic)
    directions={str(r):{} for r in range(32)}
    for r in range(32):
      for g in range(1,73):
        theta=float(np.random.default_rng(np.random.SeedSequence([20261007,2,r,g])).uniform(0,2*np.pi))
        directions[str(r)][str(g)]=[float(np.cos(theta)),float(np.sin(theta))]
    real={**common,'registry_id':'PAPERB-REAL-CORE-20261007-v1','maps':list(MAPS),'target_sets':[[14],[14,69]],'D_m':[0,100,500,1000,5000],'draws':list(range(32)),'directions_by_draw_receiver':directions,'direction_key':'SeedSequence([20261007,2,replicate,numeric_receiver_id]); excludes map,kappa,D,policy and target set','selection':'original fixed raw-RSSI ranked 10 slots, minimum3 before any coordinate perturbation; no reselection/refill', 'raw_csv_sha256':CSV_SHA,'upstream_sha256':ARCHIVE_SHA,'D_zero':'only once per map/target, not32 artificial replicates; each kappa has own baseline','target_validation':'not part of this core; six-receiver training-stratum extension remains separately scheduled','resource_ceiling':{'seconds_per_run':300,'max_output_bytes':1500000000},'retention':'all arm error and normalized target-mass vectors, field maps, refitted intercepts and indices; source-row IDs and selected slots. Raw RSSI and transmitter coordinates obtained from fingerprinted CSV; not redistributed.'}
    js(pd/'REAL_CORE_REGISTRY.json',real)
    receipt={'historical_reference_pilot':budgetcheck,'load_and_pilot_seconds':time.perf_counter()-start,'new_outcomes_used_for_budget':False,'numpy':np.__version__,'python':sys.version,'platform':platform.platform()}
    js(ROOT/'reports/KNOWN_CASE_RESOURCE_PILOT.json',receipt)
    for stem in ['C2','REAL_CORE']:
        js(pd/(stem+'_LOCK.json'),{'status':'LOCKED_BEFORE_NEW_OUTCOMES','registry_sha256':sha(pd/(stem+'_REGISTRY.json')),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reference_pilot_sha256':sha(ROOT/'reports/KNOWN_CASE_RESOURCE_PILOT.json'),'definition':'Local prospective lock after historical results; not independent preregistration or novelty clearance'})
    js(pd/'STAGE_SCOPE_AMENDMENT.json',{'user_instruction':'Proceed with planned work not dependent on three unavailable PDF methods','change':'C2 and real core may run with prior-art gate partial; claims of novelty and final manuscript positioning remain blocked. No assumption that unread papers omit findings.','before_new_outcomes':True,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    print(json.dumps(receipt,indent=2));print('Both new-case registries locked; no new-case predictions run.')
if __name__=='__main__':main()
