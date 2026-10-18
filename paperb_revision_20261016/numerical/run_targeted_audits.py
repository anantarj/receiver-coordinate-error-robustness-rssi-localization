#!/usr/bin/env python3
"""Separate bounded strong audits, retaining found candidates; never replace primary."""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import time
from pathlib import Path
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
import numpy as np
from recover_candidates import ROOT,OLD,SOLVER_PATH,sha,save_npz,write_json,verify_lock

REG=None;EXPECTED=None;SOLVER=None;BASE_OBJECTIVE=None;BASE_SEARCH=None;AUDIT_LOCK_SHA=None

def prepare():
    verify_lock()
    if (ROOT/'protocol/TARGETED_AUDIT_LOCK.json').exists():raise RuntimeError('Audit already locked')
    schedule=json.loads((ROOT/'protocol/TARGETED_AUDIT_SCHEDULE.json').read_text())
    if len(schedule['selected_input_ids'])>900:raise RuntimeError('Audit budget exceeded')
    protocol={'status':'FIXED_BEFORE_STRONG_AUDIT_OUTPUTS','source':'Bounded diagnostic follow-up; selection uses recorded primary/candidate difficulties.',
        'original_solver_unmodified':True,'primary_outputs_replaced':False,
        'selected_input_count':len(schedule['selected_input_ids']),
        'first_budget':30000,'one_escalation_budget':100000,'objective_gap_db2':0.01,
        'escalation':'Primary any-local-unconverged OR objective improvement>max(1e-4,1e-6*(1+Jprimary))dB2 OR position shift>1m. One repeated100000-split audit only.',
        'candidate_retention':'Every strong-search prescribed initial and recorded endpoint/fallback; primary incumbent; every strict improving objective evaluation observed during search; final audit incumbent. Superseded candidates retained. Not all evaluated box centres are retained.',
        'candidate_kind':{'0':'strong_initial','1':'strong_endpoint_or_fallback','2':'primary_incumbent','3':'strict_improving_objective_evaluation','4':'final_audit_incumbent'},
        'scope':'Finite found-candidate pools and numerically guarded objective bounds; no complete near-optimal set, directed-rounding proof, physical accuracy or uniqueness claim.',
        'maximum_distinct_inputs':900,'unresolved_gap_action':'Stop and retain unresolved status; no automatic additional study.',
        'objective_input':'Only coordinates,RSS,intercepts,n,d0; no query reference coordinates or WCL prediction.',
        'workers':'Execution resource only; no wall-time stopping rule.'}
    write_json(ROOT/'protocol/TARGETED_AUDIT_PROTOCOL.json',protocol)
    files=[Path(__file__),ROOT/'prepare_targeted_audit.py',ROOT/'recover_candidates.py',
        ROOT/'protocol/TARGETED_AUDIT_PROTOCOL.json',ROOT/'protocol/TARGETED_AUDIT_SCHEDULE.json',
        ROOT/'protocol/AUDIT_BASE_SELECTION.json',ROOT/'protocol/RECOVERY_LOCK.json',
        ROOT/'inputs/UNIQUE_INPUTS.npz',ROOT/'inputs/EXPECTED_PRIMARY.npz',
        ROOT/'receipts/PILOT_RECEIPT.json',ROOT/'receipts/RUN_RECEIPT.json',
        ROOT/'receipts/INDEPENDENT_RECOVERY_CHECK.json']
    lock={'status':'LOCKED_BEFORE_STRONG_AUDIT_OUTPUTS','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'bindings':{str(p.relative_to(ROOT)):sha(p) for p in files},'original_solver_sha256':sha(SOLVER_PATH)}
    write_json(ROOT/'protocol/TARGETED_AUDIT_LOCK.json',lock)
    print(json.dumps({'locked_inputs':len(schedule['selected_input_ids']),'lock_sha256':sha(ROOT/'protocol/TARGETED_AUDIT_LOCK.json')}),flush=True)

def check_lock():
    verify_lock()
    lock=json.loads((ROOT/'protocol/TARGETED_AUDIT_LOCK.json').read_text())
    for name,value in lock['bindings'].items():
        if sha(ROOT/name)!=value:raise RuntimeError('Changed audit-bound file '+name)
    if sha(SOLVER_PATH)!=lock['original_solver_sha256']:raise RuntimeError('Changed original solver')

def initialize():
    global REG,EXPECTED,SOLVER,BASE_OBJECTIVE,BASE_SEARCH,AUDIT_LOCK_SHA
    REG=dict(np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False));EXPECTED=dict(np.load(ROOT/'inputs/EXPECTED_PRIMARY.npz',allow_pickle=False))
    spec=importlib.util.spec_from_file_location('unchanged_solver_for_targeted_audit',SOLVER_PATH)
    SOLVER=importlib.util.module_from_spec(spec);spec.loader.exec_module(SOLVER)
    BASE_OBJECTIVE=SOLVER.objective;BASE_SEARCH=SOLVER._local_search
    AUDIT_LOCK_SHA=sha(ROOT/'protocol/TARGETED_AUDIT_LOCK.json')

def one_stage(uid,stage,budget):
    m=int(REG['receiver_count'][uid]);a=REG['anchors_m'][uid,:m];s=REG['rss_dbm'][uid,:m];intercept=REG['intercepts_dbm'][uid,:m]
    primary={'position_m':EXPECTED['position_m'][uid].tolist()}
    capture={};improvements=[];best_seen=float('inf')
    def objective_observer(point,*args):
        nonlocal best_seen
        value=BASE_OBJECTIVE(point,*args)
        if np.isfinite(value) and value<best_seen:
            best_seen=float(value);improvements.append((np.asarray(point).copy(),float(value)))
        return value
    def local_observer(starts,scale,args,max_nfev):
        result=BASE_SEARCH(starts,scale,args,max_nfev)
        capture.update(starts=starts,scale=scale,args=args,result=result)
        return result
    SOLVER.objective=objective_observer;SOLVER._local_search=local_observer
    result=SOLVER.audit(a,s,intercept,primary,4.7,1.,max_splits=budget,objective_tolerance_db2=.01)
    origin=a.mean(axis=0);args=capture['args'];raw=[]
    def retain(point,original,kind,index=-1,status=-100,converged=False):
        if not np.isfinite(point).all() or not np.isfinite(original):return
        raw.append((np.asarray(point).copy(),float(BASE_OBJECTIVE(point,*args)),float(original),kind,index,status,converged))
    for index,(point,record) in enumerate(zip(capture['starts'],capture['result'][4])):
        retain(point,BASE_OBJECTIVE(point,*args),0,index)
        retain(record['point'],record['objective'],1,index,record['status'],record['success'])
    primary_local=np.asarray(primary['position_m'])-origin
    retain(primary_local,BASE_OBJECTIVE(primary_local,*args),2)
    for point,value in improvements:retain(point,value,3)
    final_local=np.asarray(result['audit_position_m'])-origin
    retain(final_local,result['audit_objective_db2'],4)
    local=np.asarray([x[0] for x in raw]);j=np.asarray([x[1] for x in raw]);recorded=np.asarray([x[2] for x in raw])
    dest=ROOT/'targeted_audits'/f'input_{uid:06d}_stage{stage}.npz'
    save_npz(dest,input_id=np.asarray(uid),stage=np.asarray(stage),search_origin_m=origin,
        candidate_local_position_m=local,candidate_position_m=local+origin,
        candidate_objective_db2=j,candidate_recorded_objective_db2=recorded,
        candidate_kind=np.asarray([x[3] for x in raw],np.int8),candidate_start_index=np.asarray([x[4] for x in raw],np.int16),
        candidate_local_status=np.asarray([x[5] for x in raw],np.int16),candidate_local_converged=np.asarray([x[6] for x in raw],bool))
    result.update(input_id=int(uid),stage=stage,candidate_file=dest.name,candidate_file_sha256=sha(dest),
        retained_candidate_count=len(raw),max_candidate_recompute_difference_db2=float(np.max(np.abs(j-recorded))),
        numerical_input_sha256=str(REG['input_sha256'][uid]),audit_lock_sha256=AUDIT_LOCK_SHA)
    write_json(dest.with_suffix('.json'),result)
    return result

def run_input(uid):
    final=ROOT/'targeted_audits'/f'input_{uid:06d}_receipt.json'
    if final.exists():
        rec=json.loads(final.read_text())
        if rec['audit_lock_sha256']!=AUDIT_LOCK_SHA:raise RuntimeError('Changed audit checkpoint lock')
        for name,value in rec['files_sha256'].items():
            if sha(ROOT/'targeted_audits'/name)!=value:raise RuntimeError('Changed audit checkpoint')
        return rec
    began=time.monotonic();first=one_stage(uid,0,30000)
    reasons=[]
    if EXPECTED['status'][uid]!='finite_all_local_runs_converged':reasons.append('primary_local_unconverged')
    threshold=max(1e-4,1e-6*(1+float(EXPECTED['objective_db2'][uid])))
    if first['objective_improvement_db2']>threshold:reasons.append('objective_improvement')
    if first['position_shift_m']>1.:reasons.append('incumbent_shift')
    stages=[first]
    if reasons:stages.append(one_stage(uid,1,100000))
    files={}
    for result in stages:
        p=ROOT/'targeted_audits'/result['candidate_file'];files[p.name]=sha(p);files[p.with_suffix('.json').name]=sha(p.with_suffix('.json'))
    final_result=min(stages,key=lambda r:r['audit_objective_db2'])
    rec={'status':'COMPLETE','input_id':int(uid),'stages':len(stages),'escalation_reasons':reasons,
        'best_stage':int(final_result['stage']),'best_audit_position_m':final_result['audit_position_m'],
        'best_audit_objective_db2':final_result['audit_objective_db2'],
        'best_objective_improvement_db2':max(s['objective_improvement_db2'] for s in stages),
        'max_incumbent_shift_m':max(s['position_shift_m'] for s in stages),
        'last_objective_gap_db2':stages[-1]['objective_gap_db2'],
        'last_objective_gap_met_numerically':stages[-1]['objective_gap_met_numerically'],
        'total_splits':sum(s['splits'] for s in stages),'seconds':time.monotonic()-began,
        'files_sha256':files,'audit_lock_sha256':AUDIT_LOCK_SHA,'primary_outputs_replaced':False}
    write_json(final,rec);return rec

def run(workers):
    check_lock();began=time.monotonic();schedule=json.loads((ROOT/'protocol/TARGETED_AUDIT_SCHEDULE.json').read_text())
    ids=schedule['selected_input_ids'];done=[]
    with cf.ProcessPoolExecutor(max_workers=workers,initializer=initialize) as pool:
        futures=[pool.submit(run_input,uid) for uid in ids]
        for future in cf.as_completed(futures):
            result=future.result();done.append(result)
            progress={'completed':len(done),'scheduled':len(ids),'escalated':sum(r['stages']>1 for r in done),
                'seconds':time.monotonic()-began,'latest_input':result['input_id'],'workers':workers}
            write_json(ROOT/'receipts/TARGETED_AUDIT_PROGRESS.json',progress)
            if len(done)%8==0 or len(done)==len(ids):print(json.dumps(progress),flush=True)
    check_lock()
    rec={'status':'COMPLETE','seconds':time.monotonic()-began,'scheduled':len(ids),'completed':len(done),
        'escalated':sum(r['stages']>1 for r in done),'numerical_gap_met':sum(r['last_objective_gap_met_numerically'] for r in done),
        'max_incumbent_shift_m':max(r['max_incumbent_shift_m'] for r in done),
        'max_objective_improvement_db2':max(r['best_objective_improvement_db2'] for r in done),
        'primary_outputs_replaced':False,'audit_lock_sha256':sha(ROOT/'protocol/TARGETED_AUDIT_LOCK.json'),
        'input_receipts_sha256':{f'input_{r["input_id"]:06d}_receipt.json':sha(ROOT/'targeted_audits'/f'input_{r["input_id"]:06d}_receipt.json') for r in sorted(done,key=lambda r:r['input_id'])}}
    write_json(ROOT/'receipts/TARGETED_AUDIT_RECEIPT.json',rec)
    print(json.dumps({k:v for k,v in rec.items() if k!='input_receipts_sha256'}),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run']);ap.add_argument('--workers',type=int,default=4);a=ap.parse_args()
    prepare() if a.action=='prepare' else run(a.workers)
