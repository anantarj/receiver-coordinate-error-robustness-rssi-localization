#!/usr/bin/env python3
"""Fit/validation secondary localization: unchanged solver, complete candidates.

Root reviews this file, then prepares the lock and runs a one-worker pilot/full
run. Per-block query chunks are immutable verified checkpoints. Every stored
state maps to an exact numerical input and its complete observed candidate pool.
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, hashlib, importlib.util, json, os, struct, time
from pathlib import Path
for _v in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[_v]='1'
import numpy as np
from calibration_quality import ROOT, BASE, sha, save_npz, write_json, load

SOLVER_PATH=BASE/'src/rss_nlls_production.py'
POLICIES=['frozen','refit','selected']
BANDS=np.array([.01,.001,.0001])
MAXC=39
SOLVER=None
CAPTURE=None

def payload(a,s,i):
    return (b'PAPERB_CANDIDATE_INPUT_V1\0'+struct.pack('<Idd',len(s),4.7,1.)+
            np.asarray(a,dtype='<f8').tobytes()+np.asarray(s,dtype='<f8').tobytes()+np.asarray(i,dtype='<f8').tobytes())

def initialize():
    global SOLVER
    spec=importlib.util.spec_from_file_location('calibration_extension_original_solver',SOLVER_PATH)
    SOLVER=importlib.util.module_from_spec(spec);spec.loader.exec_module(SOLVER)
    original_search=SOLVER._local_search
    def observer(starts,scale,args,max_nfev):
        global CAPTURE
        result=original_search(starts,scale,args,max_nfev)
        CAPTURE=(starts,scale,args,result)
        return result
    SOLVER._local_search=observer

def capture(a,s,i):
    result=SOLVER.solve(a,s,i,4.7,1.)
    starts,scale,args,raw=CAPTURE;best,upper,best_index,best_source,records=raw
    origin=np.asarray(result['search_origin_m']);points=[]
    def retain(point,recorded,kind,index,status=-100,success=False,exception=''):
        if np.isfinite(point).all() and np.isfinite(recorded):
            recomputed=SOLVER.objective(point,*args)
            assert abs(recomputed-recorded)<=1e-8,'Candidate objective recomputation mismatch'
            points.append(dict(local=np.asarray(point),position=np.asarray(point)+origin,objective=recomputed,
                               recorded=recorded,kind=kind,index=index,status=status,success=success,exception=exception))
    for si,(start,rec) in enumerate(zip(starts,records)):
        retain(start,SOLVER.objective(start,*args),0,si)
        retain(rec['point'],rec['objective'],1,si,rec['status'],rec['success'],rec['exception'])
    incumbent_slot=len(points)
    if result['finite_output']:retain(best,upper,2,best_index)
    assert len(points)<=MAXC
    if result['finite_output']:
        assert len(points)>incumbent_slot and points[incumbent_slot]['objective']==min(p['objective'] for p in points)
        assert np.array_equal(points[incumbent_slot]['position'],result['position_m'])
    return result,points,incumbent_slot

def prepare(chunk):
    lp=ROOT/'protocol/EXTENSION_QUERY_LOCK.json'
    assert not lp.exists(),'Query execution is already locked.'
    receipt=ROOT/'receipts/EXTENSION_PREPARATION_RECEIPT.json'
    r=json.loads(receipt.read_text());assert r['status']=='COMPLETE_INPUTS_PREPARED_NO_QUERY_LOCALIZATION'
    inputs=sorted((ROOT/'inputs/blocks').glob('*.npz'));assert len(inputs)==4
    bindings={str(p.relative_to(ROOT)):sha(p) for p in inputs}
    for p in [Path(__file__),ROOT/'src/calibration_quality.py',ROOT/'protocol/CALIBRATION_PROTOCOL.json',ROOT/'receipts/EXTENSION_PREPARATION_RECEIPT.json']:
        bindings[str(p.relative_to(ROOT))]=sha(p)
    protocol={
        'status':'FIXED_BEFORE_SECONDARY_QUERY_LOCALIZATION','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'chronology':'Follow-up after original outcomes. Fit/validation partition and lambda selection already executed under separately frozen protocol; no query-localization outcomes yet.',
        'policies':POLICIES,'input_blocks':[str(p.relative_to(ROOT)) for p in inputs],
        'solver':'Unchanged original solve; 3x3 plus selected anchors, 200 residual evaluations/start, original tolerances and strict tie order.',
        'candidate_capture':'Read-only observer returns original _local_search result unchanged. Retain all finite initials, finite endpoints/fallbacks, explicit chosen incumbent, exact local coordinates and recomputed/recorded objectives.',
        'candidate_bands_db2':BANDS.tolist(),'candidate_kind':{'0':'initial','1':'endpoint_or_fallback','2':'selected_incumbent'},
        'candidate_scope':'Found finite candidates, not complete near-optimal regions, uniqueness proofs or confidence regions.',
        'input_hash':'Same PAPERB_CANDIDATE_INPUT_V1 ordered binary hash as original candidate recovery; exact input bytes checked on cache hit.',
        'cache':'Exact ordered coordinates/RSS/intercepts,n,d0 within each query chunk; repeated states retain separate state-to-input mappings.',
        'chunk_queries':chunk,'pilot':'First chunk of each of four predetermined blocks; no outcome-dependent case selection.',
        'controls':'Zero policies equal; unchanged receivers/metadata untouched; frozen/refit endpoints recomputed from fit-only observations; selected lambda fixed before query evaluation.',
        'aggregation':'Do not replace original estimates. Secondary finite selected-output results and found-candidate sensitivity must both be reported.',
        'source_bindings':bindings,'original_solver_sha256':sha(SOLVER_PATH),
    }
    write_json(lp,protocol);print(json.dumps({'locked':True,'sha256':sha(lp),'blocks':4,'chunk':chunk}),flush=True)

def verify():
    p=ROOT/'protocol/EXTENSION_QUERY_LOCK.json';lock=json.loads(p.read_text())
    for name,digest in lock['source_bindings'].items():assert sha(ROOT/name)==digest,name
    assert sha(SOLVER_PATH)==lock['original_solver_sha256']
    return lock

def run_shard(task):
    path,start,stop=task;path=Path(path);b=load(path);name=f'{path.stem}__{start:05d}_{stop:05d}'
    out=ROOT/'results/extension_query_shards'/(name+'.npz')
    cp=ROOT/'results/extension_candidate_shards'/(name+'.npz')
    receipt=ROOT/'receipts/extension_query_shards'/(name+'.json');locksha=sha(ROOT/'protocol/EXTENSION_QUERY_LOCK.json')
    if out.exists() and cp.exists() and receipt.exists():
        old=json.loads(receipt.read_text());assert old['output_sha256']==sha(out) and old['candidate_sha256']==sha(cp) and old['lock_sha256']==locksha
        return old
    began=time.monotonic();Q=stop-start;F=len(b['field_D_m']);shape=(F,3,Q)
    arrays={
        'nlls_position_m':np.full(shape+(2,),np.nan),'nlls_objective_db2':np.full(shape,np.nan),
        'nlls_finite':np.zeros(shape,bool),'nlls_status':np.full(shape,'not_executed',dtype='U64'),
        'nlls_local_runs':np.zeros(shape,np.int16),'nlls_local_converged':np.zeros(shape,np.int16),
        'nlls_local_failed':np.zeros(shape,np.int16),'nlls_local_exhausted':np.zeros(shape,np.int16),
        'nlls_nfev':np.zeros(shape,np.int32),'nlls_best_start':np.full(shape,-1,np.int16),
        'nlls_competitive_diameter_m':np.full(shape,np.nan),'nlls_competitive_count':np.zeros(shape,np.int16),
        'nlls_input_index':np.full(shape,-1,np.int32),'nlls_input_sha256':np.full(shape,'',dtype='U64'),
        'exact_input_reused':np.zeros(shape,bool),'wcl_position_m':np.full(shape+(2,),np.nan),
        'wcl_target_mass':np.zeros(shape),'wcl_effective_weight_count':np.zeros(shape),
        'source_rows':b['source_rows'][start:stop],'query_indices':np.arange(start,stop),
        'field_D_m':b['field_D_m'],'field_draw':b['field_draw'],'field_target_count':b['field_target_count'],
        'field_selected_lambda':b['field_selected_lambda'],'policies':np.array(POLICIES),
    }
    cache={};unique=[];exceptions=[]
    for fi in range(F):
        anchors=b['field_anchors_m'][fi]
        for pi,A in enumerate([b['reference_intercepts_dbm'],b['field_refit_intercepts_dbm'][fi],b['field_selected_intercepts_dbm'][fi]]):
            for qi,q in enumerate(range(start,stop)):
                mask=b['selected_mask'][q].astype(bool);ids=b['selected_ids'][q,mask].astype(int)-1
                aa=anchors[ids];ss=b['query_rssi_dbm'][q,mask];av=A[ids];idx=(fi,pi,qi)
                lw=(np.log(10.)/10.)*(ss-av);w=np.exp(lw-lw.max());w/=w.sum()
                arrays['wcl_position_m'][idx]=(w[:,None]*(aa-aa[0])).sum(axis=0)+aa[0]
                arrays['wcl_target_mass'][idx]=w[b['field_target_mask'][fi,ids]].sum();arrays['wcl_effective_weight_count'][idx]=1./(w@w)
                data=payload(aa,ss,av);digest=hashlib.sha256(data).hexdigest();reuse=digest in cache
                if reuse:
                    uid=cache[digest];item=unique[uid];assert item['payload']==data
                else:
                    uid=len(unique)
                    try:
                        result,points,incumbent=capture(aa,ss,av)
                    except Exception as exc:
                        result={'finite_output':False,'position_m':[np.nan,np.nan],'objective_db2':np.nan,'status':'exception_'+type(exc).__name__}
                        points=[];incumbent=-1;exceptions.append(dict(field=fi,policy=pi,source_row=int(b['source_rows'][q]),type=type(exc).__name__,message=str(exc)))
                    item=dict(payload=data,digest=digest,result=result,points=points,incumbent=incumbent,receivers=len(ss));unique.append(item);cache[digest]=uid
                res=item['result'];arrays['nlls_input_index'][idx]=uid;arrays['nlls_input_sha256'][idx]=digest;arrays['exact_input_reused'][idx]=reuse
                arrays['nlls_position_m'][idx]=res['position_m'];arrays['nlls_objective_db2'][idx]=res['objective_db2'];arrays['nlls_finite'][idx]=res['finite_output'];arrays['nlls_status'][idx]=res['status']
                for dst,src in [('nlls_local_runs','local_runs'),('nlls_local_converged','local_runs_converged'),('nlls_local_failed','local_runs_failed'),('nlls_local_exhausted','local_runs_budget_exhausted'),('nlls_nfev','nfev_total'),('nlls_best_start','best_start_index'),('nlls_competitive_diameter_m','competitive_diameter_m'),('nlls_competitive_count','competitive_local_solution_count')]:
                    arrays[dst][idx]=res.get(src,np.nan if 'diameter' in dst else (-1 if 'best_start' in dst else 0))
    K=len(unique)
    cand={
        'input_index':np.arange(K,dtype=np.int32),'input_sha256':np.array([u['digest'] for u in unique]),'receiver_count':np.array([u['receivers'] for u in unique],np.int16),
        'candidate_position_m':np.full((K,MAXC,2),np.nan),'candidate_local_position_m':np.full((K,MAXC,2),np.nan),
        'candidate_objective_db2':np.full((K,MAXC),np.nan),'candidate_recorded_objective_db2':np.full((K,MAXC),np.nan),
        'candidate_valid':np.zeros((K,MAXC),bool),'candidate_kind':np.full((K,MAXC),-1,np.int8),
        'candidate_start_index':np.full((K,MAXC),-1,np.int16),'candidate_local_status':np.full((K,MAXC),-100,np.int16),
        'candidate_local_converged':np.zeros((K,MAXC),bool),'candidate_exception':np.full((K,MAXC),'',dtype='U48'),
        'candidate_count':np.zeros(K,np.int16),'selected_candidate_slot':np.array([u['incumbent'] for u in unique],np.int16),
        'search_origin_m':np.full((K,2),np.nan),'search_scale_m':np.full(K,np.nan),
        'selected_position_m':np.array([u['result']['position_m'] for u in unique]),'selected_objective_db2':np.array([u['result']['objective_db2'] for u in unique]),
        'candidate_bands_db2':BANDS,'candidate_in_band':np.zeros((K,len(BANDS),MAXC),bool),'candidate_band_diameter_m':np.full((K,len(BANDS)),np.nan),
    }
    for k,item in enumerate(unique):
        points=item['points'];cand['candidate_count'][k]=len(points);res=item['result']
        cand['search_origin_m'][k]=res.get('search_origin_m',[np.nan,np.nan]);cand['search_scale_m'][k]=res.get('search_scale_m',np.nan)
        for j,p in enumerate(points):
            for dst,src in [('candidate_position_m','position'),('candidate_local_position_m','local'),('candidate_objective_db2','objective'),('candidate_recorded_objective_db2','recorded'),('candidate_kind','kind'),('candidate_start_index','index'),('candidate_local_status','status'),('candidate_local_converged','success'),('candidate_exception','exception')]:cand[dst][k,j]=p[src]
            cand['candidate_valid'][k,j]=True
        if points:
            for bi,band in enumerate(BANDS):
                keep=cand['candidate_valid'][k]&(cand['candidate_objective_db2'][k]<=min(p['objective'] for p in points)+band)
                cand['candidate_in_band'][k,bi]=keep;xy=cand['candidate_position_m'][k,keep]
                cand['candidate_band_diameter_m'][k,bi]=float(np.max(np.linalg.norm(xy[:,None]-xy[None,:],axis=-1)))
    save_npz(out,**arrays);save_npz(cp,**cand)
    rec=dict(status='COMPLETE' if not exceptions else 'COMPLETE_WITH_EXCEPTIONS',block=path.stem,start=start,stop=stop,
             queries=Q,fields=F,stored_states=int(F*3*Q),unique_solves=K,finite_states=int(arrays['nlls_finite'].sum()),
             seconds=time.monotonic()-began,exceptions=exceptions,input_sha256=sha(path),lock_sha256=locksha,
             output_sha256=sha(out),candidate_sha256=sha(cp),candidate_count=int(cand['candidate_count'].sum()))
    write_json(receipt,rec);return rec

def run(mode,workers):
    lock=verify();chunk=lock['chunk_queries'];paths=[ROOT/p for p in lock['input_blocks']];tasks=[]
    for p in paths:
        q=len(load(p)['source_rows']);starts=[0] if mode=='pilot' else list(range(0,q,chunk))
        tasks.extend((str(p),s,min(s+chunk,q)) for s in starts)
    began=time.monotonic();results=[]
    with cf.ProcessPoolExecutor(max_workers=workers,initializer=initialize) as pool:
        future={pool.submit(run_shard,t):t for t in tasks}
        for f in cf.as_completed(future):
            rec=f.result();results.append(rec)
            print(json.dumps({'done':len(results),'total':len(tasks),'block':rec['block'],'rows':[rec['start'],rec['stop']],'seconds':round(time.monotonic()-began,1)}),flush=True)
            write_json(ROOT/'receipts/EXTENSION_QUERY_PROGRESS.json',dict(mode=mode,completed_shards=len(results),expected_shards=len(tasks),seconds=time.monotonic()-began,last=rec))
    verify()
    if mode=='run':
        for p in paths:
            bb=load(p);parts=[load(ROOT/'results/extension_query_shards'/f'{p.stem}__{s:05d}_{min(s+chunk,len(bb["source_rows"])):05d}.npz') for s in range(0,len(bb['source_rows']),chunk)]
            merged={}
            for key in parts[0]:
                if key.startswith('field_') or key=='policies':
                    assert all(np.array_equal(x[key],parts[0][key]) for x in parts);merged[key]=parts[0][key]
                else:merged[key]=np.concatenate([x[key] for x in parts],axis=0 if key in ['source_rows','query_indices'] else 2)
            assert np.array_equal(merged['source_rows'],bb['source_rows'])
            # nlls_input_index is shard-local; source-row query chunk locates pool.
            save_npz(ROOT/'results/extension_query_arrays'/p.name,**merged)
    write_json(ROOT/'receipts'/f'EXTENSION_QUERY_{mode.upper()}_RECEIPT.json',dict(status='COMPLETE',mode=mode,seconds=time.monotonic()-began,shards=len(results),
              stored_states=sum(r['stored_states'] for r in results),unique_solves_within_shards=sum(r['unique_solves'] for r in results),
              exceptions=sum(len(r['exceptions']) for r in results),lock_sha256=sha(ROOT/'protocol/EXTENSION_QUERY_LOCK.json'),
              output_arrays={p.name:sha(p) for p in sorted((ROOT/'results/extension_query_arrays').glob('*.npz'))} if mode=='run' else {}))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','pilot','run']);ap.add_argument('--chunk',type=int,default=16);ap.add_argument('--workers',type=int,default=1);args=ap.parse_args()
    if args.mode=='prepare':prepare(args.chunk)
    else:run(args.mode,args.workers)
