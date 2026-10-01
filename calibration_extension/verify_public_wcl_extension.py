#!/usr/bin/env python3
"""Check the delivered WCL extension without redistributing raw measurements.

Default: hashes, design, saved-output arithmetic, coordinate/weight prediction
identities, unchanged untouched messages, and bridge equality. --csv additionally
reconstructs raw RSSI slots and transmitter truth from the pinned external CSV,
then verifies error magnitudes and raw-RSSI/intercept-derived weights.
This program does not refit intercepts, alter a manifest, or write inside the input.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path
import numpy as np

CSV_SHA='870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446'

def sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def req(ok: bool, msg: str):
    if not ok: raise ValueError(msg)

def close(a,b,msg,tol=1e-9):
    req(bool(np.allclose(a,b,rtol=0,atol=tol,equal_nan=False)),msg)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--csv',type=Path)
    p.add_argument('--report',type=Path,help='Optional output JSON outside the input root; must not exist')
    a=p.parse_args(); root=a.root.resolve();run=root/'extension'
    if a.report:
        report=a.report.resolve()
        req(not report.is_relative_to(root),'Report must be outside the input root')
        req(not report.exists(),'Refusing to overwrite report')
    status=json.loads((run/'RUN_STATUS.json').read_text())
    req(status['status']=='COMPLETE' and status['complete_pairs']==128,'Incomplete experiment')
    scheduled=json.loads((root/'protocol/DIRECTION_REGISTER.json').read_text())['cases']
    expected={(f['map'],f['k'],f['draw']):f for f in scheduled}
    req(len(expected)==128,'Invalid direction register')
    transformed=json.loads((root/'EXPORT_TRANSFORMATIONS.json').read_text())['transformations']
    for item in transformed: req(sha(root/item['path'])==item['exported_sha256'],'Exported reference hash mismatch')
    frame=None
    if a.csv:
        req(sha(a.csv)==CSV_SHA,'External CSV hash mismatch')
        import pandas as pd
        from pyproj import Transformer
        frame=pd.read_csv(a.csv)
        transformer=Transformer.from_crs(4326,32631,always_xy=True)
    refs={}
    for name in ['recovered29','official32_minus71']:
        with np.load(run/f'{name}_reference.npz',allow_pickle=False) as z:
            ref={k:z[k] for k in z.files}
        meta=json.loads((run/f'{name}_reference.json').read_text())
        req('raw_rssi' not in ref and 'truth' not in ref,'Raw source slice unexpectedly included')
        close(np.median(ref['errors']),meta['baseline_median_m'],'Baseline median',1e-10)
        req(ref['selected_ids'].shape==(2498,10),'Selected receiver array shape')
        if frame is not None:
            selected=frame.iloc[ref['source_rows']]
            x,y=transformer.transform(selected['Longitude'].to_numpy(),selected['Latitude'].to_numpy())
            ref['truth']=np.column_stack((x,y))
            ids=ref['selected_ids']; raw=np.zeros(ids.shape,float)
            for g in meta['coordinates']:
                vals=selected[f'BS {g}'].to_numpy(float)
                q,slot=np.where(ids==int(g));raw[q,slot]=vals[q]
            ref['raw_rssi']=raw
            close(np.linalg.norm(ref['predictions']-ref['truth'],axis=1),ref['errors'],'Reference error reconstruction',1e-8)
        refs[name]=(ref,meta)
    rows=list(csv.DictReader((run/'paired_results.csv').open()))
    req(len(rows)==128,'Wrong case count')
    seen=set();nbridge=0;maxpred=0.;maxweight=0.;verrors=0;vweight=0
    for row in rows:
        key=(row['map'],int(row['k']),int(row['draw']))
        req(key in expected and key not in seen,'Duplicate/unregistered case');seen.add(key)
        f=expected[key];case=row['case']; npz=run/'pairs'/f'{case}.npz'
        meta=json.loads((run/'pairs'/f'{case}.json').read_text())
        req(sha(npz)==row['array_sha256']==meta['array_sha256'],'Pair hash mismatch')
        req(meta['field']==f,'Field record mismatch')
        with np.load(npz,allow_pickle=False) as zz:z={k:zz[k] for k in zz.files}
        ref,rm=refs[row['map']];ids=ref['selected_ids'];valid=ids>=0
        target=np.isin(ids,[int(g) for g in f['offsets']]);touched=target.any(axis=1)
        req(np.array_equal(touched,z['touched']),'Touched subset mismatch')
        req(int(touched.sum())==int(row['touched_n']),'Touched count mismatch')
        req(np.array_equal(valid.sum(axis=1)-target.sum(axis=1),z['selected_clean_count']),'Remaining support mismatch')
        req(int(z['selected_clean_count'].min())>=1,'Clean support absent')
        mp={str(int(g)):xy for g,xy in zip(z['map_receiver_ids'],z['map_coordinates'])}
        req(set(mp)==set(rm['coordinates']),'Map membership mismatch')
        coords=np.zeros((2498,10,2))
        multiplier=np.ones((2498,10))
        for g,xy in mp.items():
            want=np.array(rm['coordinates'][g])
            if g in f['offsets']:
                off=f['offsets'][g];want=want+np.array([off['dx_m'],off['dy_m']])
            close(xy,want,'Coordinate field',0.)
            coords[ids==int(g)]=xy
            multiplier[ids==int(g)]=10**(-(meta['refit_a0'][g]-meta['reference_a0'][g])/10)
        req(meta['reference_a0']==rm['intercepts'],'Frozen intercepts mismatch')
        close(z['frozen_weights'],ref['weights'],'Frozen weights unchanged',0.)
        alt=z['frozen_weights']*multiplier;alt/=alt.sum(axis=1,keepdims=True)
        close(alt,z['refit_weights'],'Reweighting identity',1e-13)
        for arm in ['refit','frozen']:
            weights=z[arm+'_weights'];pred=z[arm+'_predictions'];err=z[arm+'_errors']
            req(np.isfinite(pred).all() and np.isfinite(err).all() and np.isfinite(weights).all(),'Nonfinite output')
            close(weights.sum(axis=1),1.,'Normalized weights',1e-13)
            reconstruction=(weights[:,:,None]*coords).sum(axis=1)
            maxpred=max(maxpred,float(np.max(np.abs(pred-reconstruction))))
            close(pred,reconstruction,'Prediction from weights',5e-9)
            close((weights*target).sum(axis=1),z[arm+'_target_weight_mass'],'Target weight mass',1e-13)
            close(np.median(err),float(row[arm+'_m']),'Message median',1e-9)
            close(np.median(err[touched]),float(row['touched_'+arm+'_m']),'Touched median',1e-9)
            close(100*(np.median(err)/rm['baseline_median_m']-1),float(row[arm+'_pct']),'Percent change',1e-9)
            req(np.array_equal(pred[~touched],ref['predictions'][~touched]),'Untouched prediction changed')
            if frame is not None:
                close(np.linalg.norm(pred-ref['truth'],axis=1),err,'Errors from external transmitter truth',1e-8)
                a0=np.zeros(ids.shape)
                intercepts=meta['refit_a0'] if arm=='refit' else meta['reference_a0']
                for g,v in intercepts.items():a0[ids==int(g)]=v
                w=np.where(valid,10**((ref['raw_rssi']-a0)/10),0.)
                w/=w.sum(axis=1,keepdims=True)
                maxweight=max(maxweight,float(np.max(np.abs(w-weights))))
                close(w,weights,'Weights from external RSSI and recorded intercepts',1e-13)
                verrors+=len(err);vweight+=len(err)
        close(float(row['frozen_m'])-float(row['refit_m']),float(row['delta_m']),'Paired delta')
        close(float(row['touched_frozen_m'])-float(row['touched_refit_m']),float(row['touched_delta_m']),'Touched delta')
        if f['historical_R29_bridge']:
            with np.load(root/'bridge/pairs'/f'{case}.npz',allow_pickle=False) as bridge:
                for k in bridge.files:req(np.array_equal(bridge[k],z[k]),'Bridge equality '+k)
            nbridge+=1
    req(seen==set(expected),'Missing planned field')
    for s in status['summaries']:
        cell=[row for row in rows if row['map']==s['map'] and int(row['k'])==s['k']]
        vals=np.array([float(row['delta_m']) for row in cell])
        req(len(vals)==32,'Incomplete cell')
        for name,value in [('median',np.median(vals)),('q25',np.quantile(vals,.25)),('q75',np.quantile(vals,.75)),('minimum',vals.min()),('maximum',vals.max())]:
            close(value,s['delta_m'][name],'Cell delta statistic '+name,1e-10)
        req(int((vals>0).sum())==s['positive'] and int((vals<0).sum())==s['negative'] and int((vals==0).sum())==s['zero'],'Sign count mismatch')
    result={'status':'PUBLIC_DERIVED_OUTPUT_CHECK_PASS','pairs':len(seen),'bridge_cases_equal':nbridge,
        'source_csv_supplied':a.csv is not None,'external_source_error_values_checked':verrors,
        'external_source_weight_vectors_checked':vweight,'max_prediction_identity_difference_m':maxpred,
        'max_external_weight_difference':maxweight,
        'scope':'Design, output arithmetic, weight/prediction identities and bridge equality. External CSV additionally enables error/RSSI-weight reconstruction. Does not independently refit intercepts or re-execute the producer.'}
    if a.report:a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
