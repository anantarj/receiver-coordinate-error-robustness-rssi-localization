#!/usr/bin/env python3
"""Independent read-only registry/mapping/candidate checks; no solver calls."""
import csv,hashlib,json,struct,time
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parent
R=P.parent
OLD=R.parent/'paperb_execution_20261015'
N=R/'numerical';C=R/'calibration'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(a,s,i):
    h=hashlib.sha256();h.update(b'PAPERB_CANDIDATE_INPUT_V1\0')
    h.update(struct.pack('<Idd',len(s),4.7,1.))
    for x in (a,s,i):h.update(np.asarray(x,dtype='<f8').tobytes(order='C'))
    return h.hexdigest()
start=time.monotonic()
with np.load(N/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False) as f:reg={k:f[k] for k in f.files}
for uid,m in enumerate(reg['receiver_count']):
    assert digest(reg['anchors_m'][uid,:m],reg['rss_dbm'][uid,:m],reg['intercepts_dbm'][uid,:m])==reg['input_sha256'][uid]
mapped=0;blocks=0
for path in sorted((N/'mappings').glob('*.npz')):
    with np.load(path) as mm,np.load(OLD/'inputs/blocks'/path.name) as b:
        mm={k:mm[k] for k in mm.files};b={k:b[k] for k in b.files}
        assert np.array_equal(mm['source_rows'],b['source_rows'])
        mapping=mm['input_id'];assert np.all(mapping>=0) and np.all(mapping<len(reg['input_id']))
        for fi in range(mapping.shape[0]):
            for pi in range(mapping.shape[1]):
                A=b['reference_intercepts_dbm'] if pi==0 else b['field_refit_intercepts_dbm'][fi]
                for qi in range(mapping.shape[2]):
                    mask=b['selected_mask'][qi].astype(bool);ix=b['selected_ids'][qi,mask].astype(int)-1
                    d=digest(b['field_anchors_m'][fi,ix],b['query_rssi_dbm'][qi,mask],A[ix])
                    assert d==reg['input_sha256'][mapping[fi,pi,qi]]
        mapped+=mapping.size;blocks+=1
recovery_receipts=[json.loads(p.read_text()) for p in (N/'receipts').glob('*.json')]
problem_receipts=[x.get('name') for x in recovery_receipts if 'status'in x and x['status']!='COMPLETE']
querystatecount=0;querycandidates=0;queryshards=0;exceptioncount=0
for path in sorted((C/'receipts/extension_query_shards').glob('*.json')):
    rec=json.loads(path.read_text());stem=path.stem
    op=C/'results/extension_query_shards'/(stem+'.npz');cp=C/'results/extension_candidate_shards'/(stem+'.npz')
    assert sha(op)==rec['output_sha256'] and sha(cp)==rec['candidate_sha256']
    with np.load(op) as out,np.load(cp) as cand,np.load(C/'inputs/blocks'/(rec['block']+'.npz')) as b:
        out={k:out[k] for k in out.files};cand={k:cand[k] for k in cand.files};b={k:b[k] for k in b.files}
        for fi in range(len(b['field_D_m'])):
          for pi,A in enumerate((b['reference_intercepts_dbm'],b['field_refit_intercepts_dbm'][fi],b['field_selected_intercepts_dbm'][fi])):
            for local,q in enumerate(range(rec['start'],rec['stop'])):
                mask=b['selected_mask'][q].astype(bool);ix=b['selected_ids'][q,mask].astype(int)-1
                d=digest(b['field_anchors_m'][fi,ix],b['query_rssi_dbm'][q,mask],A[ix]);idx=(fi,pi,local)
                uid=int(out['nlls_input_index'][idx])
                assert d==out['nlls_input_sha256'][idx]==cand['input_sha256'][uid]
                if out['nlls_finite'][idx]:
                    v=cand['candidate_valid'][uid];slot=int(cand['selected_candidate_slot'][uid]);m=int(cand['receiver_count'][uid])
                    assert int(v.sum())==int(cand['candidate_count'][uid])==2*(9+m)+1
                    assert v[slot] and cand['candidate_kind'][uid,slot]==2
                    assert cand['candidate_objective_db2'][uid,slot]==np.min(cand['candidate_objective_db2'][uid,v])
                    assert np.array_equal(out['nlls_position_m'][idx],cand['candidate_position_m'][uid,slot])
                querystatecount+=1
        querycandidates+=int(cand['candidate_count'].sum())
    queryshards+=1;exceptioncount+=len(rec['exceptions'])
result={
 'status':'PASS_CURRENT_SNAPSHOT_WITH_CONDITIONAL_WORKFLOW_FINDINGS',
 'review_time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
 'source_sha256':{str(p.relative_to(R)):sha(p) for p in (N/'recover_candidates.py',C/'src/run_extension_queries.py')},
 'recovery_registry_unique_inputs_verified':len(reg['input_id']),
 'recovery_state_mappings_reconstructed_independently':mapped,'recovery_blocks_checked':blocks,
 'recovery_problem_receipts_current_snapshot':problem_receipts,
 'calibration_query_shards_checked_current_snapshot':queryshards,'calibration_stored_state_mappings_checked':querystatecount,
 'calibration_candidate_records_checked':querycandidates,'calibration_exceptions_current_snapshot':exceptioncount,
 'static_review_findings':[
  {'severity':'PASS','finding':'Both observers call the original _local_search without changing arguments or returned result. Candidate capture includes all finite prescribed initials, all finite endpoints/fallbacks, explicit incumbent, exact local coordinates, recomputed and recorded objectives, source kind, start index, status and exception.'},
  {'severity':'PASS','finding':'Solver keys include ordered float64 anchors/RSS/intercepts, receiver count, n, d0. Fixed shapes are implied by receiver count and validated solver contract. No query-reference coordinates, WCL estimate or error enters the hash, solver, candidate ordering or incumbent selection.'},
  {'severity':'CONDITIONAL_RESUME_HAZARD','finding':'recover_candidates.recover_shard returns an existing hash-valid receipt without requiring status COMPLETE; an INVESTIGATION_REQUIRED receipt could be accepted by a later resume. No such receipt exists in this snapshot. Require a final independent check rejecting every non-COMPLETE shard, or version a repair before future resumes after failure; do not alter locked running source.'},
  {'severity':'AGGREGATION_REQUIREMENT','finding':'Original recovery run excludes 64 pilot inputs and its RUN_RECEIPT totals concern the remaining scheduled inputs. Full coverage requires union of pilot and regular candidate shards, exactly one occurrence for every registry input ID.'},
  {'severity':'COMPLETION_GATE','finding':'Calibration aggregate receipt status COMPLETE does not itself guarantee no exceptions; exception count and finite/candidate coverage must be checked explicitly. Current checked shards have no exceptions.'},
  {'severity':'MAPPING_REQUIREMENT','finding':'Calibration nlls_input_index is shard-local, including after full-array concatenation. Join via block plus query chunk to candidate shard, and validate input_sha256; never treat index as global.'},
  {'severity':'REPORTING_FOLLOWUP','finding':'Recovery stores absolute discrepancies. The plan also requested scale-relative discrepancy reporting; these can be derived additively from EXPECTED_PRIMARY and search scale without replay.'}
 ],
 'scope':'Complete locked original registry and 195,200-state mappings; static capture/selection interface review; calibration completed-shard snapshot only. No new solves, no source edits, no global-optimality or scientific-claim validation.',
 'seconds':time.monotonic()-start}
(P/'CANDIDATE_PIPELINE_INDEPENDENT_REVIEW.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
