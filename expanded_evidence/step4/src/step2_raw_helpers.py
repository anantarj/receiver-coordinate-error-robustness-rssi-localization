#!/usr/bin/env python3
"""Raw-input validation of archived Paper B WCL cases and removal scoring.
Reads immutable upstream ZIP and exact CSV. No new field/model is introduced.
Outputs do not redistribute raw RSSI or transmitter-reference coordinates.
Fresh output is required. Repeated fields/messages are not independent samples.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, platform, random, sys, time, zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
import pyproj
ARCHIVE_SHA='01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268'
CSV_SHA='870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446'
ROOT='receiver-coordinate-error-robustness-rssi-localization-v1.1.0/'
EXT=ROOT+'calibration_extension/'
MAPS=('recovered29','official32_minus71')
ATOL=1e-6; WTOL=1e-12; A0TOL=1e-9; RTOL=1e-12
Q=(.5,.9,.95)

def require(ok: bool, msg: str) -> None:
    if not ok: raise ValueError(msg)

def digest(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def json_out(p: Path, v: Any) -> None:
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

def csv_out(p: Path, rows: list[dict]) -> None:
    require(bool(rows),'Empty report '+str(p))
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def close(a: Any,b: Any,msg: str,atol: float=ATOL) -> float:
    a=np.asarray(a);b=np.asarray(b)
    require(a.shape==b.shape,msg+': shape')
    require(np.isfinite(a).all() and np.isfinite(b).all(),msg+': nonfinite')
    d=float(np.max(np.abs(a-b))) if a.size else 0.
    require(d<=atol,f'{msg}: abs discrepancy {d:.17g} exceeds {atol}')
    return d

def eq(a: Any,b: Any,msg: str) -> None: require(np.array_equal(a,b),msg)

def stats(a: Any) -> dict:
    a=np.asarray(a,dtype=float);require(a.size>0 and np.isfinite(a).all(),'Bad stats vector')
    return dict(zip(['min','q25','median','q75','max'],map(float,np.quantile(a,[0,.25,.5,.75,1],method='linear'))))

def npz_out(p: Path, **arrays) -> None:
    with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(arrays):
            a=np.asarray(arrays[name]);require(a.dtype.kind!='O','Object array prohibited')
            b=io.BytesIO();np.lib.format.write_array(b,a,allow_pickle=False)
            zi=zipfile.ZipInfo(name+'.npy',date_time=(1980,1,1,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o600<<16
            z.writestr(zi,b.getvalue())

class Archive:
    def __init__(self,p: Path):
        require(digest(p)==ARCHIVE_SHA,'Wrong upstream ZIP');self.z=zipfile.ZipFile(p);self.consumed={}
        b=self.z.read(EXT+'ARTIFACT_SHA256SUMS.txt')
        self.manifest={line.split(None,1)[1].lstrip('*'):line.split(None,1)[0] for line in b.decode().splitlines() if line.strip()}
        self.consumed[EXT+'ARTIFACT_SHA256SUMS.txt']={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'manifest_match':None}
    def read(self,rel: str) -> bytes:
        b=self.z.read(EXT+rel);h=hashlib.sha256(b).hexdigest();require(rel in self.manifest and h==self.manifest[rel],'Manifest mismatch '+rel)
        self.consumed[EXT+rel]={'sha256':h,'bytes':len(b),'manifest_match':True};return b
    def js(self,rel: str): return json.loads(self.read(rel))
    def npz(self,rel: str):
        with np.load(io.BytesIO(self.read(rel)),allow_pickle=False) as z:return {k:z[k] for k in z.files}
    def rootread(self,rel: str,expected: str):
        b=self.z.read(ROOT+rel);h=hashlib.sha256(b).hexdigest();require(h==expected,'Pinned source '+rel)
        self.consumed[ROOT+rel]={'sha256':h,'bytes':len(b),'pinned_match':True};return b

def fingerprint_step1(p: Path) -> dict:
    entries={}
    for line in (p/'SHA256SUMS.txt').read_text().splitlines():
        if not line.strip():continue
        h,n=line.split(None,1);n=n.lstrip('*');q=p/n
        require(q.is_file() and digest(q)==h,'Step1 integrity '+n);entries[n]=h
    return entries

def load_raw(csv_path: Path) -> dict:
    require(digest(csv_path)==CSV_SHA,'Wrong CSV fingerprint');frame=pd.read_csv(csv_path)
    require(len(frame)==130429,'Raw record count');bs=[f'BS {i}' for i in range(1,73)]
    eq(list(frame.columns[:72]),bs,'Receiver column order')
    rssi=frame[bs].to_numpy(dtype=float);valid=np.isfinite(rssi)&(rssi>=-150)&(rssi<=-20)
    transform=pyproj.Transformer.from_crs('EPSG:4326','EPSG:32631',always_xy=True)
    x,y=transform.transform(frame['Longitude'].to_numpy(float),frame['Latitude'].to_numpy(float));xy=np.column_stack([x,y])
    eligible=np.flatnonzero(valid.sum(axis=1)>=3);require(len(eligible)==55375,'Working population');require(np.isfinite(xy[eligible]).all(),'Nonfinite working positions')
    order=list(map(int,eligible));random.Random(1).shuffle(order)
    return {'rssi':rssi,'valid':valid,'xy':xy,'source_order':order,'columns':list(frame.columns),'active_columns':int(valid.any(axis=0).sum()),'raw_n':len(frame),'working_n':len(eligible)}

def row_key(raw: dict,row: int):
    ids=np.flatnonzero(raw['valid'][row])+1
    rec=tuple(sorted((str(int(g)),round(float(raw['rssi'][row,g-1]),3)) for g in ids))
    return round(float(raw['xy'][row,0]),3),round(float(raw['xy'][row,1]),3),rec

def fit_all(raw: dict,cal: np.ndarray,coords: dict) -> tuple[dict,dict]:
    a0={};counts={}
    for g,xy in coords.items():
        rid=int(g)-1;rows=cal[raw['valid'][cal,rid]];counts[g]=int(len(rows))
        if len(rows)<10:continue
        d=np.linalg.norm(raw['xy'][rows]-np.asarray(xy),axis=1)+1.
        a0[g]=float(np.median(raw['rssi'][rows,rid]+47.*np.log10(d)))
    return a0,counts

def raw_selection(raw: dict,rows: np.ndarray,a0: dict,coords: dict) -> tuple[np.ndarray,np.ndarray]:
    present=raw['valid'][rows].copy();allowed=np.zeros(72,dtype=bool);allowed[[int(g)-1 for g in coords if g in a0]]=True;present &= allowed
    order=np.argsort(np.where(present,-raw['rssi'][rows],np.inf),axis=1,kind='stable')[:,:10]
    ok=np.take_along_axis(present,order,axis=1);ids=np.where(ok,order+1,-1).astype(np.int16)
    values=np.where(ok,np.take_along_axis(raw['rssi'][rows],order,axis=1),0.)
    require(np.all(ok.sum(axis=1)>=3),'Raw selection insufficient');return ids,values

def score(ids: np.ndarray,rx: np.ndarray,coords: dict,a0: dict,truth: np.ndarray):
    ok=ids>=0;xy=np.zeros((*ids.shape,2));av=np.zeros(ids.shape)
    for g,co in coords.items():
        mask=ids==int(g);xy[mask]=co;av[mask]=a0[g]
    w=np.where(ok,np.power(10.,(rx-av)/10.),0.)
    require(np.isfinite(w).all() and np.all(w[ok]>0),'Nonpositive/nonfinite weight')
    sw=w.sum(axis=1);require(np.all(sw>0),'Zero normalization')
    pred=np.sum(w[:,:,None]*xy,axis=1)/sw[:,None];nw=w/sw[:,None];error=np.linalg.norm(pred-truth,axis=1)
    return {'predictions':pred,'weights':nw,'errors':error,'xy':xy}

def populations(touched: np.ndarray,remaining: np.ndarray) -> dict:
    elig=remaining>=3
    return {'full':np.ones(len(touched),bool),'affected':touched,'eligible_min3':elig,'affected_eligible_min3':touched&elig,'ineligible_min3':~elig,'affected_ineligible_min3':touched&~elig}

def proportions(left: np.ndarray,right: np.ndarray) -> dict:
    d=left-right;eps=ATOL+RTOL*np.maximum(np.abs(left),np.abs(right));h=d>eps;j=d < -eps;t=~(h|j)
    return {'right_help_n':int(h.sum()),'right_harm_n':int(j.sum()),'numeric_tie_n':int(t.sum()),'right_help_fraction':float(h.mean()),'right_harm_fraction':float(j.mean()),'median_message_benefit_m':float(np.median(d)),'harm_median_m':float(np.median(-d[j])) if j.any() else 0.,'harm_p95_m':float(np.quantile(-d[j],.95)) if j.any() else 0.,'max_harm_m':float(np.max(-d[j])) if j.any() else 0.}

def analyze(args) -> None:
    start=time.perf_counter();out=args.out;require(not out.exists(),'Refusing existing output '+str(out))
    lock=json.loads(args.lock.read_text());require(lock['status']=='LOCKED_FOR_RAW_VALIDATION_AND_COMPARATOR_SCORING','Wrong lock status')
    require(lock['csv_sha256']==CSV_SHA and lock['upstream_sha256']==ARCHIVE_SHA,'Lock input mismatch')
    step1_entries=fingerprint_step1(args.step1)
    out.mkdir(parents=True);(out/'message_arrays').mkdir();(out/'replay_arrays').mkdir()
    ar=Archive(args.archive);raw=load_raw(args.csv);protocol=ar.js('protocol/PROTOCOL.json');fields=ar.js('protocol/DIRECTION_REGISTER.json')['cases']
    expected=protocol['immutable_inputs']
    for rel,key in [('code/baseline_001_e123_pairfallback_040926.py','harness'),('code/deltamesh_antwerp_eval_v10_fixed_080826.py','evaluator')]:ar.rootread(rel,expected[key]['sha256'])
    cal=np.asarray(ar.js('reproduction_inputs/results/rc5/populations/calibration_ordered_source_rows.json'),dtype=np.int64)
    eq(cal,raw['source_order'][:16612],'Raw calibration ordering');require(len(np.unique(cal))==16612,'Cal IDs nonunique')
    calkeys={row_key(raw,int(i)) for i in cal};configs={};refchecks=[];intercept_rows=[]
    print('Raw input and calibration rows reconstructed',flush=True)
    for name in MAPS:
        ref=ar.npz(f'extension/{name}_reference.npz');meta=ar.js(f'extension/{name}_reference.json')
        coords=ar.js(f'reproduction_inputs/maps/{name}.json');eq(coords,meta['coordinates'],'Map binding')
        rows=np.asarray(ar.js(f'reproduction_inputs/results/rc5/populations/{name}_ordered_source_rows.json'),np.int64)
        eq(rows,ref['source_rows'],'Ref source rows');eq(cal,ref['calibration_source_rows'],'Ref cal rows')
        roster=np.array([int(g)-1 for g in coords]);remainder=np.asarray(raw['source_order'][16612:],np.int64)
        pool=remainder[raw['valid'][remainder][:,roster].sum(axis=1)>=3].tolist()
        sampled=random.Random(9).sample(pool,min(2500,len(pool)))
        removed=[r for r in sampled if row_key(raw,r) in calkeys];selected=[r for r in sampled if row_key(raw,r) not in calkeys]
        eq(rows,selected,'Raw evaluation sampling/dedup '+name);require(len(removed)==2,'Dedup count');require(not set(rows)&set(cal),'Row overlap')
        a0,counts=fit_all(raw,cal,coords);require(set(a0)==set(coords),'Uncalibrated receiver')
        a0diff=close([a0[g] for g in coords],[meta['intercepts'][g] for g in coords],'Baseline intercepts',A0TOL)
        ids,rx=raw_selection(raw,rows,a0,coords);eq(ids,ref['selected_ids'],'Selected order '+name)
        scores=score(ids,rx,coords,a0,raw['xy'][rows])
        pdiff=close(scores['predictions'],ref['predictions'],'Reference prediction '+name)
        wdiff=close(scores['weights'],ref['weights'],'Reference weight '+name,WTOL)
        ediff=close(scores['errors'],ref['errors'],'Reference error '+name)
        directerr=close(np.linalg.norm(ref['predictions']-raw['xy'][rows],axis=1),ref['errors'],'Saved prediction -> CSV error '+name)
        scount={g:int(np.sum(ids==int(g))) for g in coords};eq(scount,meta['selection_counts'],'Selection counts');eq(sorted(scount,key=lambda g:(-scount[g],int(g))),meta['rank_order'],'Ranks')
        for g in sorted(coords,key=int):intercept_rows.append({'case':name+'_reference','map':name,'receiver_id':int(g),'calibration_receptions':counts[g],'recomputed_a0_dbm':a0[g],'saved_a0_dbm':meta['intercepts'][g],'absolute_difference_db':abs(a0[g]-meta['intercepts'][g])})
        configs[name]={'ref':ref,'meta':meta,'coords':coords,'rows':rows,'a0':a0,'ids':ids,'rx':rx,'scores':scores,'truth':raw['xy'][rows]}
        refchecks.append({'map':name,'calibration_n':len(cal),'eligible_heldout_pool_n':len(pool),'sampled_n':len(sampled),'content_duplicates_removed':removed,'evaluation_n':len(rows),'all_source_rows_reconstructed':True,'all_selected_slots_match':True,'baseline_median_m':float(np.median(scores['errors'])),'max_a0_difference_db':a0diff,'max_weight_difference':wdiff,'max_prediction_difference_m':pdiff,'max_error_difference_m':ediff,'max_archived_prediction_csv_error_difference_m':directerr})
        npz_out(out/'replay_arrays'/f'{name}_reference.npz',source_rows=rows,selected_ids=ids,predictions=scores['predictions'],weights=scores['weights'],errors=scores['errors'])
        print('Reference validated',name,refchecks[-1]['baseline_median_m'],flush=True)
    pair_rows=[];replay={};seen=set();maxdiff=defaultdict(float)
    # Complete correspondence checks before reporting any new removal error.
    for f in fields:
        name=f['map'];k=f['k'];r=f['draw'];case=f'{name}_top{k}_r{r:02d}';c=configs[name];require(case not in seen,'Duplicate case');seen.add(case)
        a=ar.npz(f'extension/pairs/{case}.npz');meta=ar.js(f'extension/pairs/{case}.json');eq(meta['field'],f,'Field binding')
        coords={g:list(xy) for g,xy in c['coords'].items()};rng=np.random.default_rng(f['seed'])
        for g in sorted(f['offsets'],key=int):
            theta=float(rng.uniform(0,2*np.pi));off=np.array([5000.*np.cos(theta),5000.*np.sin(theta)])
            close(off,[f['offsets'][g]['dx_m'],f['offsets'][g]['dy_m']],'Seed-offset replay',1e-9);coords[g]=(np.asarray(coords[g])+off).tolist()
        eq(a['map_receiver_ids'],np.array(sorted(map(int,coords))),'Map order');close(a['map_coordinates'],[coords[str(g)] for g in a['map_receiver_ids']],'Pair coordinates',1e-9)
        a0,counts=fit_all(raw,cal,coords)
        adiff=close([a0[g] for g in coords],[meta['refit_a0'][g] for g in coords],'Refit intercepts '+case,A0TOL)
        close([c['a0'][g] for g in coords],[meta['reference_a0'][g] for g in coords],'Baseline pair intercepts',A0TOL)
        for g in coords:
            if g not in f['offsets']:require(a0[g]==c['a0'][g],'Nontarget fit changed')
            intercept_rows.append({'case':case,'map':name,'receiver_id':int(g),'calibration_receptions':counts[g],'recomputed_a0_dbm':a0[g],'saved_a0_dbm':meta['refit_a0'][g],'absolute_difference_db':abs(a0[g]-meta['refit_a0'][g])})
        ids,rx=raw_selection(raw,c['rows'],a0,coords);eq(ids,c['ids'],'Pair selection');eq(rx,c['rx'],'Pair RSSI')
        touched=np.isin(ids,list(map(int,f['offsets']))).any(axis=1);eq(touched,a['touched'],'Touched raw')
        check={'case':case,'map':name,'k':k,'draw':r,'seed':f['seed'],'n':len(c['rows']),'max_a0_difference_db':adiff};checkscores={}
        for arm,intercepts in [('refit',a0),('frozen',c['a0'])]:
            sc=score(ids,rx,coords,intercepts,c['truth']);checkscores[arm]=sc
            for key,tol in [('predictions',ATOL),('weights',WTOL),('errors',ATOL)]:
                d=close(sc[key],a[arm+'_'+key],f'{case} {arm} {key}',tol);check[f'max_{arm}_{key}_difference']=d;maxdiff[f'{arm}_{key}']=max(maxdiff[f'{arm}_{key}'],d)
            d=close(np.linalg.norm(a[arm+'_predictions']-c['truth'],axis=1),a[arm+'_errors'],f'{case} direct CSV {arm} error');check[f'max_saved_{arm}_prediction_csv_error_difference_m']=d
            close(sc['predictions'][~touched],c['scores']['predictions'][~touched],'Untouched predictions')
        close(checkscores['frozen']['weights'],c['scores']['weights'],'Frozen weights',WTOL)
        pair_rows.append(check);replay[case]={'saved':a,'meta':meta,'coords':coords,'a0':a0,'scores':checkscores}
        if len(seen)%32==0:print('Original raw pairs validated',len(seen),'/128',flush=True)
    require(len(seen)==128,'Incomplete pair replay');csv_out(out/'raw_pair_validation.csv',pair_rows);csv_out(out/'intercept_reconstruction.csv',intercept_rows)
    rawreport={'status':'PASS','scope':'Exact CSV -> original rows, vectorized median fits, WCL weights/predictions/errors for 2 references and 128 original pairs; not a full four-pipeline study replay or physical coordinate validation','csv_sha256':CSV_SHA,'csv_bytes':args.csv.stat().st_size,'raw_records':raw['raw_n'],'working_records':raw['working_n'],'active_bs_columns':raw['active_columns'],'projection':'EPSG:4326 longitude first -> EPSG:32631 metres','reference_checks':refchecks,'original_pairs_replayed':128,'original_pair_condition_message_evaluations':128*2*2498,'reference_message_evaluations':2*2498,'max_pair_differences':dict(maxdiff),'intercepts_checked':len(intercept_rows),'zero_based_original_csv_indices':True,'new_field_or_model':False}
    json_out(out/'RAW_VALIDATION.json',rawreport)
    qrows=[];hrows=[];grows=[];remrows=[];field_arrays=defaultdict(list);remcache={};geommax=0.;boundmax=0.
    for name in MAPS:
      c=configs[name]
      for k in (1,2):
        target=np.isin(c['ids'],[14] if k==1 else [14,69]);touched=target.any(axis=1);remaining=(c['ids']>=0).sum(axis=1)-target.sum(axis=1)
        weights=np.where(target,0.,c['scores']['weights']);mass=weights.sum(axis=1);require((mass>0).all(),'Undefined removal')
        removal=np.sum(weights[:,:,None]*c['scores']['xy'],axis=1)/mass[:,None]
        pp=args.step1/'results/saved_analysis/removal_predictions'/f'{name}_top{k}.npz'
        with np.load(pp,allow_pickle=False) as z:
            eq(c['rows'],z['source_rows'],'Step1 removal rows');close(removal,z['predictions'],'Raw vs Step1 removal');eq(remaining,z['selected_clean_count'],'Remaining count');eq(touched,z['touched'],'Affected set')
        err=np.linalg.norm(removal-c['truth'],axis=1);masks=populations(touched,remaining)
        remcache[(name,k)]={'predictions':removal,'errors':err,'masks':masks,'remaining':remaining,'touched':touched,'mass':mass}
        for pop,mask in masks.items():
            require(mask.any(),'Empty planned population')
            row={'map':name,'k':k,'population':pop,'n':int(mask.sum()),'full_n':2498,'affected_n':int(touched.sum()),'full_min3_coverage':float(np.mean(remaining>=3)),'affected_min3_coverage':float(np.mean(remaining[touched]>=3))}
            for label,v in [('reference',c['scores']['errors'][mask]),('removal',err[mask])]:
                for quant,val in zip(Q,np.quantile(v,Q,method='linear')):row[f'{label}_p{int(100*quant)}_m']=float(val)
                row[label+'_mean_m']=float(np.mean(v));row[label+'_max_m']=float(v.max())
            remrows.append(row)
    for f in fields:
        name,k,r=f['map'],f['k'],f['draw'];case=f'{name}_top{k}_r{r:02d}';c=configs[name];rp=replay[case];rem=remcache[(name,k)]
        a=rp['saved'];er=rp['scores']['refit']['errors'];ef=rp['scores']['frozen']['errors'];eu=rem['errors']
        pr=rp['scores']['refit']['predictions'];pf=rp['scores']['frozen']['predictions'];pu=rem['predictions']
        movement=pr-pf;residual=pf-c['truth'];move2=np.sum(movement**2,axis=1);dot2=2*np.sum(residual*movement,axis=1)
        left=er**2-ef**2;right=dot2+move2;residualdiff=np.abs(left-right);scale=np.maximum.reduce([er**2,ef**2,np.abs(dot2),move2,np.ones(len(er))])
        require(np.all(residualdiff<=1e-6+128*np.finfo(float).eps*scale),'Squared-error movement identity '+case);geommax=max(geommax,float(residualdiff.max()))
        dist=np.linalg.norm(pr-pu,axis=1);bound=np.abs(er-eu)-dist;require(np.all(bound<=ATOL),'Removal bound '+case);boundmax=max(boundmax,float(bound.max()))
        mvnorm=np.sqrt(move2);den=mvnorm*np.linalg.norm(residual,axis=1);cosine=np.zeros(len(er));np.divide(np.sum(residual*movement,axis=1),den,out=cosine,where=den>0)
        for pop,mask in rem['masks'].items():
            n=int(mask.sum());rquant=np.quantile(er[mask],Q);fquant=np.quantile(ef[mask],Q);uquant=np.quantile(eu[mask],Q);bquant=np.quantile(c['scores']['errors'][mask],Q)
            for t,qr,qf,qu,qb in zip(Q,rquant,fquant,uquant,bquant):qrows.append({'case':case,'map':name,'k':k,'draw':r,'population':pop,'n':n,'quantile':t,'reference_m':float(qb),'refit_m':float(qr),'frozen_m':float(qf),'removal_m':float(qu),'frozen_minus_refit_m':float(qf-qr),'removal_minus_refit_m':float(qu-qr),'frozen_minus_removal_m':float(qf-qu)})
            for label,lft,rgt in [('frozen_vs_refit',ef,er),('removal_vs_refit',eu,er),('frozen_vs_removal',ef,eu)]:hrows.append({'case':case,'map':name,'k':k,'draw':r,'population':pop,'n':n,'comparison':label,**proportions(lft[mask],rgt[mask])})
            eps=ATOL+RTOL*np.maximum(er,ef);help_mask=(ef-er)>eps;harm_mask=(ef-er)<-eps
            grows.append({'case':case,'map':name,'k':k,'draw':r,'population':pop,'n':n,'move_p50_m':float(np.median(mvnorm[mask])),'move_p95_m':float(np.quantile(mvnorm[mask],.95)),'refit_removal_distance_p50_m':float(np.median(dist[mask])),'refit_removal_distance_p95_m':float(np.quantile(dist[mask],.95)),'help_n':int(help_mask[mask].sum()),'harm_n':int(harm_mask[mask].sum()),'numeric_tie_n':int((~(help_mask|harm_mask))[mask].sum()),'toward_reference_direction_n':int(np.sum((dot2<0)&mask)),'movement_overcompensates_n':int(np.sum((dot2<0)&harm_mask&mask)),'away_direction_harm_n':int(np.sum((dot2>=0)&harm_mask&mask)),'max_squared_identity_residual_m2':float(residualdiff[mask].max())})
        field_arrays[(name,k)].append({'draw':r,'refit_errors':er,'frozen_errors':ef,'dot_term_m2':dot2,'movement_squared_m2':move2,'error_squared_difference_m2':left,'movement_m':mvnorm,'residual_movement_cosine':cosine,'refit_removal_distance_m':dist,'refit_target_mass':a['refit_target_weight_mass']})
    csv_out(out/'removal_error_summaries.csv',remrows);csv_out(out/'paired_comparator_quantiles.csv',qrows);csv_out(out/'comparator_help_harm.csv',hrows);csv_out(out/'geometric_diagnostics_by_field.csv',grows)
    cells={}
    for (name,k),arr in field_arrays.items():
        arr.sort(key=lambda r:r['draw']);rem=remcache[(name,k)];c=configs[name];arrays={q:np.stack([r[q] for r in arr]) for q in arr[0] if q!='draw'}
        arrays.update(draws=np.array([r['draw'] for r in arr]),source_rows=c['rows'],removal_errors=rem['errors'],reference_errors=c['scores']['errors'],touched=rem['touched'],remaining_count=rem['remaining'],eligible_min3=rem['remaining']>=3,untargeted_reference_mass=rem['mass'])
        npz_out(out/'message_arrays'/f'{name}_top{k}.npz',**arrays)
        for arm in ['refit','frozen']:
            npz_out(out/'replay_arrays'/f'{name}_top{k}_{arm}.npz',source_rows=c['rows'],draws=np.arange(32),predictions=np.stack([replay[f'{name}_top{k}_r{r:02d}']['scores'][arm]['predictions'] for r in range(32)]),weights=np.stack([replay[f'{name}_top{k}_r{r:02d}']['scores'][arm]['weights'] for r in range(32)]),errors=arrays[arm+'_errors'])
        cell={'map':name,'k':k,'fields':32,'populations':{}}
        for pop in rem['masks']:
            rows=[row for row in qrows if row['map']==name and row['k']==k and row['population']==pop];p={'n':int(rem['masks'][pop].sum()),'quantiles':{},'help_harm':{}}
            for t in Q:
                v=[r for r in rows if r['quantile']==t]
                p['quantiles'][str(t)]={col:stats([r[col] for r in v]) for col in ['refit_m','frozen_m','removal_m','frozen_minus_refit_m','removal_minus_refit_m','frozen_minus_removal_m']}
                p['quantiles'][str(t)]['fields_refit_better_than_removal']=sum(r['removal_minus_refit_m']>ATOL for r in v);p['quantiles'][str(t)]['fields_removal_better_than_refit']=sum(r['removal_minus_refit_m'] < -ATOL for r in v)
            for label in ['frozen_vs_refit','removal_vs_refit','frozen_vs_removal']:
                h=[r for r in hrows if r['map']==name and r['k']==k and r['population']==pop and r['comparison']==label]
                p['help_harm'][label]={col:stats([r[col] for r in h]) for col in ['right_help_fraction','right_harm_fraction','median_message_benefit_m','harm_median_m','harm_p95_m','max_harm_m']}
            cell['populations'][pop]=p
        cells[f'{name}_top{k}']=cell
    json_out(out/'CELL_SUMMARIES.json',cells)
    focus=[];targets=[('recovered29',1,21,15145),('official32_minus71',2,25,None)]+[('official32_minus71',1,r,None) for r in (4,5,9,14)]
    for name,k,r,rowid in targets:
        case=f'{name}_top{k}_r{r:02d}';c=configs[name];rem=remcache[(name,k)];a=replay[case]['scores']
        entry={'case':case,'selection_status':'identified in Step1 or historical adverse register before Step2 scoring','full_quantiles':[v for v in qrows if v['case']==case and v['population']=='full'],'affected_quantiles':[v for v in qrows if v['case']==case and v['population']=='affected'],'affected_geometric_diagnostics':next(v for v in grows if v['case']==case and v['population']=='affected')}
        if rowid is not None:
            indices=np.flatnonzero(c['rows']==rowid);require(len(indices)==1,'Focused row absent');j=int(indices[0]);p=a['refit']['predictions'][j]
            entry['message']={'source_row':rowid,'selected_receiver_ids':c['ids'][j][c['ids'][j]>=0].tolist(),'remaining_selected_count':int(rem['remaining'][j]),'operational_min3_eligible':bool(rem['remaining'][j]>=3),'reference_error_m':float(c['scores']['errors'][j]),'refit_error_m':float(a['refit']['errors'][j]),'frozen_error_m':float(a['frozen']['errors'][j]),'removal_error_m':float(rem['errors'][j]),'refit_to_removal_distance_m':float(np.linalg.norm(p-rem['predictions'][j])),'untargeted_reference_weight':float(rem['mass'][j]),'refitted_target_weight':float(replay[case]['saved']['refit_target_weight_mass'][j])}
        focus.append(entry)
    json_out(out/'PREIDENTIFIED_CASE_DIAGNOSTICS.json',focus)
    json_out(out/'GEOMETRIC_VERIFICATION.json',{'status':'PASS','comparisons':128*2498,'max_squared_error_identity_residual_m2':geommax,'maximum_reverse_triangle_excess_m':boundmax,'physical_reference_status':'Released CSV positions, not independently surveyed truth','source_coordinates_inferred_from_errors':False,'raw_rssi_and_reference_coordinates_redistributed':False})
    json_out(out/'CONSUMED_INPUTS.json',{'external_csv':{'sha256':CSV_SHA,'bytes':args.csv.stat().st_size},'archive_sha256':ARCHIVE_SHA,'consumed_archive_members':ar.consumed,'validated_step1_member_hashes':step1_entries,'lock_sha256':digest(args.lock)})
    receipt={'status':'PASS','elapsed_seconds':time.perf_counter()-start,'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,'pyproj':pyproj.__version__,'proj':pyproj.proj_version_str,'platform':platform.platform(),'driver_sha256':digest(Path(__file__)),'lock_sha256':digest(args.lock),'pair_quantile_rows':len(qrows),'comparator_help_harm_rows':len(hrows),'geometric_rows':len(grows),'removal_score_population_rows':len(remrows),'original_replay_pairs':len(pair_rows),'new_model_runs':0,'new_displacement_fields':0}
    json_out(out/'RUN_RECEIPT.json',receipt);print(json.dumps(receipt,indent=2),flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for flag in ['archive','csv','step1','lock','out']:ap.add_argument('--'+flag,type=Path,required=True)
    args=ap.parse_args()
    try:analyze(args)
    except Exception as ex:
        if args.out.exists():json_out(args.out/'FAILURE.json',{'status':'STOPPED','exception_type':type(ex).__name__,'message':str(ex)})
        raise
if __name__=='__main__':main()
