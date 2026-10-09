#!/usr/bin/env python3
"""Independent scalar checks of STEP1 quantiles and removal predictions.

Uses manual sorted linear interpolation and math.fsum row sums, not the main
analysis's quantile/einsum/removal functions. No original calibration execution.
"""
from pathlib import Path
import argparse,csv,hashlib,io,json,math,zipfile
import numpy as np

SHA='01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268'

def quant(x,t):
    v=sorted(map(float,x));p=(len(v)-1)*t;i=math.floor(p);j=math.ceil(p)
    return v[i]+(p-i)*(v[j]-v[i])

def run(archive,out,report):
    if report.exists(): raise FileExistsError(report)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA:raise ValueError('archive hash')
    z=zipfile.ZipFile(archive);prefix='receiver-coordinate-error-robustness-rssi-localization-v1.1.0/calibration_extension/'
    def npz(p):
        with np.load(io.BytesIO(z.read(prefix+p)),allow_pickle=False) as a:return dict(a)
    qs=list(csv.DictReader((out/'paired_quantiles_by_field.csv').open()));mxq=0.;mxp=0.;checks=0;rows=[];mxmass=0.
    cache={};refs={}
    for name in ['recovered29','official32_minus71']:
        refs[name]=(npz(f'extension/{name}_reference.npz'),json.loads(z.read(prefix+f'extension/{name}_reference.json')))
    for name in refs:
        ref,meta=refs[name]
        for k in [1,2]:
            targetids=set([14] if k==1 else [14,69]);ids=ref['selected_ids'];w=ref['weights']
            pred=[]
            for q,idrow in enumerate(ids):
                keep=[s for s,g in enumerate(idrow) if g>=0 and int(g) not in targetids]
                total=math.fsum(float(w[q,s]) for s in keep)
                if total<=0:raise ValueError('undefined removal')
                pred.append([math.fsum(float(w[q,s])*float(meta['coordinates'][str(int(idrow[s]))][j]) for s in keep)/total for j in [0,1]])
            pred=np.asarray(pred)
            delivered=np.load(out/'removal_predictions'/f'{name}_top{k}.npz',allow_pickle=False)
            pdiff=float(np.max(np.abs(pred-delivered['predictions'])));mxp=max(mxp,pdiff)
            if pdiff>1e-6:raise ValueError('Scalar removal mismatch')
            for d in range(32):
                case=f'{name}_top{k}_r{d:02d}';a=npz('extension/pairs/'+case+'.npz'); cache[case]=a
                jmeta=json.loads(z.read(prefix+'extension/pairs/'+case+'.json'))
                t=np.isin(ids,list(targetids));valid=ids>=0
                zslot=np.ones(ids.shape)
                for g in targetids:zslot[ids==g]=10**(-(jmeta['refit_a0'][str(g)]-jmeta['reference_a0'][str(g)])/10)
                pu=(w*valid*(~t)).sum(axis=1);tz=(w*t*zslot).sum(axis=1)
                odds=tz/pu;bp=odds/(1+odds)
                mdiff=float(np.max(np.abs(bp-a['refit_target_weight_mass'])));mxmass=max(mxmass,mdiff)
                if mdiff>1e-12:raise ValueError('Reference-mass odds identity')
                dist=np.linalg.norm(a['refit_predictions']-pred,axis=1)
                q=int(np.argmax(dist));eligible=delivered['original_min3_eligible']
                qe=int(np.argmax(np.where(eligible,dist,-1)))
                rows.append({'case':case,'map':name,'k':k,'draw':d,'worst_local_row':q,'worst_source_row':int(ref['source_rows'][q]),
                    'max_refit_remove_distance_m':float(dist[q]),'worst_remaining_clean':int(delivered['selected_clean_count'][q]),
                    'worst_frozen_target_mass':float(a['frozen_target_weight_mass'][q]),
                    'worst_refit_target_mass':float(a['refit_target_weight_mass'][q]),'worst_reference_clean_mass':float(pu[q]),
                    'worst_refit_error_m':float(a['refit_errors'][q]),'worst_frozen_error_m':float(a['frozen_errors'][q]),
                    'max_distance_min3_subset_m':float(dist[qe]),'min3_worst_source_row':int(ref['source_rows'][qe]),
                    'min3_worst_clean':int(delivered['selected_clean_count'][qe]),
                    'min3_worst_refit_target_mass':float(a['refit_target_weight_mass'][qe])})
    for row in qs:
        a=cache[row['case']];mask=a['touched'] if row['population']=='affected' else np.ones(2498,bool)
        rf=quant(a['refit_errors'][mask],float(row['quantile']));ff=quant(a['frozen_errors'][mask],float(row['quantile']))
        for key,value in [('refit_m',rf),('frozen_m',ff),('paired_benefit_m',ff-rf)]:
            diff=abs(float(row[key])-value);mxq=max(mxq,diff)
            if diff>1e-8:raise ValueError('Manual quantile mismatch')
            checks+=1
    worstfile=report.parent/'POSTHOC_FINITE_SUPPORT_AUDIT.csv'
    with worstfile.open('w',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
    receipt={'status':'PASS','checks':'Manual linear quantiles; scalar fsum removal predictions; reference clean-mass/attenuation odds identity.',
      'quantile_cells_checked':checks,'removal_prediction_rows_checked':2*2*2498,'paired_mass_values_checked':128*2498,
      'max_quantile_difference_m':mxq,'max_scalar_removal_coordinate_difference_m':mxp,'max_mass_odds_identity_difference':mxmass,
      'posthoc_case_selection':'All 128 fieldwise maxima and all 128 maxima restricted to >=3 remaining receivers; selected for numerical diagnosis after observing wide maxima, not new confirmatory evidence.',
      'no_truth_inference':True,'no_new_fits':True}
    report.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--results',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();run(a.archive,a.results,a.report)
