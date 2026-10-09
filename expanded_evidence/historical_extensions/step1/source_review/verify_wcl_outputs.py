#!/usr/bin/env python3
"""Independent saved-output reconstruction for the bounded WCL extension.
Does not invoke the producer and does not fit intercepts or rerun localization.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def require(ok, msg):
    if not ok: raise RuntimeError(msg)


def close(actual, expected, label, tol=1e-8):
    require(np.allclose(actual, expected, rtol=0, atol=tol, equal_nan=False), label)


def main():
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument('--run',type=Path,required=True)
    pa.add_argument('--bridge',type=Path,required=True)
    pa.add_argument('--protocol',type=Path,required=True)
    pa.add_argument('--report',type=Path,required=True)
    a=pa.parse_args();r=a.run
    status=json.loads((r/'RUN_STATUS.json').read_text())
    require(status['status']=='COMPLETE' and status['complete_pairs']==128, 'Incomplete producer status')
    fields=json.loads((a.protocol/'DIRECTION_REGISTER.json').read_text())['cases']
    expected={(f['map'],f['k'],f['draw']):f for f in fields}
    rows=list(csv.DictReader((r/'paired_results.csv').open()))
    require(len(rows)==128,'Wrong CSV length')
    seen=set(); stats=[]; max_pred=0.;max_weight=0.; inspected=0; bridge_cases=0
    references={}
    for name in ['recovered29','official32_minus71']:
        ref=np.load(r/f'{name}_reference.npz',allow_pickle=False)
        meta=json.loads((r/f'{name}_reference.json').read_text())
        close(np.linalg.norm(ref['predictions']-ref['truth'],axis=1),ref['errors'],'Reference errors',1e-10)
        close(np.median(ref['errors']),meta['baseline_median_m'],'Reference median',1e-10)
        references[name]=(ref,meta)
    for row in rows:
        name,k,draw=row['map'],int(row['k']),int(row['draw']); key=(name,k,draw)
        require(key in expected and key not in seen,'Duplicate/unregistered case');seen.add(key)
        f=expected[key];case=row['case'];meta=json.loads((r/'pairs'/f'{case}.json').read_text())
        path=r/'pairs'/f'{case}.npz'
        require(sha(path)==row['array_sha256']==meta['array_sha256'],'Array hash mismatch')
        require(meta['field']==f,'Field metadata mismatch')
        z=np.load(path,allow_pickle=False);ref,refmeta=references[name]
        gids=z['map_receiver_ids'];xy=z['map_coordinates']
        require(len(set(map(int,gids)))==len(gids),'Duplicate map identities')
        mp={str(int(g)):pos for g,pos in zip(gids,xy)}
        targets={int(g) for g in f['offsets']}
        ids=ref['selected_ids'];valid=ids>=0;touched=np.isin(ids,list(targets)).any(axis=1)
        require(np.array_equal(touched,z['touched']),'Touched subset mismatch')
        require(int(touched.sum())==int(row['touched_n']),'Touched count mismatch')
        selectedxy=np.zeros((2498,10,2))
        for g in mp:
            selectedxy[ids==int(g)]=mp[g]
            base=np.array(refmeta['coordinates'][g]);want=base.copy()
            if int(g) in targets:
                d=f['offsets'][g];want=base+np.array([d['dx_m'],d['dy_m']])
            close(mp[g],want,'Coordinate field mismatch',0)
        require(meta['reference_a0']==refmeta['intercepts'],'Frozen intercept mismatch')
        errors={};weight_sets={}
        for arm,intercepts in [('frozen',meta['reference_a0']),('refit',meta['refit_a0'])]:
            require(set(intercepts)==set(mp),'Intercept membership mismatch')
            a0=np.zeros_like(ref['raw_rssi'])
            for g,v in intercepts.items(): a0[ids==int(g)]=v
            raw=np.where(valid,ref['raw_rssi'],0.)
            ww=np.where(valid,np.power(10.,(raw-a0)/10.),0.)
            ww=ww/ww.sum(axis=1,keepdims=True)
            saved=z[f'{arm}_weights']
            max_weight=max(max_weight,float(np.max(np.abs(saved-ww))))
            close(ww,saved,'Weight reconstruction mismatch',1e-13)
            pred=(ww[:,:,None]*selectedxy).sum(axis=1)
            max_pred=max(max_pred,float(np.max(np.abs(pred-z[f'{arm}_predictions']))))
            close(pred,z[f'{arm}_predictions'],'Prediction reconstruction mismatch',5e-9)
            err=np.linalg.norm(z[f'{arm}_predictions']-ref['truth'],axis=1)
            close(err,z[f'{arm}_errors'],'Error reconstruction mismatch',1e-10)
            close(np.median(err),float(row[f'{arm}_m']),'Full median mismatch',1e-9)
            close(np.median(err[touched]),float(row[f'touched_{arm}_m']),'Touched median mismatch',1e-9)
            pct=100*(float(np.median(err))/refmeta['baseline_median_m']-1)
            close(pct,float(row[f'{arm}_pct']),'Percent change mismatch',1e-10)
            require(np.array_equal(z[f'{arm}_predictions'][~touched],ref['predictions'][~touched]),'Untouched prediction changed')
            targetmass=(ww*np.isin(ids,list(targets))).sum(axis=1)
            close(targetmass,z[f'{arm}_target_weight_mass'],'Target weight mass mismatch',1e-13)
            errors[arm]=err;weight_sets[arm]=ww; inspected+=2498
        # Normalized reweighting identity, independently applied to frozen p_i.
        multiplier=np.ones_like(weight_sets['frozen'])
        for g in mp:
            multiplier[ids==int(g)]=10**(-(meta['refit_a0'][g]-meta['reference_a0'][g])/10)
        algebra=weight_sets['frozen']*multiplier
        algebra=algebra/algebra.sum(axis=1,keepdims=True)
        close(algebra,weight_sets['refit'],'Normalized reweighting identity',1e-13)
        delta=float(np.median(errors['frozen'])-np.median(errors['refit']))
        close(delta,float(row['delta_m']),'Pair delta mismatch',1e-10)
        close(delta/refmeta['baseline_median_m']*100,float(row['delta_pp']),'Pair pp mismatch',1e-10)
        if f['historical_R29_bridge']:
            zz=np.load(a.bridge/'pairs'/f'{case}.npz',allow_pickle=False)
            for field in zz.files: require(np.array_equal(zz[field],z[field]),'Bridge/extension array mismatch '+field)
            bridge_cases+=1
        stats.append((name,k,delta,float(row['refit_m']),float(row['frozen_m']),float(row['touched_delta_m'])))
    require(seen==set(expected),'Scheduled field missing')
    require(len(list((r/'pairs').glob('*.npz')))==128,'Unexpected pair arrays')
    for summary in status['summaries']:
        ss=[x for x in stats if x[0]==summary['map'] and x[1]==summary['k']]
        d=np.array([x[2] for x in ss])
        for name,expected_value in [('median',np.median(d)),('q25',np.quantile(d,.25)),('q75',np.quantile(d,.75)),('minimum',d.min()),('maximum',d.max())]:
            close(summary['delta_m'][name],expected_value,'Cell summary '+name,1e-10)
        require(int((d>0).sum())==summary['positive'] and int((d<0).sum())==summary['negative'],'Sign count mismatch')
    report={'status':'SAVED_OUTPUT_RECONSTRUCTION_PASS','complete_pairs':128,'scored_message_condition_values':inspected,
      'cells':4,'fields_per_cell':32,'bridge_pair_arrays_equal':bridge_cases,
      'maximum_prediction_reconstruction_difference_m':max_pred,'maximum_normalized_weight_difference':max_weight,
      'checks':['exact scheduled field set','array hashes','native population identities carried in reference arrays','exact map transformations',
                'unchanged frozen intercepts','normalized weights from RSSI and saved intercepts','predictions from saved weights/coordinates',
                'errors from predictions and transmitter positions','whole/touched medians','signed paired differences',
                'primary per-cell median/IQR/range/sign counts','untouched prediction equality','normalized reweighting identity','historical bridge array equality'],
      'limit':'Independent reconstruction from saved outputs and inputs; not a second intercept-fitting run or independent physical experiment.'}
    a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
