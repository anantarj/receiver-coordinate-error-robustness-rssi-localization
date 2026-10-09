#!/usr/bin/env python3
"""Validate immutable Paper B v1.1.0 pairs and derive reliability/removal diagnostics.

Reads the published ZIP directly. Does not refit, generate perturbations, infer
omitted transmitter coordinates, or alter an input. A fresh output directory is
required. Error values are checked against their saved summaries, not raw truth.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import platform
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ARCHIVE_SHA = '01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268'
ATOL = 1e-6
RTOL = 1e-12
WTOL = 1e-12
MAPS = ('recovered29', 'official32_minus71')


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def close(a: Any, b: Any, msg: str, atol: float = ATOL) -> float:
    av, bv = np.asarray(a), np.asarray(b)
    require(av.shape == bv.shape, msg + ': shape mismatch')
    require(bool(np.all(np.isfinite(av)) and np.all(np.isfinite(bv))), msg + ': nonfinite')
    diff = float(np.max(np.abs(av-bv))) if av.size else 0.0
    require(diff <= atol, f'{msg}: max absolute discrepancy {diff:.16g} > {atol}')
    return diff


def equal(a: Any, b: Any, msg: str) -> None:
    require(bool(np.array_equal(a, b)), msg)


def write_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_csv(p: Path, rows: list[dict]) -> None:
    require(bool(rows), f'Empty CSV: {p}')
    with p.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def stats(x: Any) -> dict:
    v=np.asarray(x, dtype=np.float64)
    require(bool(v.size and np.isfinite(v).all()), 'Invalid summary vector')
    q=np.quantile(v, [0, .25, .5, .75, 1], method='linear')
    return dict(zip(('min','q25','median','q75','max'), map(float,q)))


def help_harm(frozen: np.ndarray, refit: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    eps=ATOL+RTOL*np.maximum(np.abs(frozen), np.abs(refit))
    d=frozen-refit
    return d>eps, d < -eps, np.abs(d)<=eps


def removal(weights: np.ndarray, selected_coords: np.ndarray, target: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    """Fixed selection; target weights zero; no receiver refill or fallback."""
    wu=np.where(target, 0.0, weights)
    mass=wu.sum(axis=1)
    ok=mass>0
    out=np.full((weights.shape[0],2),np.nan)
    out[ok]=np.einsum('qi,qij->qj',wu[ok],selected_coords[ok])/mass[ok,None]
    return out,ok


class Archive:
    def __init__(self,path: Path):
        require(sha_file(path)==ARCHIVE_SHA,'Wrong upstream archive fingerprint')
        self.z=zipfile.ZipFile(path)
        self.prefix='receiver-coordinate-error-robustness-rssi-localization-v1.1.0/calibration_extension/'
        self.consumed={}
        raw=self.z.read(self.prefix+'ARTIFACT_SHA256SUMS.txt')
        self.manifest={line.split(None,1)[1].lstrip('*'):line.split(None,1)[0]
                       for line in raw.decode().splitlines() if line.strip()}
        self.consumed['ARTIFACT_SHA256SUMS.txt']={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'manifest_match':None}
    def read(self,rel: str) -> bytes:
        b=self.z.read(self.prefix+rel); h=hashlib.sha256(b).hexdigest()
        require(rel in self.manifest, 'Unmanifested extension input: '+rel)
        require(h==self.manifest[rel], 'Input member hash: '+rel)
        self.consumed[rel]={'sha256':h,'bytes':len(b),'manifest_match':True}
        return b
    def js(self,rel: str): return json.loads(self.read(rel))
    def npz(self,rel: str):
        with np.load(io.BytesIO(self.read(rel)),allow_pickle=False) as z:
            return {k:z[k] for k in z.files}
    def csv(self,rel: str): return list(csv.DictReader(io.StringIO(self.read(rel).decode())))


def selected_xy(ids: np.ndarray, coords: dict) -> np.ndarray:
    out=np.zeros((*ids.shape,2))
    for g,xy in coords.items(): out[ids==int(g)]=xy
    return out


def main(archive_path: Path,out: Path,lock_path: Path) -> None:
    require(not out.exists(), 'Refusing to overwrite existing output: '+str(out))
    lock=json.loads(lock_path.read_text())
    require(lock['status']=='LOCKED_FOR_SAVED_OUTPUT_ANALYSIS','Missing saved-analysis lock')
    out.mkdir(parents=True);(out/'message_arrays').mkdir();(out/'removal_predictions').mkdir()
    ar=Archive(archive_path)
    schedule=ar.js('protocol/DIRECTION_REGISTER.json')['cases']
    expected={(v['map'],v['k'],v['draw']):v for v in schedule}
    require(len(expected)==128,'Bad schedule')
    rows=ar.csv('extension/paired_results.csv')
    # The summarizer rewrites float strings; compare identities exactly and
    # numeric cells at the already declared calculation tolerances.
    rewritten=ar.csv('results/paired_results.csv')
    require(len(rewritten)==len(rows), 'Saved pair-register lengths differ')
    csv_roundtrip_max=0.0
    for left,right in zip(rows,rewritten):
        require(left.keys()==right.keys(),'Saved pair-register columns differ')
        for col,value in left.items():
            if col in ('case','map','historical_bridge','all_untouched_predictions_exact','array_sha256'):
                require(value==right[col], 'Saved register identity mismatch: '+col)
            else:
                dd=close(float(value),float(right[col]),'Saved register numeric cell: '+col,
                         WTOL if 'weight' in col else 1e-9)
                csv_roundtrip_max=max(csv_roundtrip_max,dd)
    require(len(rows)==128,'Pair count')
    old_cells=ar.csv('results/cell_summary.csv')
    old_protocol=ar.js('protocol/PROTOCOL.json')
    run_status=ar.js('extension/RUN_STATUS.json')
    require(run_status['status']=='COMPLETE' and run_status['complete_pairs']==128,'Upstream incomplete')
    refs={}; reference_checks=[]
    for name in MAPS:
        ref=ar.npz(f'extension/{name}_reference.npz');meta=ar.js(f'extension/{name}_reference.json')
        require('truth' not in ref and 'raw_rssi' not in ref,'Unexpected restricted source slice')
        ids=ref['selected_ids']; valid=ids>=0
        require(ids.shape==(2498,10) and np.issubdtype(ids.dtype,np.integer),'Reference IDs')
        require(np.all((ids>=0)|(ids==-1)),'Invalid padding ID')
        require(np.all(valid.sum(axis=1)>=3),'Thin reference selection')
        equal(valid,np.arange(10)[None,:]<valid.sum(axis=1)[:,None],'Non-contiguous valid slots')
        require(all(len(set(row[row>=0]))==sum(row>=0) for row in ids),'Duplicate selected receiver')
        require(set(map(str,np.unique(ids[valid])))<=set(meta['coordinates']),'Unknown selected receiver')
        require(len(np.unique(ref['source_rows']))==2498,'Duplicate source-row identities')
        require(not set(ref['source_rows'])&set(ref['calibration_source_rows']),'Calibration row overlap')
        rowfile=f'reproduction_inputs/results/rc5/populations/{name}_ordered_source_rows.json'
        equal(ref['source_rows'],ar.js(rowfile),'Ordered evaluation rows')
        require(ar.consumed[rowfile]['sha256']==meta['source_row_sha256'],'Source-row JSON hash')
        equal(ref['calibration_source_rows'],ar.js('reproduction_inputs/results/rc5/populations/calibration_ordered_source_rows.json'),'Calibration rows')
        equal(ar.js(f'reproduction_inputs/maps/{name}.json'),meta['coordinates'],'Reference map JSON')
        w=ref['weights'];require(np.isfinite(w).all() and np.all(w[valid]>0),'Invalid positive weights')
        equal(w[~valid],np.zeros((~valid).sum()),'Nonzero padded weights')
        close(w.sum(axis=1),np.ones(2498),'Reference sum',WTOL)
        coords=selected_xy(ids,meta['coordinates'])
        pdiff=close(ref['predictions'],np.einsum('qi,qij->qj',w,coords),'Reference prediction reconstruction')
        require(np.isfinite(ref['errors']).all() and np.all(ref['errors']>=0),'Reference errors')
        close(np.median(ref['errors']),meta['baseline_median_m'],'Reference error median',1e-9)
        counts={g:int(np.sum(ids==int(g))) for g in meta['coordinates']}
        equal(counts,meta['selection_counts'],'Selection counts')
        equal(sorted(counts,key=lambda g:(-counts[g],int(g))),meta['rank_order'],'Receiver rank')
        refs[name]=(ref,meta,coords)
        reference_checks.append({'map':name,'messages':2498,'calibration_rows':len(ref['calibration_source_rows']),
                                 'median_m':float(np.median(ref['errors'])),'max_prediction_abs_difference_m':pdiff,
                                 'source_row_order_matches':True,'selected_slots_and_padding_valid':True})
    quantile_rows=[];help_rows=[];distance_rows=[];support_rows=[];validation_rows=[]
    state=defaultdict(list); removals={};seen=set();bridge_count=0
    for row in rows:
        name,k,draw=row['map'],int(row['k']),int(row['draw']);case=row['case'];key=(name,k,draw)
        require(key in expected and key not in seen,'Unknown/duplicate pair');seen.add(key)
        f=expected[key];meta=ar.js(f'extension/pairs/{case}.json');a=ar.npz(f'extension/pairs/{case}.npz')
        equal(meta['field'],f,'Field metadata'); require(int(row['seed'])==f['seed']==8800+k+101*draw,'Seed mismatch')
        h=ar.consumed[f'extension/pairs/{case}.npz']['sha256']
        require(h==row['array_sha256']==meta['array_sha256'],'NPZ cross-binding')
        ref,rm,refxy=refs[name];ids=ref['selected_ids'];valid=ids>=0
        target=np.isin(ids,[int(g) for g in f['offsets']]);touched=target.any(axis=1)
        clean=valid.sum(axis=1)-target.sum(axis=1)
        require(set(f['offsets'])==set(rm['rank_order'][:k]),'Target rank membership')
        equal(touched,a['touched'],'Affected mask');equal(clean,a['selected_clean_count'],'Clean counts')
        require(int(touched.sum())==int(row['touched_n']),'Affected count')
        require(np.min(clean)>=1,'No clean support: removal cannot be globally defined')
        equal(meta['reference_a0'],rm['intercepts'],'Frozen intercept bindings')
        require(set(meta['refit_a0'])==set(rm['intercepts']),'Refit intercept roster')
        mp={str(int(g)):xy for g,xy in zip(a['map_receiver_ids'],a['map_coordinates'])}
        require(set(mp)==set(rm['coordinates']),'Map IDs')
        multiplier=np.ones(ids.shape)
        for g,coord in mp.items():
            want=np.asarray(rm['coordinates'][g])
            if g in f['offsets']:
                off=f['offsets'][g];want=want+np.array([off['dx_m'],off['dy_m']])
                close(np.linalg.norm([off['dx_m'],off['dy_m']]),5000.,'Field magnitude')
            else: require(meta['refit_a0'][g]==meta['reference_a0'][g],'Non-target intercept changed')
            equal(coord,want,'Only target coordinates change')
            multiplier[ids==int(g)]=10.**(-(meta['refit_a0'][g]-meta['reference_a0'][g])/10.)
        coords=selected_xy(ids,mp)
        equal(a['frozen_weights'],ref['weights'],'Frozen weights differ')
        alt=ref['weights']*multiplier;alt/=alt.sum(axis=1,keepdims=True)
        wd=close(alt,a['refit_weights'],'Reweight identity',WTOL)
        maxpred=0.
        for arm in ('refit','frozen'):
            w,p,e=a[arm+'_weights'],a[arm+'_predictions'],a[arm+'_errors']
            require(w.shape==(2498,10) and p.shape==(2498,2) and e.shape==(2498,),'Pair shapes')
            require(np.isfinite(w).all() and np.isfinite(e).all() and np.all(w[valid]>0) and np.all(e>=0),'Pair finite/positive')
            equal(w[~valid],np.zeros((~valid).sum()),'Padded weights')
            close(w.sum(axis=1),np.ones(2498),'Weight sum',WTOL)
            maxpred=max(maxpred,close(p,np.einsum('qi,qij->qj',w,coords),'Pair prediction identity'))
            close((w*target).sum(axis=1),a[arm+'_target_weight_mass'],'Target mass',WTOL)
            close(np.median(e),float(row[arm+'_m']),'Field error median',1e-9)
            close(np.median(e[touched]),float(row['touched_'+arm+'_m']),'Affected error median',1e-9)
            close(100*(np.median(e)/rm['baseline_median_m']-1),float(row[arm+'_pct']),'Field percentage',1e-9)
            equal(p[~touched],ref['predictions'][~touched],'Untouched predictions')
            equal(e[~touched],ref['errors'][~touched],'Untouched errors')
        close(np.median(a['frozen_errors'])-np.median(a['refit_errors']),float(row['delta_m']),'Field contrast',1e-9)
        if f['historical_R29_bridge']:
            b=ar.npz(f'bridge/pairs/{case}.npz')
            for keyb,val in b.items(): equal(val,a[keyb],'Historical computed bridge '+keyb)
            bridge_count+=1
        u,ok=removal(ref['weights'],refxy,target)
        require(bool(ok.all()),'Undefined removal unexpectedly')
        u_refit,ok_refit=removal(a['refit_weights'],coords,target)
        require(bool(ok_refit.all()),'Undefined refit nontarget centroid')
        nd=close(u,u_refit,'Non-target relative weights and centroid unchanged')
        if (name,k) in removals: equal(u,removals[(name,k)],'Removal changed with direction')
        else:
            removals[name,k]=u.copy()
            np.savez_compressed(out/'removal_predictions'/f'{name}_top{k}.npz',predictions=u,
                 source_rows=ref['source_rows'],selected_clean_count=clean,touched=touched,
                 original_min3_eligible=clean>=3)
        target_mass=a['refit_target_weight_mass']
        rhs=np.einsum('qi,qij->qj',a['refit_weights']*target,coords-u[:,None,:])
        dd=a['refit_predictions']-u
        identity_diff=close(dd,rhs,'Finite removal identity')
        dist=np.linalg.norm(dd,axis=1)
        # Triangle inequality available without any inversion of omitted truth.
        error_gap=np.abs(a['frozen_errors']-a['refit_errors'])
        move=np.linalg.norm(a['frozen_predictions']-a['refit_predictions'],axis=1)
        require(np.all(error_gap<=move+ATOL),'Stored errors violate necessary reverse-triangle inequality')
        base={'case':case,'map':name,'k':k,'draw':draw,'seed':f['seed']}
        for pop,mask in [('all',np.ones(2498,bool)),('affected',touched)]:
            er,ef=a['refit_errors'][mask],a['frozen_errors'][mask];eb=ref['errors'][mask]
            helped,harmed,ties=help_harm(ef,er); d=ef-er
            harmvals=-d[harmed]
            hh={**base,'population':pop,'n':len(er),'helped_n':int(helped.sum()),'harmed_n':int(harmed.sum()),'tie_n':int(ties.sum()),
                'helped_pct':100*float(helped.mean()),'harmed_pct':100*float(harmed.mean()),'tie_pct':100*float(ties.mean()),
                'message_benefit_min_m':float(d.min()),'message_benefit_q05_m':float(np.quantile(d,.05)),
                'message_benefit_q50_m':float(np.median(d)),'message_benefit_q95_m':float(np.quantile(d,.95)),
                'message_benefit_max_m':float(d.max()),'harm_among_harmed_p50_m':float(np.median(harmvals)) if len(harmvals) else 0.,
                'harm_among_harmed_p95_m':float(np.quantile(harmvals,.95)) if len(harmvals) else 0.,
                'harm_max_m':float(harmvals.max()) if len(harmvals) else 0.}
            help_rows.append(hh)
            for t in (.5,.9,.95):
                qr,qf,qb=map(float,(np.quantile(er,t,method='linear'),np.quantile(ef,t,method='linear'),np.quantile(eb,t,method='linear')))
                quantile_rows.append({**base,'population':pop,'n':len(er),'quantile':t,'reference_m':qb,'refit_m':qr,'frozen_m':qf,
                    'paired_benefit_m':qf-qr,'refit_minus_reference_m':qr-qb,'frozen_minus_reference_m':qf-qb})
            dv=dist[mask]
            distance_rows.append({**base,'population':pop,'n':int(mask.sum()),'p50_m':float(np.median(dv)),
               'p90_m':float(np.quantile(dv,.9)),'p95_m':float(np.quantile(dv,.95)),'max_m':float(dv.max()),
               'non_target_only_defined_n':int(ok[mask].sum()),'original_min3_eligible_n':int((clean[mask]>=3).sum()),
               'original_min3_coverage_pct':100*float((clean[mask]>=3).mean())})
        for nclean in sorted(np.unique(clean[touched])):
            mask=touched&(clean==nclean);ef=a['frozen_errors'][mask];er=a['refit_errors'][mask]
            hp,hm,tt=help_harm(ef,er)
            support_rows.append({**base,'remaining_uncorrupted_selected':int(nclean),'n':int(mask.sum()),
                'helped_pct':100*float(hp.mean()),'harmed_pct':100*float(hm.mean()),'median_message_benefit_m':float(np.median(ef-er)),
                'difference_of_arm_medians_m':float(np.median(ef)-np.median(er)),
                'refit_remove_distance_p95_m':float(np.quantile(dist[mask],.95)),
                'target_weight_mass_p95':float(np.quantile(target_mass[mask],.95))})
        validation_rows.append({**base,'status':'PASS','affected_n':int(touched.sum()),'min_clean_selected':int(clean.min()),
            'pair_npz_sha256':h,'max_prediction_abs_difference_m':maxpred,'max_weight_identity_difference':wd,
            'max_nontarget_centroid_difference_m':nd,'max_removal_identity_difference_m':identity_diff,
            'max_refit_remove_distance_m':float(dist.max())})
        state[name,k].append({'draw':draw,'refit_errors':a['refit_errors'],'frozen_errors':a['frozen_errors'],
             'message_benefit_m':a['frozen_errors']-a['refit_errors'],
             'refit_benefit_vs_reference_m':ref['errors']-a['refit_errors'],
             'removal_prediction_distance_m':dist,'refit_target_weight_mass':target_mass,
             'touched':touched,'clean':clean,'source_rows':ref['source_rows']})
    require(seen==set(expected),'Incomplete execution set')
    oldcheck=[]
    for oc in old_cells:
        name,k=oc['map'],int(oc['k']);items=sorted(state[name,k],key=lambda v:v['draw'])
        require(len(items)==32,'Cell count')
        er=np.stack([v['refit_errors'] for v in items]);ef=np.stack([v['frozen_errors'] for v in items])
        delta=np.median(ef,axis=1)-np.median(er,axis=1)
        for field,fval in [('paired_delta_m_median',np.median(delta)),('paired_delta_m_q25',np.quantile(delta,.25)),
                          ('paired_delta_m_q75',np.quantile(delta,.75)),('paired_delta_m_min',delta.min()),('paired_delta_m_max',delta.max())]:
            close(fval,float(oc[field]),'Cell '+field,1e-9)
        adverse=np.where(delta<0)[0].tolist()
        require(adverse==([4,5,9,14] if name=='official32_minus71' and k==1 else []),'Adverse fields')
        for label,e in [('refit',er),('frozen',ef)]:
            close(np.median(100*(np.median(e,axis=1)/refs[name][1]['baseline_median_m']-1)),float(oc[label+'_pct_median']),'Cell pct',1e-9)
        oldcheck.append({'map':name,'k':k,'median_benefit_m':float(np.median(delta)),'adverse_draws':adverse,'status':'PASS'})
        np.savez_compressed(out/'message_arrays'/f'{name}_top{k}.npz',
            field_draw=np.arange(32),source_rows=items[0]['source_rows'],touched=items[0]['touched'],
            remaining_uncorrupted_selected=items[0]['clean'],
            **{key:np.stack([v[key] for v in items]) for key in ['refit_errors','frozen_errors','message_benefit_m',
                         'refit_benefit_vs_reference_m','removal_prediction_distance_m','refit_target_weight_mass']})
    cellout=[]
    for name in MAPS:
        for k in (1,2):
            for pop in ('all','affected'):
                qrows=[v for v in quantile_rows if v['map']==name and v['k']==k and v['population']==pop]
                hs=[v for v in help_rows if v['map']==name and v['k']==k and v['population']==pop]
                ds=[v for v in distance_rows if v['map']==name and v['k']==k and v['population']==pop]
                qdict={}
                for t in (.5,.9,.95):
                    qs=[v for v in qrows if v['quantile']==t]
                    benefit=np.array([v['paired_benefit_m'] for v in qs])
                    qdict[str(t)]={key:stats([v[key] for v in qs]) for key in ['reference_m','refit_m','frozen_m','paired_benefit_m','refit_minus_reference_m']}
                    qdict[str(t)]['beneficial_fields']=int((benefit>ATOL).sum());qdict[str(t)]['harmful_fields']=int((benefit < -ATOL).sum())
                bydraw=defaultdict(dict)
                for v in qrows: bydraw[v['draw']][v['quantile']]=v['paired_benefit_m']
                discord={str(t):[int(d) for d,q in bydraw.items() if q[.5]>ATOL and q[t]<-ATOL] for t in (.9,.95)}
                c={'map':name,'k':k,'population':pop,'messages':hs[0]['n'],'fields':32,'quantiles':qdict,
                    'helped_pct':stats([v['helped_pct'] for v in hs]),'harmed_pct':stats([v['harmed_pct'] for v in hs]),
                    'tie_pct':stats([v['tie_pct'] for v in hs]),'harm_max_m':stats([v['harm_max_m'] for v in hs]),
                    'harm_among_harmed_p95_m':stats([v['harm_among_harmed_p95_m'] for v in hs]),
                    'removal_distance':{key:stats([v[key] for v in ds]) for key in ['p50_m','p90_m','p95_m','max_m']},
                    'min3_coverage_pct':ds[0]['original_min3_coverage_pct'],'median_favors_refit_but_tail_harms_draws':discord}
                cellout.append(c)
    for filename,v in [('paired_quantiles_by_field.csv',quantile_rows),('help_harm_by_field.csv',help_rows),
                       ('removal_prediction_by_field.csv',distance_rows),('support_strata_by_field.csv',support_rows),('pair_validation.csv',validation_rows)]:
        write_csv(out/filename,v)
    validation={'status':'PASS','archive_sha256':ARCHIVE_SHA,'pair_count':len(seen),'reference_count':2,'computed_historical_bridge_matches':bridge_count,
        'reference_checks':reference_checks,'historical_cell_checks':oldcheck,'member_files_hashed':len(ar.consumed),
        'max_prediction_abs_difference_m':max(v['max_prediction_abs_difference_m'] for v in validation_rows),
        'max_weight_identity_difference':max(v['max_weight_identity_difference'] for v in validation_rows),
        'max_removal_identity_difference_m':max(v['max_removal_identity_difference_m'] for v in validation_rows),
        'max_duplicate_csv_roundtrip_difference':csv_roundtrip_max,
        'source_csv_supplied':False,'fits_reexecuted':False,'stored_errors_checked_against_original_transmitter_references':False,
        'scope':'Immutable member integrity, stored identity/summary consistency, reweighting and prediction identities; no raw-observation or transmitter-reference reconstruction and no fitting.'}
    write_json(out/'VALIDATION.json',validation)
    write_json(out/'CELL_SUMMARIES.json',cellout)
    write_json(out/'CONSUMED_INPUTS.json',{'archive_sha256':ARCHIVE_SHA,'prefix':ar.prefix,'members':ar.consumed})
    write_json(out/'RUN_RECEIPT.json',{'analysis_id':lock['analysis_id'],'status':'COMPLETE','lock_sha256':sha_file(lock_path),
       'script_sha256':sha_file(Path(__file__)),'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),
       'pairs':128,'condition_message_evaluations':128*2498*2,'paired_message_field_comparisons':128*2498,
       'denominator_warning':'Repeated messages and maps/fields are not independent statistical samples.',
       'new_metrics':True,'new_fits_or_coordinate_perturbations':False,'exact_removal_error_scoring':False})
    print(json.dumps(validation,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--lock',type=Path,required=True)
    args=ap.parse_args()
    try: main(args.archive.resolve(),args.out.resolve(),args.lock.resolve())
    except Exception as exc:
        if args.out.exists(): write_json(args.out/'FAILURE.json',{'status':'FAILED','error':repr(exc)})
        raise
