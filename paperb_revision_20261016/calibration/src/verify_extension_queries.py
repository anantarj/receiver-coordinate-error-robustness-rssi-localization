#!/usr/bin/env python3
"""Verify all selected outputs and retained candidate objectives without solving."""
import hashlib, json, struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def load(p):
    with np.load(p,allow_pickle=False) as z:return dict(z)
rec=json.loads((ROOT/'receipts/EXTENSION_QUERY_RUN_RECEIPT.json').read_text());assert rec['exceptions']==0
blocks={};candidate_inputs=0;state_count=0;maxobj=0.;maxpos=0.;maxwcl=0.
for p in sorted((ROOT/'results/extension_query_shards').glob('*.npz')):
    name,bounds=p.stem.split('__');start,stop=map(int,bounds.split('_'))
    if name not in blocks:blocks[name]=load(ROOT/'inputs/blocks'/f'{name}.npz')
    b=blocks[name];a=load(p);c=load(ROOT/'results/extension_candidate_shards'/p.name)
    assert a['nlls_finite'].all();state_count+=a['nlls_finite'].size
    seen=set()
    for fi in range(len(b['field_D_m'])):
        for pi,fit in enumerate([b['reference_intercepts_dbm'],b['field_refit_intercepts_dbm'][fi],b['field_selected_intercepts_dbm'][fi]]):
            for qi,q in enumerate(range(start,stop)):
                keep=b['selected_mask'][q];idx=b['selected_ids'][q,keep]-1
                aa=b['field_anchors_m'][fi,idx];rss=b['query_rssi_dbm'][q,keep];A=fit[idx];u=int(a['nlls_input_index'][fi,pi,qi])
                payload=b'PAPERB_CANDIDATE_INPUT_V1\0'+struct.pack('<Idd',len(rss),4.7,1.)+aa.astype('<f8').tobytes()+rss.astype('<f8').tobytes()+A.astype('<f8').tobytes()
                digest=hashlib.sha256(payload).hexdigest();assert digest==a['nlls_input_sha256'][fi,pi,qi]==c['input_sha256'][u]
                slot=c['selected_candidate_slot'][u];assert c['candidate_kind'][u,slot]==2
                d=np.linalg.norm(a['nlls_position_m'][fi,pi,qi]-c['candidate_position_m'][u,slot]);maxpos=max(maxpos,float(d));assert d==0.
                assert a['nlls_objective_db2'][fi,pi,qi]==c['candidate_objective_db2'][u,slot]
                weights=np.power(10.,(rss-A-np.max(rss-A))/10.);weights/=weights.sum()
                wcl=np.sum(weights[:,None]*aa,axis=0);d=np.linalg.norm(wcl-a['wcl_position_m'][fi,pi,qi]);maxwcl=max(maxwcl,float(d));assert d<1e-7
                if u in seen:continue
                seen.add(u);candidate_inputs+=1
                good=c['candidate_valid'][u];assert good.sum()==2*(9+len(rss))+1
                local=c['candidate_local_position_m'][u,good];origin=c['search_origin_m'][u]
                assert np.array_equal(local+origin,c['candidate_position_m'][u,good])
                dist=np.sqrt(((local[:,None,:]-(aa-origin)[None,:,:])**2).sum(axis=2))
                residual=rss[None,:]-A[None,:]+47*np.log10(dist+1.)
                objective=np.sum(residual*residual,axis=1);d=np.max(abs(objective-c['candidate_objective_db2'][u,good]));maxobj=max(maxobj,float(d));assert d<1e-8
                assert c['candidate_objective_db2'][u,slot]==np.min(c['candidate_objective_db2'][u,good])
                for bi,band in enumerate(c['candidate_bands_db2']):
                    mask=good&(c['candidate_objective_db2'][u]<=np.min(c['candidate_objective_db2'][u,good])+band)
                    assert np.array_equal(mask,c['candidate_in_band'][u,bi])
    assert len(seen)==len(c['input_index'])
report=dict(status='PASS',stored_states=state_count,checkpoint_unique_inputs=candidate_inputs,
            all_prescribed_initials_endpoints_incumbents_retained=True,exceptions=0,
            maximum_candidate_objective_difference_db2=maxobj,maximum_selected_position_difference_m=maxpos,
            maximum_wcl_direct_reconstruction_difference_m=maxwcl,
            producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            interpretation='Saved-output and candidate reconstruction, not independent numerical optimization or physical validation.')
(ROOT/'receipts/INDEPENDENT_EXTENSION_QUERY_CHECK.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
