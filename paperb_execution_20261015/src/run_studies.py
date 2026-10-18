#!/usr/bin/env python3
"""Execute fixed matched designs, preserving every primary output and status.

The lock binds input blocks, this runner, and the numerical algorithm. Exact
input reuse is computational caching only; every scheduled arm retains its own
entry. Primary estimates are never overwritten by stronger numerical audits.
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, hashlib, io, json, os, sys, time, zipfile
from pathlib import Path
import numpy as np
from rss_nlls_production import solve

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');temp.replace(path)

def save_npz(path, **arrays):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(arrays):
            array=np.asarray(arrays[name]);assert array.dtype.kind!='O'
            buf=io.BytesIO();np.lib.format.write_array(buf,array,allow_pickle=False)
            info=zipfile.ZipInfo(name+'.npy',(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,buf.getvalue())
    temp.replace(path)

def verify_lock(lock_path):
    lock=json.loads(Path(lock_path).read_text())
    for name, digest in lock['bound_files'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Lock mismatch: '+name)
    return lock

def run_shard(spec):
    block_path, start, stop, out_dir = spec
    block_path=Path(block_path);out_dir=Path(out_dir)
    name=f'{block_path.stem}__{start:05d}_{stop:05d}'
    dest=out_dir/(name+'.npz');receipt=out_dir/(name+'.json')
    if dest.exists() and receipt.exists():
        prior=json.loads(receipt.read_text())
        if sha(dest)!=prior['output_sha256']:raise ValueError('Changed completed shard')
        if sha(block_path)!=prior['input_sha256']:raise ValueError('Changed shard input')
        if sha(__file__)!=prior['runner_sha256'] or sha(Path(__file__).with_name('rss_nlls_production.py'))!=prior['solver_sha256']:raise ValueError('Changed producing code')
        return prior
    began=time.monotonic()
    with np.load(block_path,allow_pickle=False) as f:b={k:f[k] for k in f.files}
    rows=np.arange(start,stop);ids=b['selected_ids'][rows];mask=b['selected_mask'][rows].astype(bool)
    rss=b['query_rssi_dbm'][rows];lookup=np.maximum(ids-1,0)
    F=len(b['field_D_m']);Q=len(rows);shape=(F,2,Q)
    arrays={
        'nlls_position_m':np.full(shape+(2,),np.nan),
        'nlls_objective_db2':np.full(shape,np.nan),
        'nlls_finite':np.zeros(shape,bool),
        'nlls_local_runs':np.zeros(shape,np.int16),
        'nlls_local_converged':np.zeros(shape,np.int16),
        'nlls_local_failed':np.zeros(shape,np.int16),
        'nlls_local_exhausted':np.zeros(shape,np.int16),
        'nlls_nfev':np.zeros(shape,np.int32),
        'nlls_competitive_count':np.zeros(shape,np.int16),
        'nlls_competitive_diameter_m':np.full(shape,np.nan),
        'nlls_best_start':np.full(shape,-1,np.int16),
        'nlls_status':np.full(shape,'not_executed',dtype='U64'),
        'exact_input_reused':np.zeros(shape,bool),
        'wcl_position_m':np.full(shape+(2,),np.nan),
        'wcl_target_mass':np.zeros(shape),
        'wcl_effective_weight_count':np.zeros(shape),
    }
    cache=[{} for _ in rows];exceptions=[];unique=0
    for fi in range(F):
        coordinates=b['field_anchors_m'][fi]
        target=b['field_target_mask'][fi][lookup] & mask
        axy=np.where(mask[:,:,None],coordinates[lookup],0.)
        for pi in range(2):
            intercept=b['reference_intercepts_dbm'] if pi==0 else b['field_refit_intercepts_dbm'][fi]
            fitted=np.where(mask,intercept[lookup],0.)
            logw=np.where(mask,(np.log(10.)/10.)*(rss-fitted),-np.inf)
            p=np.exp(logw-logw.max(axis=1,keepdims=True));p/=p.sum(axis=1,keepdims=True)
            origin=axy[:,0,:]
            pred=(p[:,:,None]*(axy-origin[:,None,:])).sum(axis=1)+origin
            if not np.isfinite(pred).all() or not np.all(p[mask]>0):raise ValueError('Invalid WCL output')
            arrays['wcl_position_m'][fi,pi]=pred
            arrays['wcl_target_mass'][fi,pi]=np.where(target,p,0.).sum(axis=1)
            arrays['wcl_effective_weight_count'][fi,pi]=1./(p*p).sum(axis=1)
            for qi in range(Q):
                aa=axy[qi,mask[qi]];ss=rss[qi,mask[qi]];fit=fitted[qi,mask[qi]]
                key=(aa.tobytes(),ss.tobytes(),fit.tobytes())
                reused=key in cache[qi]
                if reused:result=cache[qi][key]
                else:
                    try:result=solve(aa,ss,fit)
                    except Exception as exc:
                        result={'finite_output':False,'position_m':[np.nan,np.nan],'objective_db2':np.nan,'status':'exception_'+type(exc).__name__}
                        exceptions.append({'field':fi,'policy':pi,'source_row':int(b['source_rows'][start+qi]),'type':type(exc).__name__,'message':str(exc)})
                    cache[qi][key]=result;unique+=1
                idx=(fi,pi,qi)
                arrays['nlls_position_m'][idx]=result['position_m']
                arrays['nlls_objective_db2'][idx]=result['objective_db2']
                arrays['nlls_finite'][idx]=result['finite_output']
                arrays['nlls_status'][idx]=result['status']
                arrays['exact_input_reused'][idx]=reused
                pairs={'nlls_local_runs':'local_runs','nlls_local_converged':'local_runs_converged',
                       'nlls_local_failed':'local_runs_failed','nlls_local_exhausted':'local_runs_budget_exhausted',
                       'nlls_nfev':'nfev_total','nlls_competitive_count':'competitive_local_solution_count',
                       'nlls_competitive_diameter_m':'competitive_diameter_m','nlls_best_start':'best_start_index'}
                for dst,src in pairs.items():arrays[dst][idx]=result.get(src,np.nan if 'diameter' in dst else (-1 if 'best_start' in dst else 0))
    arrays['source_rows']=b['source_rows'][rows];arrays['query_indices']=rows
    arrays['field_D_m']=b['field_D_m'];arrays['field_draw']=b['field_draw'];arrays['field_target_count']=b['field_target_count']
    save_npz(dest,**arrays)
    rec={'status':'COMPLETE','block':block_path.stem,'start':start,'stop':stop,'queries':Q,'fields':F,
         'scheduled_entries_including_duplicate_zero_arm':int(F*2*Q),
         'unique_nlls_solves':unique,'cached_entries':int(arrays['exact_input_reused'].sum()),
         'finite_entries':int(arrays['nlls_finite'].sum()),'exceptions':exceptions,
         'seconds':time.monotonic()-began,'input_sha256':sha(block_path),'output_sha256':sha(dest),
         'runner_sha256':sha(__file__),'solver_sha256':sha(Path(__file__).with_name('rss_nlls_production.py'))}
    write_json(receipt,rec);return rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=6);ap.add_argument('--chunk',type=int,default=32)
    ap.add_argument('--lock',type=Path,default=ROOT/'protocol/EXECUTION_LOCK.json');args=ap.parse_args()
    began=time.monotonic();lock=verify_lock(args.lock)
    blocks=sorted((ROOT/'inputs/blocks').glob('*.npz'));assert len(blocks)==18
    out_dir=ROOT/'results/shards';out_dir.mkdir(parents=True,exist_ok=True)
    specs=[]
    for path in blocks:
        with np.load(path) as b:q=len(b['source_rows'])
        specs.extend((str(path),start,min(start+args.chunk,q),str(out_dir)) for start in range(0,q,args.chunk))
    results=[]
    with cf.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(run_shard,s):s for s in specs}
        for future in cf.as_completed(futures):
            rec=future.result();results.append(rec)
            print(json.dumps({'done':len(results),'total':len(specs),'block':rec['block'],'rows':[rec['start'],rec['stop']],
                              'unique_solves':rec['unique_nlls_solves'],'seconds':round(time.monotonic()-began,1)}),flush=True)
            write_json(ROOT/'receipts/PRIMARY_PROGRESS.json',{'completed_shards':len(results),'expected_shards':len(specs),
                       'elapsed_seconds':time.monotonic()-began,'last_block':rec['block']})
    verify_lock(args.lock)
    for path in blocks:
        items=[]
        for shard in sorted(out_dir.glob(path.stem+'__*.npz')):
            with np.load(shard,allow_pickle=False) as f:items.append({k:f[k] for k in f.files})
        merged={}
        for key in items[0]:
            axis=0 if key in ['source_rows','query_indices'] else 2
            if key.startswith('field_'):
                assert all(np.array_equal(item[key],items[0][key]) for item in items);merged[key]=items[0][key]
            else:merged[key]=np.concatenate([item[key] for item in items],axis=axis)
        with np.load(path,allow_pickle=False) as b:assert np.array_equal(merged['source_rows'],b['source_rows'])
        save_npz(ROOT/'results/arrays'/path.name,**merged)
    rec={'status':'COMPLETE','seconds':time.monotonic()-began,'blocks':len(blocks),'shards':len(results),
         'unique_nlls_solves':sum(r['unique_nlls_solves'] for r in results),
         'scheduled_entries_including_duplicate_zero_arm':sum(r['scheduled_entries_including_duplicate_zero_arm'] for r in results),
         'exceptions':sum(len(r['exceptions']) for r in results),'lock_sha256':sha(args.lock),
         'output_arrays':{p.name:sha(p) for p in sorted((ROOT/'results/arrays').glob('*.npz'))}}
    write_json(ROOT/'receipts/PRIMARY_RUN_RECEIPT.json',rec);print(json.dumps(rec),flush=True)

if __name__=='__main__':main()
