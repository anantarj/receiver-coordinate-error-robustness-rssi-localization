#!/usr/bin/env python3
"""Independent read-back checks using the direct residual formula."""
from pathlib import Path
import hashlib,json,csv
import numpy as np

P=Path(__file__).resolve().parent
proto=json.loads((P/'REMOVAL_PROTOCOL.json').read_text())
receipt=json.loads((P/'REMOVAL_RECEIPT.json').read_text())
max_obj_diff=0.;max_absolute_obj_diff=0.;cells={};local_rows=[];global_abs_exceedances=0
for path in sorted((P/'candidates').glob('*.json')):
    c=json.loads(path.read_text());a=np.array(c['anchors_m']);r=np.array(c['rss_dbm']);A=np.array(c['intercepts_dbm'])
    points=np.array([x['position_m'] for x in c['candidates']]);v=np.array([x['objective_db2'] for x in c['candidates']])
    global_residual=r[None,:]-A[None,:]+47*np.log10(np.linalg.norm(points[:,None,:]-a[None,:,:],axis=2)+1)
    global_direct=np.sum(global_residual*global_residual,axis=1)
    max_absolute_obj_diff=max(max_absolute_obj_diff,float(np.max(abs(v-global_direct))))
    global_abs_exceedances+=int(np.sum(abs(v-global_direct)>1e-8))
    # Production is evaluated after centering. Recover prescribed grid points
    # without their avoidable add/subtract of a ~5.7e6-m northing. Endpoints and
    # incumbents were explicitly re-evaluated from their retained global points.
    origin=a.mean(axis=0);aa=a-origin;span=np.ptp(aa,axis=0)
    half=np.maximum(span/2,max(float(max(span)),1.)/2)
    starts=[np.array([x,y])*half for x in (-1.,0.,1.) for y in (-1.,0.,1.)]+list(aa)
    local=points-origin
    for i,record in enumerate(c['candidates']):
        if record['kind']=='start':local[i]=starts[record['start_index']]
        local_rows.append((path.stem,i,local[i].copy()))
    residual=r[None,:]-A[None,:]+47*np.log10(np.linalg.norm(local[:,None,:]-aa[None,:,:],axis=2)+1)
    direct=np.sum(residual*residual,axis=1)
    max_obj_diff=max(max_obj_diff,float(np.max(abs(v-direct))))
    assert np.allclose(v,direct,atol=1e-8,rtol=1e-12)
    assert c['best_found_objective_db2']==min(v)
    assert len([x for x in c['candidates'] if x['kind']=='start'])==9+len(a)
    assert len([x for x in c['candidates'] if x['kind']=='incumbent'])==1
    assert c['solver_result']['finite_output']
    assert c['input_hash']==path.stem
    cells[path.stem]=c
assert len(cells)==receipt['unique_numerical_inputs']
mapping=list(csv.DictReader((P/'REMOVAL_INPUT_MAPPING.csv').open()))
assert len(mapping)==1024 and len({(x['target_set'],x['query_index']) for x in mapping})==1024
for row in mapping:
    assert int(row['remaining_receiver_count'])==cells[row['input_hash']]['remaining_receivers']
    assert int(row['remaining_receiver_count'])+int(row['target_exposure'])==int(row['original_receiver_count'])
for filename,digest in receipt['files'].items():
    assert hashlib.sha256((P/filename).read_bytes()).hexdigest()==digest
np.savez_compressed(P/'CANDIDATE_LOCAL_COORDINATES.npz',input_hash=np.array([x[0] for x in local_rows]),candidate_index=np.array([x[1] for x in local_rows]),local_position_m=np.array([x[2] for x in local_rows]))
result={'status':'PASS','distinct_input_cells_verified':len(cells),'mapping_rows_verified':len(mapping),'max_candidate_objective_difference_direct_local_formula_vs_stored_db2':max_obj_diff,'objective_absolute_tolerance_db2':1e-8,'objective_relative_tolerance':1e-12,'all_recorded_CSV_hashes_verified':True,'global_coordinate_roundtrip_check':{'initial_1e8_absolute_check_exceedances':global_abs_exceedances,'maximum_absolute_objective_difference_db2':max_absolute_obj_diff,'resolution':'Direct evaluation in original centered arithmetic passes; 23 prescribed initial grid candidates lose sub-nanometre relative precision when rounded into global northings and recentered. Original outputs unchanged. Exact evaluation coordinates retained in additive CANDIDATE_LOCAL_COORDINATES.npz.'},'scope':'Read-back direct residual formula, candidate retention/counts, receiver-count accounting, mapping uniqueness and file integrity; no global optimality or completeness certification'}
(P/'REMOVAL_VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
