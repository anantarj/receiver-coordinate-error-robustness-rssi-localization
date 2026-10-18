"""Independent input/candidate/comparison read-back; does not rerun optimization."""
from pathlib import Path
import csv,hashlib,json
import numpy as np
import pandas as pd

P=Path(__file__).resolve().parent; R=P.parent/'removal'
B=P.parents[1]/'paperb_execution_20261015'
inp=np.load(B/'inputs/blocks/study1_official32_minus71_all.npz')
out=np.load(B/'results/arrays/study1_official32_minus71_all.npz')
mapping=pd.read_csv(R/'REMOVAL_INPUT_MAPPING.csv',dtype={'target_set':str})
comparisons=pd.read_csv(R/'REMOVAL_COMPARISONS.csv',dtype={'target_set':str})
local=np.load(R/'CANDIDATE_LOCAL_COORDINATES.npz')
locals_by_hash={}
for ih,ix,x in zip(local['input_hash'],local['candidate_index'],local['local_position_m']):
    locals_by_hash.setdefault(str(ih),{})[int(ix)]=x
cells={};diameters={};max_obj_error=0.
for p in sorted((R/'candidates').glob('*.json')):
    c=json.loads(p.read_text());cells[p.stem]=c
    a=np.asarray(c['anchors_m']);o=np.mean(a,axis=0);aa=a-o
    s=np.asarray(c['rss_dbm']);A=np.asarray(c['intercepts_dbm'])
    positions=np.asarray([v['position_m'] for v in c['candidates']])
    z=np.asarray([locals_by_hash[p.stem][j] for j in range(len(positions))])
    res=s-A+47*np.log10(np.linalg.norm(z[:,None,:]-aa[None,:,:],axis=2)+1.)
    values=np.sum(res**2,axis=1);saved=np.asarray([v['objective_db2'] for v in c['candidates']])
    max_obj_error=max(max_obj_error,float(np.max(np.abs(values-saved))))
    assert np.allclose(values,saved,atol=1e-8,rtol=1e-12)
    competitive=positions[saved<=saved.min()+.01]
    diameters[p.stem]=float(np.max(np.linalg.norm(competitive[:,None,:]-competitive[None,:,:],axis=2)))
    c['_positions']=positions;c['_values']=saved;c['_a']=a;c['_o']=o;c['_s']=s;c['_A']=A
for m in mapping.itertuples(index=False):
    mask=inp['selected_mask'][m.query_index];ids=inp['selected_ids'][m.query_index,mask]
    targets=list(map(int,m.target_set.split(',')));keep=~np.isin(ids,targets);ix=ids[keep]-1
    c=cells[m.input_hash]
    assert np.array_equal(c['_a'],inp['reference_anchors_m'][ix])
    assert np.array_equal(c['_s'],inp['query_rssi_dbm'][m.query_index,mask][keep])
    assert np.array_equal(c['_A'],inp['reference_intercepts_dbm'][ix])
    assert int((~keep).sum())==m.target_exposure and int(keep.sum())==m.remaining_receiver_count
keymap={(r.target_set,r.query_index):r.input_hash for r in mapping.itertuples(index=False)}
max_distance_diff=0.;max_signed_diff=0.;max_movement_diff=0.
for row in comparisons.to_dict('records'):
    c=cells[keymap[(row['target_set'],row['query_index'])]]
    pi={'frozen':0,'refitted':1}[row['policy']]
    x=out['nlls_position_m'][row['field_index'],pi,row['query_index']]
    z=x-c['_o'];aa=c['_a']-c['_o']
    rr=c['_s']-c['_A']+47*np.log10(np.linalg.norm(z-aa,axis=1)+1.)
    signed=float(rr@rr-c['_values'].min())
    max_signed_diff=max(max_signed_diff,abs(signed-row['signed_JU_excess_vs_best_found_db2']))
    for band in (.01,.001,.0001):
        pc=c['_positions'][c['_values']<=c['_values'].min()+band]
        dist=float(np.min(np.linalg.norm(pc-x,axis=1)))
        max_distance_diff=max(max_distance_diff,abs(dist-row[f'distance_to_found_U_band_{band}_m']))
    move=float(np.linalg.norm(x-out['nlls_position_m'][0,0,row['query_index']]))
    max_movement_diff=max(max_movement_diff,abs(move-row['full_movement_from_zero_m']))
assert max_distance_diff<1e-8 and max_signed_diff<1e-7 and max_movement_diff<1e-8
positive=comparisons[comparisons.D_m>0]
counts={}
for t,g in mapping.groupby('target_set'):
    exposed=g[g.target_exposure>0]
    counts[t]={'exposed':len(exposed),'exposed_U_ge3':int((exposed.remaining_receiver_count>=3).sum()),
               'exposed_U_lt3':int((exposed.remaining_receiver_count<3).sum())}
by_n={}
for n in sorted({c['remaining_receivers'] for c in cells.values()}):
    ds=[diameters[h] for h,c in cells.items() if c['remaining_receivers']==n]
    by_n[str(n)]={'unique_inputs':len(ds),'max_found_diameter_m':max(ds),'above_1m':sum(x>1 for x in ds)}
result={'status':'passed','reviewer':'theory agent independent code and direct-formula review',
    'all_removal_candidate_cells':len(cells),'all_mapping_rows':len(mapping),'all_comparison_rows':len(comparisons),
    'max_candidate_objective_readback_difference_db2':max_obj_error,
    'max_distance_readback_difference_m':max_distance_diff,
    'max_signed_objective_readback_difference_db2':max_signed_diff,
    'max_movement_readback_difference_m':max_movement_diff,
    'support_counts':counts,'found_diameters_by_remaining_receivers':by_n,
    'max_found_diameter_U_ge3_m':max(diameters[h] for h,c in cells.items() if c['remaining_receivers']>=3),
    'positive_outside_K_by_policy':positive.groupby('policy').full_position_outside_K.sum().astype(int).to_dict(),
    'limitations':['Found pools are not exact global minimizer sets or complete near-optimal regions.',
      'Original full incumbent positions are retained; separate branch sensitivity still applies.',
      'No certified eta or curvature/separation constant is supplied.',
      'No new localization solves were run by this verification.']}
(P/'INDEPENDENT_REMOVAL_REVIEW.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
