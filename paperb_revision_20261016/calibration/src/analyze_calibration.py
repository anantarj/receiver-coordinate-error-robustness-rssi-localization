#!/usr/bin/env python3
"""Reporting only: calibration quality, secondary localization and pool envelopes."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from calibration_quality import ROOT, BASE, sha, load, save_npz, write_json, write_csv

BANDS=[.01,.001,.0001]
POLICIES=['frozen','refit','selected']

def cls(x):return 'improved' if x < -1e-10 else ('degraded' if x>1e-10 else 'numerically_unchanged')

def original_reports():
    r=ROOT/'results';g=pd.read_csv(r/'ORIGINAL_GROUP_RESIDUALS.csv')
    out=[]
    for (block,assessment,role),s in g[(g.D_m>0)&(g.role!='all')].groupby(['block_id','assessment','role']):
        p=s.pivot(index=['field_index','D_m','draw'],columns='policy',values='macro_receiver_mae_db').reset_index()
        p['benefit_db']=p.frozen-p.refit
        for D,z in p.groupby('D_m'):
            out.append(dict(block_id=block,assessment=assessment,role=role,D_m=D,fields=len(z),improved=int((z.benefit_db>1e-10).sum()),
                            degraded=int((z.benefit_db< -1e-10).sum()),unchanged=int((abs(z.benefit_db)<=1e-10).sum()),
                            median_benefit_db=float(z.benefit_db.median()),min_benefit_db=float(z.benefit_db.min()),max_benefit_db=float(z.benefit_db.max())))
    write_csv(r/'ORIGINAL_RESIDUAL_EFFECTS.csv',out)
    selected=[];v=pd.read_csv(r/'LAMBDA_SELECTION_GRID.csv');q=pd.read_csv(r/'EXTENSION_QUERY_GROUP_RESIDUALS.csv')
    for p in sorted((ROOT/'inputs/blocks').glob('*.npz')):
        b=load(p);fold=p.stem.split('_')[1]
        for fi in range(len(b['field_D_m'])):
            z=v[(v.fold==fold)&(v.field_index==fi)];lam=float(b['field_selected_lambda'][fi]);d={}
            for pol,ll in [('frozen',0.),('refit',1.),('selected',lam)]:
                d[f'validation_{pol}_target_macro_mae_db']=float(z[z.lambda_value==ll].macro_target_mae_db.iloc[0])
                qq=q[(q.block_id==p.stem)&(q.field_index==fi)&(q.policy==pol)&(q.role=='targeted')]
                d[f'query_{pol}_target_macro_mae_db']=None if fi==0 else float(qq.macro_receiver_mae_db.iloc[0])
            selected.append(dict(block_id=p.stem,fold=fold,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),selected_lambda=lam,**d))
    write_csv(r/'CALIBRATION_POLICY_SELECTION.csv',selected)
    write_json(ROOT/'receipts/CALIBRATION_REPORT_RECEIPT.json',dict(status='CALIBRATION_REPORTS_COMPLETE',original_effect_rows=len(out),policy_selection_rows=len(selected),
               files={p.name:sha(p) for p in [r/'ORIGINAL_RESIDUAL_EFFECTS.csv',r/'CALIBRATION_POLICY_SELECTION.csv']}))
    print(json.dumps({'original_effect_rows':len(out),'policy_selection_rows':len(selected)}))

def query_reports():
    receipt=ROOT/'receipts/EXTENSION_QUERY_RUN_RECEIPT.json';done=json.loads(receipt.read_text());assert done['status']=='COMPLETE'
    qlock=json.loads((ROOT/'protocol/EXTENSION_QUERY_LOCK.json').read_text());chunk=qlock['chunk_queries']
    arms=[];effects=[];joint=[];selection=pd.read_csv(ROOT/'results/CALIBRATION_POLICY_SELECTION.csv');candidate_summary=[]
    for p in sorted((ROOT/'inputs/blocks').glob('*.npz')):
        b=load(p);outpath=ROOT/'results/extension_query_arrays'/p.name;assert sha(outpath)==done['output_arrays'][p.name];a=load(outpath)
        F,P,Q=a['nlls_objective_db2'].shape;assert P==3;fold=p.stem.split('_')[1]
        lower=np.full((F,P,Q,3),np.nan);upper=lower.copy();movelo=lower.copy();movehi=lower.copy();diameter=lower.copy()
        for start in range(0,Q,chunk):
            stop=min(start+chunk,Q);name=f'{p.stem}__{start:05d}_{stop:05d}.npz'
            z=load(ROOT/'results/extension_candidate_shards'/name);state=load(ROOT/'results/extension_query_shards'/name)
            for qi,q in enumerate(range(start,stop)):
                baseline=int(state['nlls_input_index'][0,0,qi])
                for fi in range(F):
                    for pi in range(P):
                        uid=int(state['nlls_input_index'][fi,pi,qi]);assert state['nlls_input_sha256'][fi,pi,qi]==z['input_sha256'][uid]
                        for bi,band in enumerate(BANDS):
                            keep=z['candidate_in_band'][uid,bi];xy=z['candidate_position_m'][uid,keep]
                            if len(xy):
                                e=np.linalg.norm(xy-b['query_xy_m'][q],axis=1);lower[fi,pi,q,bi]=e.min();upper[fi,pi,q,bi]=e.max()
                                diameter[fi,pi,q,bi]=z['candidate_band_diameter_m'][uid,bi]
                                if z['input_sha256'][uid]==z['input_sha256'][baseline]:movelo[fi,pi,q,bi]=0.;movehi[fi,pi,q,bi]=0.
                                else:
                                    base=z['candidate_position_m'][baseline,z['candidate_in_band'][baseline,bi]]
                                    d=np.linalg.norm(xy[:,None]-base[None,:],axis=-1);movelo[fi,pi,q,bi]=d.min();movehi[fi,pi,q,bi]=d.max()
        assert np.isfinite(lower).all() and np.isfinite(upper).all(),'Unavailable state requires explicit revised reporting, not deletion.'
        save_npz(ROOT/'results/extension_candidate_envelopes'/p.name,source_rows=b['source_rows'],bands_db2=np.array(BANDS),
                 lower_error_m=lower,upper_error_m=upper,lower_movement_m=movelo,upper_movement_m=movehi,diameter_m=diameter)
        errors={method:np.linalg.norm(a[f'{method}_position_m']-b['query_xy_m'][None,None,:,:],axis=-1) for method in ['wcl','nlls']}
        movements={method:np.linalg.norm(a[f'{method}_position_m']-a[f'{method}_position_m'][0,0][None,None,:,:],axis=-1) for method in errors}
        for fi in range(F):
            target=b['field_target_mask'][fi][np.maximum(b['selected_ids']-1,0)]&b['selected_mask'];affected=target.any(axis=1)
            masks={'full':np.ones(Q,bool),'affected':affected}
            for cohort,mask in masks.items():
                if not mask.any():continue
                for method,e in errors.items():
                    for pi,pol in enumerate(POLICIES):
                        row=dict(block_id=p.stem,fold=fold,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),cohort=cohort,n=int(mask.sum()),estimator=method,policy=pol,
                                 selected_lambda=float(b['field_selected_lambda'][fi]),p50_m=float(np.quantile(e[fi,pi,mask],.5)),p95_m=float(np.quantile(e[fi,pi,mask],.95)),mean_m=float(np.mean(e[fi,pi,mask])),
                                 movement_p50_m=float(np.median(movements[method][fi,pi,mask])),movement_p95_m=float(np.quantile(movements[method][fi,pi,mask],.95)))
                        if method=='nlls':row.update(competitive_above1m=int((diameter[fi,pi,mask,0]>1).sum()),competitive_above1km=int((diameter[fi,pi,mask,0]>1000).sum()),max_competitive_diameter_m=float(diameter[fi,pi,mask,0].max()))
                        arms.append(row)
                    if not fi:continue
                    for metric,t in [('p50',.5),('p95',.95)]:
                        for left,right in [(0,1),(0,2),(1,2)]:
                            delta=float(np.quantile(e[fi,left,mask],t)-np.quantile(e[fi,right,mask],t))
                            for bi,band in enumerate(BANDS if method=='nlls' else [None]):
                                lo=delta if method=='wcl' else float(np.quantile(lower[fi,left,mask,bi],t)-np.quantile(upper[fi,right,mask,bi],t))
                                hi=delta if method=='wcl' else float(np.quantile(upper[fi,left,mask,bi],t)-np.quantile(lower[fi,right,mask,bi],t))
                                if method=='nlls' and np.array_equal(a['nlls_input_sha256'][fi,left,mask],a['nlls_input_sha256'][fi,right,mask]):
                                    # A consistent numerical-input selection rule cannot
                                    # choose different branches for identical policy inputs.
                                    lo=hi=0.;assert abs(delta)<=1e-10
                                status='positive_invariant' if lo>1e-6 else ('negative_invariant' if hi< -1e-6 else ('numerical_tie' if max(abs(lo),abs(hi))<=1e-6 else 'unresolved_by_envelope'))
                                effects.append(dict(block_id=p.stem,fold=fold,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),cohort=cohort,n=int(mask.sum()),estimator=method,metric=metric,
                                                    comparison=f'{POLICIES[left]}_minus_{POLICIES[right]}',candidate_band_db2=band,selected_output_benefit_m=delta,lower_benefit_m=lo,upper_benefit_m=hi,envelope_status=status))
            if fi:
                ss=selection[(selection.block_id==p.stem)&(selection.field_index==fi)].iloc[0]
                for method,e in errors.items():
                    for pi,pol in [(1,'refit'),(2,'selected')]:
                        rssdelta=ss[f'query_{pol}_target_macro_mae_db']-ss.query_frozen_target_macro_mae_db
                        valdelta=ss[f'validation_{pol}_target_macro_mae_db']-ss.validation_frozen_target_macro_mae_db
                        joint.append(dict(block_id=p.stem,fold=fold,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),estimator=method,policy=pol,
                                          selected_lambda=ss.selected_lambda,query_macro_rss_mae_change_db=float(rssdelta),query_rss_class=cls(rssdelta),validation_macro_rss_mae_change_db=float(valdelta),
                                          p50_benefit_m=float(np.median(e[fi,0])-np.median(e[fi,pi])),p95_benefit_m=float(np.quantile(e[fi,0],.95)-np.quantile(e[fi,pi],.95)),
                                          own_baseline_movement_p50_m=float(np.median(movements[method][fi,pi])),
                                          nlls_ambiguous_above1m=None if method=='wcl' else int((diameter[fi,pi,:,0]>1).sum())))
        for bi,band in enumerate(BANDS):candidate_summary.append(dict(block_id=p.stem,band_db2=band,stored_states=F*P*Q,above1m=int((diameter[:,:,:,bi]>1).sum()),above1km=int((diameter[:,:,:,bi]>1000).sum()),max_diameter_m=float(diameter[:,:,:,bi].max())))
    for name,data in [('EXTENSION_POSITION_ARMS',arms),('EXTENSION_POSITION_EFFECTS',effects),('CALIBRATION_LOCALIZATION_LINK',joint),('EXTENSION_CANDIDATE_SUMMARY',candidate_summary)]:write_csv(ROOT/'results'/(name+'.csv'),data)
    paths=[ROOT/'results'/(name+'.csv') for name in ['EXTENSION_POSITION_ARMS','EXTENSION_POSITION_EFFECTS','CALIBRATION_LOCALIZATION_LINK','EXTENSION_CANDIDATE_SUMMARY']]
    write_json(ROOT/'receipts/EXTENSION_ANALYSIS_RECEIPT.json',dict(status='COMPLETE',arm_rows=len(arms),effect_rows=len(effects),link_rows=len(joint),
               files={p.name:sha(p) for p in paths},producer_sha256=sha(__file__),query_run_receipt_sha256=sha(receipt),
               interpretation='Primary unchanged finite solver on newly fit-only inputs. Candidate envelopes concern found pools only; independent per-query extremes can be conservative. Exact repeated numerical input movement is fixed to zero.'))
    print(json.dumps({'arm_rows':len(arms),'effect_rows':len(effects),'link_rows':len(joint)}),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['calibration','queries']);args=ap.parse_args()
    original_reports() if args.stage=='calibration' else query_reports()
