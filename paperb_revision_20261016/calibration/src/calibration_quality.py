#!/usr/bin/env python3
"""Outcome-labelled calibration follow-up. Never calls a position estimator.

Stages: protocol (before outcomes), feasibility (counts/geometry only), immediate
(retained fits, held-out query RSS), extension (new fit/validation shrinkage).
All changes are additive. The original inputs, code and predictions stay intact.
"""
from __future__ import annotations
import argparse, csv, datetime, hashlib, io, json, os, platform, zipfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent.parent / 'paperb_execution_20261015'
RAW = ROOT.parent.parent / 'paperb_development_20261015/inputs/lorawan_antwerp_2019_dataset.csv'
CELL_M = 250.
TARGETS = (14, 69)
LAMBDAS = np.array([0., .25, .5, .75, 1.])
TIE_DB = 1e-10

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write_json(p, value):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(p)

def save_npz(p, **arrays):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp')
    with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for k in sorted(arrays):
            a=np.asarray(arrays[k]);assert a.dtype.kind!='O'
            buf=io.BytesIO();np.lib.format.write_array(buf,a,allow_pickle=False)
            info=zipfile.ZipInfo(k+'.npy',(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,buf.getvalue())
    with zipfile.ZipFile(tmp) as z:assert z.testzip() is None
    tmp.replace(p)

def write_csv(p, rows):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def load(p):
    with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in z.files}

def blocks():return sorted((BASE/'inputs/blocks').glob('*.npz'))

def cells(xy):return np.floor(xy/CELL_M).astype(np.int64)

def validation_cells(xy,salt):
    cc=cells(xy)
    unique, inverse=np.unique(cc,axis=0,return_inverse=True)
    flags=np.array([int(hashlib.sha256(f'paperb_calibration_validation_v1:{salt}:{x}:{y}'.encode()).hexdigest(),16)%5==0 for x,y in unique])
    return flags[inverse]

def cal_slices(b):
    for j,g in enumerate(b['cal_receiver_ids']):
        yield int(g),slice(int(b['cal_offsets'][j]),int(b['cal_offsets'][j+1]))

def metric(r):
    r=np.asarray(r);n=len(r)
    if not n:return dict(n=0,bias_db=None,median_signed_db=None,mae_db=None,median_abs_db=None,p95_abs_db=None,rmse_db=None)
    assert np.isfinite(r).all()
    return dict(n=n,bias_db=float(np.mean(r)),median_signed_db=float(np.median(r)),
                mae_db=float(np.mean(np.abs(r))),median_abs_db=float(np.median(np.abs(r))),
                p95_abs_db=float(np.quantile(np.abs(r),.95,method='linear')),rmse_db=float(np.sqrt(np.mean(r*r))))

def protocol():
    assert not (ROOT/'protocol/CALIBRATION_PROTOCOL.json').exists(),'Protocol already written.'
    parent=ROOT.parent.parent/'paperb_adversarial_review_20261016/PAPERB_REVISION_PLAN_20261016.txt'
    spec={
        'status':'SPECIFIED_BEFORE_NEW_CALIBRATION_RESIDUAL_OR_VALIDATION_OUTCOMES',
        'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'chronology':'Secondary diagnostic follow-up after original localization outcomes and numerical audit omission were known; not external preregistration.',
        'parent_plan_sha256':sha(parent),
        'code_sha256':sha(__file__),
        'original_execution_lock_sha256':sha(BASE/'protocol/EXECUTION_LOCK.json'),
        'input_blocks':{str(p.relative_to(BASE)):sha(p) for p in blocks()},
        'input_metadata':{str(p.with_suffix('.json').relative_to(BASE)):sha(p.with_suffix('.json')) for p in blocks()},
        'raw_csv_sha256':sha(RAW),
        'original_residual_assessment':{
            'blocks':'All 18 frozen original blocks, all fields including zero, frozen and unrestricted.',
            'primary':'Selected receptions in each fixed original 500/512-message query cohort.',
            'companion':'All valid [-150,-20] dBm roster receptions on those SAME query source rows; not the full held-out region.',
            'residual':'observed RSSI - [A_i - 47 log10(distance_to_supplied_receiver_m+1)] in dB.',
            'metrics':['count','signed mean bias','median signed residual','MAE','median absolute residual','P95 absolute residual','RMSE'],
            'aggregation':'Receiver-level first; pooled target/unchanged/all groups and separately macro receiver averages. No independent-observation inference.',
            'spatial':'250-m EPSG:32631 cells, origin zero; per-cell target/unchanged/all pooled residual summaries.',
            'baseline':'Same receiver/reception population under own information-state zero-map fit; report metric deltas.',
            'selection_warning':'Selected-reception diagnostics condition on strongest-RSSI selection; all-roster companion assesses that conditioning.',
        },
        'extension':{
            'scope':'Four catalogue spatial folds, original all-data blocks only; unchanged 500-query cohorts, fixed original rosters, targets BS14 and BS69, D=1km/5km, four fields plus zero.',
            'spatial_split':'250-m square EPSG:32631 cells with origin zero. SHA256 UTF8 paperb_calibration_validation_v1:<salt>:<cell_x>:<cell_y>, full integer modulo5=0 to validation; other cells fit.',
            'support_only_salt_search':'Try salt 0..31 in order, choose first simultaneously feasible across all four folds. Retain every tried receiver count. No outcomes inspected to select salt; stop unavailable if no salt feasible.',
            'fit_support':'At least 10 receptions for EVERY original roster receiver. Never drop receivers or borrow validation records.',
            'validation_support':'At least 10 validation receptions for both changed target receivers, for lambda selection. Other receivers below10 remain reported as unsupported for calibration-quality classification; no silent omission.',
            'partition_dependence':'Fit and validation cells disjoint; adjacent cells and campaign records may remain statistically dependent; no independent deployment claim.',
            'zero_baseline':'Recompute zero-map and changed-map median intercepts only from the SAME fit partition. Original all-training intercepts are not reused.',
            'lambda_grid':LAMBDAS.tolist(),
            'shrinkage':'A_i(lambda)=A_i(0)+lambda*(A_i(refit)-A_i(0)). One common lambda per field for both targets; unchanged receiver updates exactly zero.',
            'validation_loss':'Unweighted arithmetic mean of the receiver-specific validation MAEs for BS14 and BS69. Equal receiver weights fixed across fields/lambda; unchanged-receiver losses constant in lambda.',
            'tie':'Choose smallest lambda with loss <= best loss + 1e-10 dB.',
            'known_target_scope':'Changed metadata target IDs are supplied by the intervention; this is not a detector for unknown erroneous receivers.',
            'assessment':'Validation score chooses lambda and is not independent adequacy evidence. Assess RSS on the fixed original query cohort, whose prior use is disclosed. No localization result selects lambda.',
            'quality_classification':'Relative MAE difference >1e-10 dB is degraded, <-1e-10 improved, otherwise numerically unchanged; insufficient receiver support labelled unsupported. No absolute acceptable-fit threshold claimed.',
            'query_localization':'Not executed by this producer. Export endpoint and selected-policy intercepts for root-owned finite-estimator runs.',
        },
        'runtime':{'python':platform.python_version(),'numpy':np.__version__,'cpu_workers':1},
    }
    write_json(ROOT/'protocol/CALIBRATION_PROTOCOL.json',spec)
    print(json.dumps({'protocol_sha256':sha(ROOT/'protocol/CALIBRATION_PROTOCOL.json'),'blocks':len(blocks())}),flush=True)

def verify():
    p=ROOT/'protocol/CALIBRATION_PROTOCOL.json';s=json.loads(p.read_text())
    assert sha(__file__)==s['code_sha256'],'Code changed after protocol.'
    for k,v in {**s['input_blocks'],**s['input_metadata']}.items():assert sha(BASE/k)==v,k
    assert sha(BASE/'protocol/EXECUTION_LOCK.json')==s['original_execution_lock_sha256']
    return s

def feasibility():
    verify();out=[];tried=[];chosen=None
    bb={f:load(BASE/f'inputs/blocks/study2_{f}_all.npz') for f in ['SW','SE','NW','NE']}
    for salt in range(32):
        ok=True;folds=[]
        for fold,b in bb.items():
            vm=validation_cells(b['cal_xy_m_flat'],salt)
            nbadfit=0;nbadtargetval=0
            for g,s in cal_slices(b):
                nv=int(vm[s].sum());nf=int(len(vm[s])-nv)
                fs=nf>=10;vs=nv>=10
                if not fs:nbadfit+=1
                if g in TARGETS and not vs:nbadtargetval+=1
                out.append(dict(salt=salt,fold=fold,receiver_id=g,fit_receptions=nf,validation_receptions=nv,
                                fit_supported=fs,validation_supported=vs,target=g in TARGETS))
            uniq=np.unique(b['cal_source_rows_flat']);
            folds.append(dict(fold=fold,fit_unsupported_receivers=nbadfit,target_validation_unsupported_receivers=nbadtargetval,
                              validation_reception_fraction=float(vm.mean()),training_distinct_source_rows=len(uniq)))
            ok=ok and nbadfit==0 and nbadtargetval==0
        tried.append(dict(salt=salt,feasible=ok,folds=folds))
        if ok:chosen=salt;break
    write_csv(ROOT/'results/SPLIT_SUPPORT_COUNTS.csv',out)
    write_json(ROOT/'receipts/SPLIT_FEASIBILITY.json',dict(status='FEASIBLE' if chosen is not None else 'UNAVAILABLE_NO_FEASIBLE_SALT',chosen_salt=chosen,tried=tried,
               protocol_sha256=sha(ROOT/'protocol/CALIBRATION_PROTOCOL.json'),outcomes_evaluated=False,
               support_counts_sha256=sha(ROOT/'results/SPLIT_SUPPORT_COUNTS.csv')))
    print(json.dumps({'status':'FEASIBLE' if chosen is not None else 'UNAVAILABLE','chosen_salt':chosen,'tried':tried}),flush=True)

def reception_design(b, mode, raw=None):
    if mode=='selected':
        q,j=np.where(b['selected_mask']);rx=b['selected_ids'][q,j];rss=b['query_rssi_dbm'][q,j]
    else:
        a=raw[b['source_rows']];valid=np.isfinite(a)&(a>=-150)&(a<=-20)&b['roster_mask'][None,:]
        q,j=np.where(valid);rx=j+1;rss=a[q,j]
    return dict(query_index=q,receiver_ids=rx,observed_rssi_dbm=rss,reference_xy_m=b['query_xy_m'][q],source_rows=b['source_rows'][q])

def residuals(design,anchors,intercepts):
    j=design['receiver_ids']-1
    d=np.linalg.norm(design['reference_xy_m']-anchors[j],axis=1)
    return design['observed_rssi_dbm']-intercepts[j]+47*np.log10(d+1.)

def blend(a0, ar, lam):
    # Preserve exact endpoint bytes for the downstream finite solver/cache.
    if lam==0.:return a0.copy()
    if lam==1.:return ar.copy()
    return a0+lam*(ar-a0)

def summarize(block,b,design,rr,policies,context,receiver_rows,group_rows,spatial_rows):
    ids=design['receiver_ids'];cc=cells(design['reference_xy_m']);uc=np.unique(cc,axis=0)
    baser=rr[0,0]
    for fi in range(len(b['field_D_m'])):
        target=b['field_target_mask'][fi][ids-1]
        for pi,policy in enumerate(policies):
            r=rr[fi,pi]
            common=dict(block_id=block,assessment=context,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),policy=policy)
            byreceiver=[]
            for g in np.flatnonzero(b['roster_mask'])+1:
                keep=ids==g;m=metric(r[keep]);bm=metric(baser[keep]);role='targeted' if b['field_target_mask'][fi,g-1] else 'unchanged'
                row={**common,'receiver_id':int(g),'role':role,**m,'support_at_least10':m['n']>=10}
                for k in ['bias_db','mae_db','median_abs_db','p95_abs_db','rmse_db']:
                    row['zero_'+k]=bm[k];row['change_'+k]=None if not m['n'] else m[k]-bm[k]
                receiver_rows.append(row);byreceiver.append(row)
            for role,keep in [('targeted',target),('unchanged',~target),('all',np.ones(len(ids),bool))]:
                m=metric(r[keep]);bm=metric(baser[keep]);rs=[x for x in byreceiver if x['n'] and (role=='all' or x['role']==role)]
                row={**common,'role':role,**m,'receivers_with_receptions':len(rs),'receivers_with_at_least10':sum(x['support_at_least10'] for x in rs)}
                for k in ['bias_db','mae_db','median_abs_db','p95_abs_db','rmse_db']:
                    row['macro_receiver_'+k]=float(np.mean([x[k] for x in rs])) if rs else None
                    row['zero_'+k]=bm[k];row['change_'+k]=None if not m['n'] else m[k]-bm[k]
                group_rows.append(row)
                for cx,cy in uc:
                    z=keep&(cc[:,0]==cx)&(cc[:,1]==cy)
                    if z.any():spatial_rows.append({**common,'role':role,'cell_x':int(cx),'cell_y':int(cy),**metric(r[z])})

def immediate():
    spec=verify()
    import pandas as pd
    assert sha(RAW)==spec['raw_csv_sha256']
    raw=pd.read_csv(RAW,usecols=[f'BS {i}' for i in range(1,73)])[[f'BS {i}' for i in range(1,73)]].to_numpy(float)
    rows=[];groups=[];spatial=[];artifacts={}
    for p in blocks():
        b=load(p);F=len(b['field_D_m'])
        for mode in ['selected','all_roster']:
            des=reception_design(b,mode,raw);rr=np.empty((F,2,len(des['receiver_ids'])))
            for fi in range(F):
                for pi,A in enumerate([b['reference_intercepts_dbm'],b['field_refit_intercepts_dbm'][fi]]):rr[fi,pi]=residuals(des,b['field_anchors_m'][fi],A)
            assert np.array_equal(rr[0,0],rr[0,1])
            for fi in range(F):
                un=~b['field_target_mask'][fi][des['receiver_ids']-1]
                assert np.array_equal(rr[fi,0,un],rr[fi,1,un])
                assert np.array_equal(rr[fi,0,un],rr[0,0,un])
            dest=ROOT/'results/original_residual_arrays'/f'{p.stem}__{mode}.npz'
            save_npz(dest,**des,residual_db=rr,field_D_m=b['field_D_m'],field_draw=b['field_draw'],policies=np.array(['frozen','refit']))
            artifacts[str(dest.relative_to(ROOT))]=sha(dest)
            summarize(p.stem,b,des,rr,['frozen','refit'],mode,rows,groups,spatial)
        print(json.dumps({'stage':'immediate','block':p.stem,'completed_receivers':len(rows)}),flush=True)
    for name,data in [('ORIGINAL_RECEIVER_RESIDUALS',rows),('ORIGINAL_GROUP_RESIDUALS',groups),('ORIGINAL_SPATIAL_RESIDUALS',spatial)]:
        p=ROOT/'results'/(name+'.csv');write_csv(p,data);artifacts[str(p.relative_to(ROOT))]=sha(p)
    verify()
    write_json(ROOT/'receipts/ORIGINAL_RESIDUAL_RECEIPT.json',dict(status='COMPLETE',blocks=18,policies=['frozen','refit'],modes=['selected','all_roster'],
               receiver_summary_rows=len(rows),group_summary_rows=len(groups),spatial_summary_rows=len(spatial),outputs=artifacts,
               interpretation='Held-out recorded-label RSS diagnostics, conditional on fixed query cohorts. No claim of absolute calibration adequacy. No query localization rerun.',
               protocol_sha256=sha(ROOT/'protocol/CALIBRATION_PROTOCOL.json')))

def extension():
    verify();feas=json.loads((ROOT/'receipts/SPLIT_FEASIBILITY.json').read_text());salt=feas['chosen_salt']
    if salt is None:raise RuntimeError('No feasible support-only split; extension unavailable.')
    input_index=[];grid=[];valrows=[];quality=[];qrrows=[];qgroups=[];qspatial=[];artifacts={};splitcounts=[]
    for fold in ['SW','SE','NW','NE']:
        source=BASE/f'inputs/blocks/study2_{fold}_all.npz';b=load(source);oldmeta=json.loads(source.with_suffix('.json').read_text())
        vm=validation_cells(b['cal_xy_m_flat'],salt);fm=~vm
        A0=np.full(72,np.nan);Ar=np.full_like(b['field_refit_intercepts_dbm'],np.nan)
        nfit={};nval={}
        for g,s in cal_slices(b):
            fit=fm[s];val=vm[s];nfit[g]=int(fit.sum());nval[g]=int(val.sum());assert nfit[g]>=10
            for fi,anchors in enumerate(b['field_anchors_m']):
                dist=np.linalg.norm(b['cal_xy_m_flat'][s][fit]-anchors[g-1],axis=1)
                Ar[fi,g-1]=np.median(b['cal_rssi_flat'][s][fit]+47*np.log10(dist+1.))
            A0[g-1]=Ar[0,g-1]
        assert all(nval[g]>=10 for g in TARGETS)
        Ac=np.empty_like(Ar);chosen=[]
        flatids=np.concatenate([np.full(s.stop-s.start,g,dtype=np.int16) for g,s in cal_slices(b)])
        vd=dict(receiver_ids=flatids[vm],observed_rssi_dbm=b['cal_rssi_flat'][vm],reference_xy_m=b['cal_xy_m_flat'][vm],source_rows=b['cal_source_rows_flat'][vm])
        vr=np.empty((len(Ar),3,len(vd['receiver_ids'])))
        for fi,anchors in enumerate(b['field_anchors_m']):
            losses=[]
            for lam in LAMBDAS:
                A=blend(A0,Ar[fi],lam);r=residuals(vd,anchors,A)
                components={str(g):float(np.mean(np.abs(r[vd['receiver_ids']==g]))) for g in TARGETS}
                loss=float(np.mean(list(components.values())));losses.append(loss)
                grid.append(dict(fold=fold,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),lambda_value=float(lam),macro_target_mae_db=loss,bs14_mae_db=components['14'],bs69_mae_db=components['69']))
            li=int(np.flatnonzero(np.array(losses)<=min(losses)+TIE_DB)[0]);lam=float(LAMBDAS[li]);chosen.append(lam);Ac[fi]=blend(A0,Ar[fi],lam)
            for pi,A in enumerate([A0,Ar[fi],Ac[fi]]):vr[fi,pi]=residuals(vd,anchors,A)
            for g in b['cal_receiver_ids']:
                k=vd['receiver_ids']==g;fr=metric(vr[fi,0,k]);rr=metric(vr[fi,1,k]);sr=metric(vr[fi,2,k]);supported=nval[int(g)]>=10
                def cls(m):
                    if not supported:return 'unsupported'
                    d=m['mae_db']-fr['mae_db'];return 'degraded' if d>TIE_DB else ('improved' if d<-TIE_DB else 'numerically_unchanged')
                quality.append(dict(fold=fold,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),receiver_id=int(g),target=int(g) in TARGETS,
                                    fit_n=nfit[int(g)],validation_n=nval[int(g)],validation_supported=supported,selected_lambda=lam,
                                    frozen_mae_db=fr['mae_db'],refit_mae_db=rr['mae_db'],selected_mae_db=sr['mae_db'],refit_vs_frozen=cls(rr),selected_vs_frozen=cls(sr)))
                for pi,pol in enumerate(['frozen','refit','selected']):valrows.append(dict(fold=fold,field_index=fi,D_m=float(b['field_D_m'][fi]),draw=int(b['field_draw'][fi]),receiver_id=int(g),policy=pol,validation_supported=supported,**metric(vr[fi,pi,k])))
        assert chosen[0]==0. and np.array_equal(Ac[0,b['roster_mask']],A0[b['roster_mask']])
        for fi in range(len(Ar)):
            unchanged=b['roster_mask']&~b['field_target_mask'][fi]
            assert np.array_equal(Ar[fi,unchanged],A0[unchanged])
            assert np.array_equal(Ac[fi,unchanged],A0[unchanged])
        fitrows=np.unique(b['cal_source_rows_flat'][fm]);valsource=np.unique(b['cal_source_rows_flat'][vm])
        assert not np.intersect1d(fitrows,valsource).size
        assert not np.intersect1d(np.r_[fitrows,valsource],b['source_rows']).size
        new=dict(b);new.update(reference_intercepts_dbm=A0,field_refit_intercepts_dbm=Ar,
                              field_selected_intercepts_dbm=Ac,field_selected_lambda=np.asarray(chosen),
                              cal_offsets=np.r_[0,np.cumsum([nfit[int(g)] for g in b['cal_receiver_ids']])],
                              cal_source_rows_flat=b['cal_source_rows_flat'][fm],cal_rssi_flat=b['cal_rssi_flat'][fm],cal_xy_m_flat=b['cal_xy_m_flat'][fm],
                              cal_unique_source_rows=fitrows,calibration_population_source_rows=fitrows,
                              validation_source_rows=valsource,original_calibration_population_source_rows=b['calibration_population_source_rows'])
        block=f'study2_{fold}_fitval_all';dest=ROOT/'inputs/blocks'/f'{block}.npz';save_npz(dest,**new)
        meta=dict(oldmeta);meta.update(block_id=block,identity={**oldmeta['identity'],'budget':'all_fit_partition','replicate':None},
             source_original_block=str(source.relative_to(BASE)),source_original_block_sha256=sha(source),
             input_npz_sha256=sha(dest),partition_salt=salt,partition_description='250m globally hashed cells, support-only chosen salt; original query cohort/roster unchanged.',
             calibration_cost=dict(fit_distinct_source_rows=len(fitrows),fit_receiver_receptions=int(fm.sum()),validation_distinct_source_rows=len(valsource),validation_receiver_receptions=int(vm.sum())),
             policy_names=['frozen','refit','selected'],selected_lambda=chosen,
             validation_selection='Equal receiver mean MAE over BS14 and BS69, lambda grid0,.25,.5,.75,1; ties<=1e-10 dB favor smallerlambda.',
             validation_unsupported_receivers=[g for g in nval if nval[g]<10],
             field_zero_semantics='Unique fit-partition reference; all three policies coincide exactly.')
        write_json(dest.with_suffix('.json'),meta);input_index.append({'block_id':block,'npz':str(dest.relative_to(ROOT)),'sha256':sha(dest),'metadata_sha256':sha(dest.with_suffix('.json'))})
        vdpath=ROOT/'inputs'/f'{block}_validation.npz';save_npz(vdpath,**vd,validation_residual_db=vr,selected_lambda=np.asarray(chosen))
        artifacts[str(vdpath.relative_to(ROOT))]=sha(vdpath)
        des=reception_design(new,'selected');rr=np.empty((len(Ar),3,len(des['receiver_ids'])))
        for fi,anchors in enumerate(new['field_anchors_m']):
            for pi,A in enumerate([A0,Ar[fi],Ac[fi]]):rr[fi,pi]=residuals(des,anchors,A)
        qpath=ROOT/'results/extension_query_residual_arrays'/f'{block}.npz';save_npz(qpath,**des,residual_db=rr,policies=np.array(['frozen','refit','selected']),field_D_m=new['field_D_m'],field_draw=new['field_draw'])
        artifacts[str(qpath.relative_to(ROOT))]=sha(qpath)
        summarize(block,new,des,rr,['frozen','refit','selected'],'selected_prior_query_cohort',qrrows,qgroups,qspatial)
        splitcounts.append(dict(fold=fold,fit_distinct_source_rows=len(fitrows),validation_distinct_source_rows=len(valsource),fit_receptions=int(fm.sum()),validation_receptions=int(vm.sum()),
                                min_fit_receptions=min(nfit.values()),min_validation_receptions=min(nval.values()),validation_unsupported_receivers=[g for g in nval if nval[g]<10]))
        print(json.dumps({'stage':'extension','fold':fold,'lambda':chosen,'support':splitcounts[-1]}),flush=True)
    for name,data in [('LAMBDA_SELECTION_GRID',grid),('EXTENSION_VALIDATION_RECEIVER_RESIDUALS',valrows),('EXTENSION_VALIDATION_QUALITY',quality),
                      ('EXTENSION_QUERY_RECEIVER_RESIDUALS',qrrows),('EXTENSION_QUERY_GROUP_RESIDUALS',qgroups),('EXTENSION_QUERY_SPATIAL_RESIDUALS',qspatial)]:
        p=ROOT/'results'/(name+'.csv');write_csv(p,data);artifacts[str(p.relative_to(ROOT))]=sha(p)
    write_json(ROOT/'inputs/EXTENSION_INPUT_INDEX.json',input_index)
    verify()
    write_json(ROOT/'receipts/EXTENSION_PREPARATION_RECEIPT.json',dict(status='COMPLETE_INPUTS_PREPARED_NO_QUERY_LOCALIZATION',partition_salt=salt,blocks=input_index,support=splitcounts,
               outputs=artifacts,protocol_sha256=sha(ROOT/'protocol/CALIBRATION_PROTOCOL.json'),
               inference='Relative calibration quality only; no absolute acceptance threshold. Validation chooses lambda; query RSS is separate assessment on a previously examined evaluation cohort.'))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['protocol','feasibility','immediate','extension']);args=ap.parse_args()
    {'protocol':protocol,'feasibility':feasibility,'immediate':immediate,'extension':extension}[args.stage]()
