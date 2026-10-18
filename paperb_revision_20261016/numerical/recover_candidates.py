#!/usr/bin/env python3
"""Additive, checkpointed candidate recovery; original numerical files are read only."""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import struct
import sys
import time
import zipfile

for _name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_name]='1'
import numpy as np
import scipy

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parents[1]/'paperb_execution_20261015'
SOLVER_PATH=OLD/'src/rss_nlls_production.py'
MAX_CANDIDATES=39
CHUNK=128
N=4.7
D0=1.0

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write_json(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
    temp.replace(p)

def save_npz(p,**arrays):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp')
    with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for key in sorted(arrays):
            a=np.asarray(arrays[key]);assert a.dtype.kind!='O'
            b=io.BytesIO();np.lib.format.write_array(b,a,allow_pickle=False)
            info=zipfile.ZipInfo(key+'.npy',(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,b.getvalue())
    temp.replace(p)

def verify_originals():
    lock=json.loads((OLD/'protocol/EXECUTION_LOCK.json').read_text())
    for key,value in lock['bound_files'].items():
        if sha(OLD/key)!=value: raise ValueError('Changed locked original '+key)
    rec=json.loads((OLD/'receipts/PRIMARY_RUN_RECEIPT.json').read_text())
    for key,value in rec['output_arrays'].items():
        if sha(OLD/'results/arrays'/key)!=value: raise ValueError('Changed original primary '+key)
    return rec

def input_bytes(anchors,rss,intercepts):
    m=len(rss)
    return (b'PAPERB_CANDIDATE_INPUT_V1\0'+struct.pack('<Idd',m,N,D0)+
            np.asarray(anchors,dtype='<f8').tobytes(order='C')+
            np.asarray(rss,dtype='<f8').tobytes(order='C')+
            np.asarray(intercepts,dtype='<f8').tobytes(order='C'))

def prepare():
    if (ROOT/'protocol/RECOVERY_LOCK.json').exists(): raise RuntimeError('Already locked; use run/resume')
    old_receipt=verify_originals()
    ids={};payloads=[];anchors=[];rss=[];intercepts=[];counts=[];digests=[]
    expected_position=[];expected_objective=[];expected_status=[];expected_diameter=[]
    bindings={};block_counts={};total=0;duplicate_discrepancy=0.0;duplicate_obj=0.0
    for p in sorted((OLD/'inputs/blocks').glob('*.npz')):
        original=OLD/'results/arrays'/p.name
        bindings[str(p.relative_to(OLD))]=sha(p);bindings[str(original.relative_to(OLD))]=sha(original)
        with np.load(p,allow_pickle=False) as b, np.load(original,allow_pickle=False) as out:
            sids=b['selected_ids'];mask=b['selected_mask'].astype(bool);qrss=b['query_rssi_dbm']
            coords=b['field_anchors_m'];refit=b['field_refit_intercepts_dbm'];reference=b['reference_intercepts_dbm']
            positions=out['nlls_position_m'];objectives=out['nlls_objective_db2'];statuses=out['nlls_status']
            diameter=out['nlls_competitive_diameter_m']
            mapping=np.full(objectives.shape,-1,dtype=np.int32)
            for fi in range(len(coords)):
                for pi in range(2):
                    fit=reference if pi==0 else refit[fi]
                    for qi in range(len(sids)):
                        selected=sids[qi,mask[qi]].astype(int)-1
                        aa=np.ascontiguousarray(coords[fi,selected],dtype=np.float64)
                        ss=np.ascontiguousarray(qrss[qi,mask[qi]],dtype=np.float64)
                        av=np.ascontiguousarray(fit[selected],dtype=np.float64)
                        payload=input_bytes(aa,ss,av);digest=hashlib.sha256(payload).hexdigest()
                        if digest not in ids:
                            uid=len(ids);ids[digest]=uid;payloads.append(payload)
                            anchors.append(aa);rss.append(ss);intercepts.append(av);counts.append(len(ss));digests.append(digest)
                            expected_position.append(positions[fi,pi,qi].copy());expected_objective.append(float(objectives[fi,pi,qi]))
                            expected_status.append(str(statuses[fi,pi,qi]));expected_diameter.append(float(diameter[fi,pi,qi]))
                        else:
                            uid=ids[digest]
                            if payloads[uid]!=payload: raise AssertionError('SHA collision')
                            dd=float(np.linalg.norm(positions[fi,pi,qi]-expected_position[uid]))
                            dj=abs(float(objectives[fi,pi,qi])-expected_objective[uid])
                            duplicate_discrepancy=max(duplicate_discrepancy,dd);duplicate_obj=max(duplicate_obj,dj)
                            if dd>1e-6 or dj>1e-8: raise AssertionError('Original identical-input outputs disagree')
                        mapping[fi,pi,qi]=uid
            save_npz(ROOT/'mappings'/p.name,input_id=mapping,source_rows=b['source_rows'],
                field_D_m=b['field_D_m'],field_draw=b['field_draw'],field_target_count=b['field_target_count'])
            block_counts[p.stem]={'stored_states':int(mapping.size),'unique_inputs_in_block':int(len(np.unique(mapping)))}
            total+=mapping.size
    count=len(ids)
    if count>old_receipt['unique_nlls_solves']: raise AssertionError('Too many global inputs')
    aa=np.full((count,10,2),np.nan);ss=np.full((count,10),np.nan);av=np.full((count,10),np.nan)
    for uid,m in enumerate(counts): aa[uid,:m]=anchors[uid];ss[uid,:m]=rss[uid];av[uid,:m]=intercepts[uid]
    save_npz(ROOT/'inputs/UNIQUE_INPUTS.npz',input_id=np.arange(count,dtype=np.int32),
        anchors_m=aa,rss_dbm=ss,intercepts_dbm=av,receiver_count=np.asarray(counts,np.int16),
        input_sha256=np.asarray(digests,dtype='U64'),n=np.asarray(N),d0_m=np.asarray(D0))
    save_npz(ROOT/'inputs/EXPECTED_PRIMARY.npz',position_m=np.asarray(expected_position),
        objective_db2=np.asarray(expected_objective),status=np.asarray(expected_status,dtype='U64'),
        competitive_diameter_m=np.asarray(expected_diameter))
    bindings['src/rss_nlls_production.py']=sha(SOLVER_PATH)
    bindings['protocol/EXECUTION_LOCK.json']=sha(OLD/'protocol/EXECUTION_LOCK.json')
    bindings['receipts/PRIMARY_RUN_RECEIPT.json']=sha(OLD/'receipts/PRIMARY_RUN_RECEIPT.json')
    write_json(ROOT/'protocol/ORIGINAL_BINDINGS.json',bindings)
    protocol={
        'status':'FIXED_BEFORE_CANDIDATE_RECOVERY',
        'scope':'Diagnostic follow-up after the observed competitive-diameter omission; not a new primary study.',
        'algorithm':'Unchanged original solve(); a read-only observer captures the return of its unchanged _local_search.',
        'solver_inputs':'Ordered numerical anchors, RSS, intercepts, n,d0 only. No query reference coordinates or WCL output.',
        'input_order':'Sorted original block names, field index, policy index, query index; first occurrence assigns input_id.',
        'input_hash':'SHA256 of version prefix + little-endian uint32 receiver count,float64 n,d0 + little-endian float64 anchor,RSS,intercept arrays in selected order.',
        'candidate_order':'For each start: initial then finite recorded endpoint/fallback; final slot explicitly repeats the selected incumbent.',
        'max_candidates':MAX_CANDIDATES,'candidate_kind':{'0':'initial','1':'endpoint_or_recorded_fallback','2':'selected_incumbent'},
        'candidate_objective':'Recomputed at the exact captured local coordinate using the original objective; original recorded value retained and compared.',
        'candidate_bands_db2':[0.01,0.001,0.0001],
        'interpretation':'Found finite candidates only, not true near-global-optimal sets; objective bands are not statistical confidence.',
        'reproduction_trigger_m':1e-6,'reproduction_trigger_db2':1e-8,
        'reproduction_action':'Checkpoint discrepancies and stop; diagnose before continuing. Never overwrite original predictions.',
        'chunk_unique_inputs':CHUNK,'pilot':'64 input IDs selected by increasing SHA256(input digest) ordering; same checkpoints reused by full run.',
        'full_workload_max':122336,'global_unique_inputs':count,'stored_state_count':int(total),
        'stronger_audits':'Not run by this recovery. Separate predetermined schedule and lock required, max900 distinct inputs.',
        'runtime':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
        'blocks':block_counts,'original_identical_input_max_position_difference_m':duplicate_discrepancy,
        'original_identical_input_max_objective_difference_db2':duplicate_obj}
    write_json(ROOT/'protocol/RECOVERY_PROTOCOL.json',protocol)
    pilot=sorted(range(count),key=lambda i:hashlib.sha256(digests[i].encode()).hexdigest())[:64]
    write_json(ROOT/'protocol/PILOT_INPUT_IDS.json',pilot)
    local_paths=[Path(__file__),ROOT/'protocol/RECOVERY_PROTOCOL.json',ROOT/'protocol/PILOT_INPUT_IDS.json',
                 ROOT/'protocol/ORIGINAL_BINDINGS.json',ROOT/'inputs/UNIQUE_INPUTS.npz',ROOT/'inputs/EXPECTED_PRIMARY.npz']
    local_paths+=sorted((ROOT/'mappings').glob('*.npz'))
    lock={'status':'LOCKED_BEFORE_RECOVERY_OUTPUTS','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'original_root':str(OLD),'local_bindings':{str(p.relative_to(ROOT)):sha(p) for p in local_paths},
        'original_solver_sha256':sha(SOLVER_PATH)}
    write_json(ROOT/'protocol/RECOVERY_LOCK.json',lock)
    print(json.dumps({'prepared':True,'global_unique_inputs':count,'stored_states':int(total),'lock_sha256':sha(ROOT/'protocol/RECOVERY_LOCK.json')}),flush=True)

REG=None;EXPECT=None;SOLVER=None;CAPTURE=None;LOCK_HASH=None

def initialize():
    global REG,EXPECT,SOLVER,LOCK_HASH
    REG={k:v for k,v in np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False).items()}
    EXPECT={k:v for k,v in np.load(ROOT/'inputs/EXPECTED_PRIMARY.npz',allow_pickle=False).items()}
    spec=importlib.util.spec_from_file_location('locked_original_rss_nlls_production',SOLVER_PATH)
    SOLVER=importlib.util.module_from_spec(spec);spec.loader.exec_module(SOLVER)
    unchanged_search=SOLVER._local_search
    def observer(starts,scale,args,max_nfev):
        global CAPTURE
        result=unchanged_search(starts,scale,args,max_nfev)
        CAPTURE=(starts,scale,args,result)
        return result
    SOLVER._local_search=observer
    LOCK_HASH=sha(ROOT/'protocol/RECOVERY_LOCK.json')

def recover_shard(task):
    name,identifiers=task
    dest=ROOT/'candidates'/(name+'.npz');receipt=ROOT/'receipts'/(name+'.json')
    if receipt.exists() and dest.exists():
        rec=json.loads(receipt.read_text())
        if rec['output_sha256']!=sha(dest) or rec['lock_sha256']!=LOCK_HASH: raise ValueError('Changed checkpoint '+name)
        return rec
    ids=np.asarray(identifiers,dtype=np.int32);z=len(ids);c=MAX_CANDIDATES
    arrays={
        'input_id':ids,'candidate_position_m':np.full((z,c,2),np.nan),
        'candidate_local_position_m':np.full((z,c,2),np.nan),
        'candidate_objective_db2':np.full((z,c),np.nan),
        'candidate_recorded_objective_db2':np.full((z,c),np.nan),
        'candidate_valid':np.zeros((z,c),bool),'candidate_kind':np.full((z,c),-1,np.int8),
        'candidate_start_index':np.full((z,c),-1,np.int16),
        'candidate_local_status':np.full((z,c),-100,np.int16),
        'candidate_local_converged':np.zeros((z,c),bool),
        'candidate_exception':np.full((z,c),'',dtype='U48'),
        'candidate_count':np.zeros(z,np.int16),'selected_candidate_slot':np.full(z,-1,np.int16),
        'selected_position_m':np.full((z,2),np.nan),'selected_objective_db2':np.full(z,np.nan),
        'selected_source_kind':np.full(z,-1,np.int8),'selected_start_index':np.full(z,-1,np.int16),
        'search_origin_m':np.full((z,2),np.nan),'search_scale_m':np.full(z,np.nan),
        'original_status':np.full(z,'',dtype='U64'),'local_runs':np.zeros(z,np.int16),
        'local_converged':np.zeros(z,np.int16),'local_nfev_total':np.zeros(z,np.int32),
        'position_discrepancy_m':np.full(z,np.nan),'objective_discrepancy_db2':np.full(z,np.nan),
        'objective_recompute_discrepancy_db2':np.full(z,np.nan),
        'recovered_endpoint_diameter_m':np.full(z,np.nan)}
    began=time.monotonic();problems=[]
    for k,uid in enumerate(ids):
        m=int(REG['receiver_count'][uid]);aa=REG['anchors_m'][uid,:m];rr=REG['rss_dbm'][uid,:m];ai=REG['intercepts_dbm'][uid,:m]
        result=SOLVER.solve(aa,rr,ai,N,D0)
        starts,scale,args,raw=CAPTURE;best,upper,best_index,best_source,records=raw
        origin=np.asarray(result['search_origin_m'])
        if not result['finite_output']: raise RuntimeError('Unexpected nonfinite recovery input '+str(uid))
        slot=0;max_recompute=0.0
        def retain(point,recorded,kind,start_index,status=-100,success=False,exception=''):
            nonlocal slot,max_recompute
            if not np.isfinite(point).all() or not np.isfinite(recorded):return
            recomputed=SOLVER.objective(point,*args)
            if not np.isfinite(recomputed):raise RuntimeError('Finite candidate recomputed nonfinite')
            arrays['candidate_local_position_m'][k,slot]=point
            arrays['candidate_position_m'][k,slot]=point+origin
            arrays['candidate_objective_db2'][k,slot]=recomputed
            arrays['candidate_recorded_objective_db2'][k,slot]=recorded
            arrays['candidate_valid'][k,slot]=True;arrays['candidate_kind'][k,slot]=kind
            arrays['candidate_start_index'][k,slot]=start_index
            arrays['candidate_local_status'][k,slot]=status;arrays['candidate_local_converged'][k,slot]=success
            arrays['candidate_exception'][k,slot]=exception
            max_recompute=max(max_recompute,abs(recomputed-recorded));slot+=1
        for si,(start,record) in enumerate(zip(starts,records)):
            retain(start,SOLVER.objective(start,*args),0,si)
            retain(record['point'],record['objective'],1,si,record['status'],record['success'],record['exception'])
        arrays['selected_candidate_slot'][k]=slot
        retain(best,upper,2,best_index)
        arrays['candidate_count'][k]=slot
        arrays['selected_position_m'][k]=result['position_m'];arrays['selected_objective_db2'][k]=result['objective_db2']
        arrays['selected_source_kind'][k]=0 if best_source=='start' else 1;arrays['selected_start_index'][k]=best_index
        arrays['search_origin_m'][k]=origin;arrays['search_scale_m'][k]=scale;arrays['original_status'][k]=result['status']
        arrays['local_runs'][k]=result['local_runs'];arrays['local_converged'][k]=result['local_runs_converged'];arrays['local_nfev_total'][k]=result['nfev_total']
        dd=float(np.linalg.norm(arrays['selected_position_m'][k]-EXPECT['position_m'][uid]))
        dj=abs(float(result['objective_db2'])-float(EXPECT['objective_db2'][uid]))
        arrays['position_discrepancy_m'][k]=dd;arrays['objective_discrepancy_db2'][k]=dj
        arrays['objective_recompute_discrepancy_db2'][k]=max_recompute
        arrays['recovered_endpoint_diameter_m'][k]=result['competitive_diameter_m']
        if dd>1e-6 or dj>1e-8 or max_recompute>1e-8 or result['status']!=EXPECT['status'][uid]:
            problems.append({'input_id':int(uid),'position_difference_m':dd,'objective_difference_db2':dj,'candidate_objective_recompute_difference_db2':max_recompute,'status_changed':result['status']!=EXPECT['status'][uid]})
    save_npz(dest,**arrays)
    rec={'status':'COMPLETE' if not problems else 'INVESTIGATION_REQUIRED','name':name,'inputs':z,
        'input_ids_sha256':hashlib.sha256(ids.astype('<i4').tobytes()).hexdigest(),
        'output_sha256':sha(dest),'lock_sha256':LOCK_HASH,'seconds':time.monotonic()-began,
        'max_position_discrepancy_m':float(arrays['position_discrepancy_m'].max()),
        'max_objective_discrepancy_db2':float(arrays['objective_discrepancy_db2'].max()),
        'max_candidate_recompute_difference_db2':float(arrays['objective_recompute_discrepancy_db2'].max()),
        'candidate_count':int(arrays['candidate_count'].sum()),'problems':problems}
    write_json(receipt,rec)
    if problems:raise RuntimeError('Recovery discrepancy; preserved '+str(receipt))
    return rec

def verify_lock():
    lock=json.loads((ROOT/'protocol/RECOVERY_LOCK.json').read_text())
    for key,value in lock['local_bindings'].items():
        if sha(ROOT/key)!=value:raise ValueError('Changed recovery-bound file '+key)
    if sha(SOLVER_PATH)!=lock['original_solver_sha256']:raise ValueError('Changed original solver')
    verify_originals()
    return lock

def run(mode,workers):
    verify_lock();began=time.monotonic()
    with np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False) as f:count=len(f['input_id'])
    pilot=json.loads((ROOT/'protocol/PILOT_INPUT_IDS.json').read_text())
    if mode=='pilot': tasks=[(f'pilot_{i:03d}',pilot[i:i+16]) for i in range(0,len(pilot),16)]
    else:
        excluded=set(pilot);rest=[i for i in range(count) if i not in excluded]
        tasks=[(f'shard_{i:06d}_{min(i+CHUNK,len(rest)):06d}',rest[i:i+CHUNK]) for i in range(0,len(rest),CHUNK)]
        # Pilot outputs are part of the full capture and remain independently checkpointed.
        for i in range(0,len(pilot),16):
            p=ROOT/'receipts'/f'pilot_{i:03d}.json'
            if not p.exists() or json.loads(p.read_text())['status']!='COMPLETE':raise ValueError('Complete pilot required')
    done=[]
    with cf.ProcessPoolExecutor(max_workers=workers,initializer=initialize) as pool:
        future_map={pool.submit(recover_shard,t):t[0] for t in tasks}
        try:
            for future in cf.as_completed(future_map):
                rec=future.result();done.append(rec)
                progress={'mode':mode,'completed_shards':len(done),'expected_shards':len(tasks),
                    'completed_inputs':sum(x['inputs'] for x in done),'expected_inputs':sum(len(t[1]) for t in tasks),
                    'seconds':time.monotonic()-began,'workers':workers,'latest':rec['name']}
                write_json(ROOT/'receipts'/f'{mode.upper()}_PROGRESS.json',progress)
                if mode=='pilot' or len(done)%8==0 or len(done)==len(tasks):print(json.dumps(progress),flush=True)
        except BaseException:
            for future in future_map:future.cancel()
            raise
    verify_lock()
    receipt={'status':'COMPLETE','mode':mode,'seconds':time.monotonic()-began,'workers':workers,
        'completed_inputs':sum(x['inputs'] for x in done),'shards':len(done),
        'max_position_discrepancy_m':max(x['max_position_discrepancy_m'] for x in done),
        'max_objective_discrepancy_db2':max(x['max_objective_discrepancy_db2'] for x in done),
        'max_candidate_recompute_difference_db2':max(x['max_candidate_recompute_difference_db2'] for x in done),
        'candidate_count':sum(x['candidate_count'] for x in done),
        'lock_sha256':sha(ROOT/'protocol/RECOVERY_LOCK.json'),
        'outputs':{x['name']+'.npz':x['output_sha256'] for x in sorted(done,key=lambda x:x['name'])}}
    write_json(ROOT/'receipts'/f'{mode.upper()}_RECEIPT.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='outputs'}),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','pilot','run']);ap.add_argument('--workers',type=int,default=4)
    a=ap.parse_args()
    if a.action=='prepare':prepare()
    else:run(a.action,a.workers)
