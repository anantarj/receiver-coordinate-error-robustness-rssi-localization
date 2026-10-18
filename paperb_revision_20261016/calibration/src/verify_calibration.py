#!/usr/bin/env python3
"""Reconstruct residual identities and split/fit/selection from saved inputs.

This verification uses an explicitly expanded observation-minus-prediction
formula rather than importing the producing residual/fitting functions.
"""
import hashlib, json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent.parent/'paperb_execution_20261015'
def load(p):
    with np.load(p,allow_pickle=False) as z:return dict(z)
checks=[];maximum=0.
for p in sorted((ROOT/'inputs/blocks').glob('*.npz')):
    b=load(p);fold=p.stem.split('_')[1];old=load(BASE/f'inputs/blocks/study2_{fold}_all.npz');v=load(ROOT/'inputs'/f'{p.stem}_validation.npz')
    for key in ['source_rows','query_xy_m','selected_ids','selected_mask','query_rssi_dbm','roster_mask','reference_anchors_m','field_anchors_m','field_D_m','field_draw','field_target_mask']:
        assert np.array_equal(b[key],old[key],equal_nan=True),(p,key)
    fitcells=set(map(tuple,np.floor(b['cal_xy_m_flat']/250).astype(int)))
    valcells=set(map(tuple,np.floor(v['reference_xy_m']/250).astype(int)))
    assert not fitcells&valcells
    for j,g in enumerate(b['cal_receiver_ids']):
        s=slice(b['cal_offsets'][j],b['cal_offsets'][j+1]);assert s.stop-s.start>=10
        for f,a in enumerate(b['field_anchors_m']):
            value=np.median(b['cal_rssi_flat'][s]+47*np.log10(np.sqrt(((b['cal_xy_m_flat'][s]-a[g-1])**2).sum(axis=1))+1))
            difference=abs(value-b['field_refit_intercepts_dbm'][f,g-1]);maximum=max(maximum,difference);assert difference<1e-12
        assert b['reference_intercepts_dbm'][g-1]==b['field_refit_intercepts_dbm'][0,g-1]
    for f,a in enumerate(b['field_anchors_m']):
        losses=[]
        for lam in [0,.25,.5,.75,1]:
            aa=b['reference_intercepts_dbm']+lam*(b['field_refit_intercepts_dbm'][f]-b['reference_intercepts_dbm']);loss=[]
            for g in [14,69]:
                mask=v['receiver_ids']==g;dist=np.sqrt(((v['reference_xy_m'][mask]-a[g-1])**2).sum(axis=1))
                residual=v['observed_rssi_dbm'][mask]-(aa[g-1]-47*np.log10(dist+1));loss.append(np.mean(np.abs(residual)))
            losses.append(np.mean(loss))
        chosen=[0,.25,.5,.75,1][np.flatnonzero(np.array(losses)<=min(losses)+1e-10)[0]]
        assert chosen==b['field_selected_lambda'][f]
    checks.append(dict(block=p.stem,unchanged_cohort_roster=True,disjoint_spatial_cells=True,fit_counts_supported=True,intercepts_reconstructed=True,lambda_reconstructed=True))
for p in sorted((ROOT/'results/original_residual_arrays').glob('*.npz')):
    name=p.stem.rsplit('__',1)[0];b=load(BASE/'inputs/blocks'/f'{name}.npz');z=load(p);j=z['receiver_ids']-1
    for f,a in enumerate(b['field_anchors_m']):
        distance=np.sqrt(((z['reference_xy_m']-a[j])**2).sum(axis=1))
        for pi,intercept in enumerate([b['reference_intercepts_dbm'],b['field_refit_intercepts_dbm'][f]]):
            manual=z['observed_rssi_dbm']-(intercept[j]-47*np.log10(distance+1))
            delta=np.max(np.abs(manual-z['residual_db'][f,pi]));maximum=max(maximum,float(delta));assert delta<1e-10
    checks.append(dict(array=p.name,all_residuals_reconstructed=True))
receipt=dict(status='PASS',check_records=len(checks),maximum_numeric_difference_db=maximum,details=checks,
             producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             note='Different expression ordering; no fitting or localization outputs changed.')
(ROOT/'receipts/INDEPENDENT_CALIBRATION_CHECK.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='details'}))
