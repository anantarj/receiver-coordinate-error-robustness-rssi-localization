#!/usr/bin/env python3
"""Independent final calibration query/candidate verification. No optimizer calls."""
from pathlib import Path
import hashlib,json,struct,time
import numpy as np
P=Path(__file__).resolve().parent;R=P.parent;C=R/'calibration';OLD=R.parent/'paperb_execution_20261015'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):
    with np.load(p,allow_pickle=False) as f:return {k:f[k] for k in f.files}
def payload(a,s,i):
    return b'PAPERB_CANDIDATE_INPUT_V1\0'+struct.pack('<Idd',len(s),4.7,1.)+b''.join(np.asarray(x,dtype='<f8').tobytes(order='C') for x in (a,s,i))
def check_originals():
    baseline=json.loads((R/'protocol/BASELINE_INTEGRITY.json').read_text());lp=OLD/'protocol/EXECUTION_LOCK.json'
    assert sha(lp)==baseline['original_execution_lock_sha256']
    lock=json.loads(lp.read_text())
    for name,digest in lock['bound_files'].items():assert sha(OLD/name)==digest,name
    receipt=json.loads((OLD/'receipts/PRIMARY_RUN_RECEIPT.json').read_text())
    for name,digest in receipt['output_arrays'].items():assert sha(OLD/'results/arrays'/name)==digest,name
    # Public distribution omits only document checks; all scientific checks above remain.
    excluded=json.loads((R.parent/'PUBLIC_DOCUMENT_EXCLUSIONS.json').read_text())['files']
    withheld={x['path']:x['sha256'] for x in excluded}
    for name,digest in baseline['original_pdf_hashes'].items():
        assert withheld.get('paperb_execution_20261015/delivery/'+name)==digest,name
    return {'bound_original_files':len(lock['bound_files']),'original_primary_arrays':len(receipt['output_arrays']),
            'original_pdf_hashes_found':0,'document_hashes_withheld_not_reverified':len(baseline['original_pdf_hashes'])}
def main():
    began=time.monotonic();lp=C/'protocol/EXTENSION_QUERY_LOCK.json';lock=json.loads(lp.read_text());locksha=sha(lp)
    finalp=C/'receipts/EXTENSION_QUERY_RUN_RECEIPT.json'
    assert finalp.exists(),'Final query run is not complete yet'
    final=json.loads(finalp.read_text());assert final['status']=='COMPLETE' and final['exceptions']==0
    assert final['lock_sha256']==locksha
    for name,digest in lock['source_bindings'].items():assert sha(C/name)==digest,name
    assert sha(OLD/'src/rss_nlls_production.py')==lock['original_solver_sha256']
    originalcheck=check_originals()
    expected_names=[];states=0;cells=0;candidates=0;receipts={};global_seen={};max_objdiff=0.;max_recorddiff=0.;max_duplicate_position=0.;max_duplicate_objective=0.;max_diameterdiff=0.;nonconverged_states=0;block_summaries={}
    for block in lock['input_blocks']:
        path=C/block;b=load(path);Q=len(b['source_rows']);F=len(b['field_D_m']);chunk=int(lock['chunk_queries']);mergedp=C/'results/extension_query_arrays'/path.name
        original_cohort=load(OLD/'inputs/blocks'/path.name.replace('_fitval_','_'))
        assert np.array_equal(b['source_rows'],original_cohort['source_rows'])
        assert np.array_equal(b['selected_ids'],original_cohort['selected_ids']) and np.array_equal(b['selected_mask'],original_cohort['selected_mask'])
        assert sha(mergedp)==final['output_arrays'][path.name];merged=load(mergedp);parts=[];query_seen=np.zeros(Q,int);blockstates=0;blockcells=0
        assert np.array_equal(merged['source_rows'],b['source_rows'])
        assert np.array_equal(merged['query_indices'],np.arange(Q))
        for start in range(0,Q,chunk):
            stop=min(start+chunk,Q);stem=f'{path.stem}__{start:05d}_{stop:05d}';expected_names.append(stem+'.json')
            recp=C/'receipts/extension_query_shards'/(stem+'.json');rec=json.loads(recp.read_text())
            assert rec['status']=='COMPLETE' and rec['exceptions']==[]
            assert rec['input_sha256']==sha(path) and rec['lock_sha256']==locksha
            assert rec['start']==start and rec['stop']==stop and rec['block']==path.stem
            outp=C/'results/extension_query_shards'/(stem+'.npz');candp=C/'results/extension_candidate_shards'/(stem+'.npz')
            assert sha(outp)==rec['output_sha256'] and sha(candp)==rec['candidate_sha256']
            out=load(outp);cand=load(candp);parts.append(out);query_seen[start:stop]+=1
            assert out['nlls_finite'].all() and np.isfinite(out['nlls_position_m']).all() and np.isfinite(out['nlls_objective_db2']).all()
            assert np.isfinite(out['wcl_position_m']).all()
            assert rec['finite_states']==rec['stored_states']==F*3*(stop-start)
            K=len(cand['input_index']);assert np.array_equal(cand['input_index'],np.arange(K))
            assert len(np.unique(cand['input_sha256']))==K==rec['unique_solves']
            assert np.array_equal(out['source_rows'],b['source_rows'][start:stop]);assert np.array_equal(out['query_indices'],np.arange(start,stop))
            input_cache={}
            for fi in range(F):
              for pi,A in enumerate((b['reference_intercepts_dbm'],b['field_refit_intercepts_dbm'][fi],b['field_selected_intercepts_dbm'][fi])):
                for local,q in enumerate(range(start,stop)):
                    mask=b['selected_mask'][q].astype(bool);ix=b['selected_ids'][q,mask].astype(int)-1
                    a=b['field_anchors_m'][fi,ix];s=b['query_rssi_dbm'][q,mask];intercept=A[ix]
                    raw=payload(a,s,intercept);d=hashlib.sha256(raw).hexdigest();idx=(fi,pi,local);uid=int(out['nlls_input_index'][idx])
                    assert d==out['nlls_input_sha256'][idx]==cand['input_sha256'][uid]
                    if uid in input_cache:assert input_cache[uid][0]==raw
                    else:input_cache[uid]=(raw,a,s,intercept)
                    selected=int(cand['selected_candidate_slot'][uid]);assert cand['candidate_valid'][uid,selected]
                    assert np.array_equal(out['nlls_position_m'][idx],cand['candidate_position_m'][uid,selected])
                    assert out['nlls_objective_db2'][idx]==cand['candidate_objective_db2'][uid,selected]
                    states+=1;blockstates+=1
                    nonconverged_states+=int(out['nlls_local_converged'][idx]<out['nlls_local_runs'][idx])
            assert set(input_cache)==set(range(K))
            for uid,(_,a,s,intercept) in input_cache.items():
                m=len(s);count=int(cand['candidate_count'][uid]);valid=cand['candidate_valid'][uid];slot=int(cand['selected_candidate_slot'][uid]);origin=a.mean(axis=0)
                assert count==2*(9+m)+1 and np.array_equal(valid,np.arange(len(valid))<count)
                assert slot==count-1 and cand['candidate_kind'][uid,slot]==2
                assert np.array_equal(cand['candidate_kind'][uid,:count-1],np.tile([0,1],9+m))
                assert np.array_equal(cand['candidate_start_index'][uid,:count-1],np.repeat(np.arange(9+m),2))
                x=cand['candidate_local_position_m'][uid,valid];xy=cand['candidate_position_m'][uid,valid];j=cand['candidate_objective_db2'][uid,valid]
                assert np.array_equal(x+origin,xy) and np.array_equal(cand['search_origin_m'][uid],origin)
                assert np.isfinite(x).all() and np.isfinite(j).all()
                rr=s-intercept+47*np.log10(np.sqrt(np.sum((x[:,None,:]-(a-origin)[None,:,:])**2,axis=2))+1.)
                direct=np.sum(rr*rr,axis=1);diff=float(np.max(abs(direct-j)));max_objdiff=max(max_objdiff,diff);assert diff<=1e-8
                rd=float(np.max(abs(j-cand['candidate_recorded_objective_db2'][uid,valid])));max_recorddiff=max(max_recorddiff,rd);assert rd<=1e-8
                assert j[-1]==min(j) and np.array_equal(cand['selected_position_m'][uid],xy[-1]) and cand['selected_objective_db2'][uid]==j[-1]
                for bi,band in enumerate(cand['candidate_bands_db2']):
                    keep=valid&(cand['candidate_objective_db2'][uid]<=min(j)+band);assert np.array_equal(keep,cand['candidate_in_band'][uid,bi])
                    pc=cand['candidate_position_m'][uid,keep];diam=float(np.max(np.linalg.norm(pc[:,None,:]-pc[None,:,:],axis=2)))
                    dd=abs(diam-float(cand['candidate_band_diameter_m'][uid,bi]));max_diameterdiff=max(max_diameterdiff,dd);assert dd<=1e-8
                d=str(cand['input_sha256'][uid]);pos=cand['selected_position_m'][uid];obj=float(cand['selected_objective_db2'][uid])
                if d in global_seen:
                    oldpos,oldobj=global_seen[d];dp=float(np.linalg.norm(pos-oldpos));dj=abs(obj-oldobj);max_duplicate_position=max(max_duplicate_position,dp);max_duplicate_objective=max(max_duplicate_objective,dj);assert dp<=1e-6 and dj<=1e-8
                else:global_seen[d]=(pos.copy(),obj)
            assert rec['candidate_count']==int(cand['candidate_count'].sum())
            cells+=K;blockcells+=K;candidates+=int(cand['candidate_count'].sum());receipts[recp.name]=sha(recp)
        assert np.all(query_seen==1)
        for key in merged:
            if key.startswith('field_') or key=='policies':
                assert all(np.array_equal(x[key],merged[key],equal_nan=True) if merged[key].dtype.kind not in 'US' else np.array_equal(x[key],merged[key]) for x in parts)
            else:
                concatenated=np.concatenate([x[key] for x in parts],axis=0 if key in ('source_rows','query_indices') else 2)
                assert np.array_equal(concatenated,merged[key],equal_nan=True) if merged[key].dtype.kind not in 'US' else np.array_equal(concatenated,merged[key])
        for pi in (1,2):
            assert np.array_equal(merged['nlls_position_m'][0,0],merged['nlls_position_m'][0,pi])
            assert np.array_equal(merged['wcl_position_m'][0,0],merged['wcl_position_m'][0,pi])
        block_summaries[path.stem]={'queries':Q,'fields':F,'states':blockstates,'shard_local_unique_inputs':blockcells}
    assert len(expected_names)==128 and final['shards']==128
    assert set(expected_names)=={p.name for p in (C/'receipts/extension_query_shards').glob('*.json')}
    assert states==final['stored_states']==sum(x['queries']*x['fields']*3 for x in block_summaries.values())
    assert cells==final['unique_solves_within_shards']
    assert originalcheck==check_originals()
    result={'status':'PASS_COMPLETE_INDEPENDENT_VERIFICATION','checked_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'expected_and_verified_shards':len(expected_names),'all_finite_stored_states':states,'shard_local_distinct_inputs_checked':cells,'global_distinct_numerical_inputs':len(global_seen),'retained_candidate_records_checked':candidates,'exceptions':0,'states_with_any_local_nonconvergence':nonconverged_states,'max_candidate_direct_formula_difference_db2':max_objdiff,'max_recorded_candidate_objective_difference_db2':max_recorddiff,'max_band_diameter_difference_m':max_diameterdiff,'identical_input_max_selected_position_difference_m':max_duplicate_position,'identical_input_max_selected_objective_difference_db2':max_duplicate_objective,'original_integrity':originalcheck,'blocks':block_summaries,'lock_sha256':locksha,'final_run_receipt_sha256':sha(finalp),'verification_script_sha256':sha(__file__),'checked_shard_receipt_sha256':receipts,'scope':'Read-only independent formulas, full input/state/pool joins, candidate retention, all band memberships, complete exact query coverage, merged-array equality, zero-policy equality, duplicate-input consistency and original bound-file integrity. No optimizer called; no global optimality, completeness of minimizer sets or physical accuracy certification.','seconds':time.monotonic()-began}
    (P/'CALIBRATION_PUBLIC_INDEPENDENT_VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checked_shard_receipt_sha256'},indent=2))
if __name__=='__main__':main()
