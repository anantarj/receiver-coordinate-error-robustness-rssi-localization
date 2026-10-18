#!/usr/bin/env python3
"""Additive, bounded found-candidate removal diagnostic; never changes primary results."""
from __future__ import annotations
import csv, hashlib, json, sys, time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]/'paperb_execution_20261015'
sys.path.insert(0,str(BASE/'src'))
import rss_nlls_production as solver

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n');t.replace(p)
def key_for(a,s,c):
    h=hashlib.sha256()
    for label,x in [('anchors',a),('rss',s),('intercepts',c),('n_d0',np.array([4.7,1.0],dtype=np.float64))]:
        x=np.ascontiguousarray(x);h.update(label.encode());h.update(str(x.dtype).encode());h.update(str(x.shape).encode());h.update(x.tobytes())
    return h.hexdigest()
def csv_write(p,rows):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def run():
    start=time.monotonic()
    ip=BASE/'inputs/blocks/study1_official32_minus71_all.npz'
    rp=BASE/'results/arrays/study1_official32_minus71_all.npz'
    sp=BASE/'src/rss_nlls_production.py'
    proto={'scope':'Post hoc diagnostic follow-up fixed before removal outcomes are computed',
      'input_sha256':sha(ip),'original_results_sha256':sha(rp),'solver_sha256':sha(sp),'runner_sha256':sha(__file__),
      'query_indices':'All 512 fixed primary catalogue-map all-calibration queries; no resampling',
      'target_sets':[[14],[14,69]],'parameters':{'n':4.7,'d0_m':1.0},
      'removal_input':'Selected receiver order retained; drop target IDs; original reference geometry and original A_U',
      'global_deduplication':'SHA256 of labels,dtypes,shapes and ordered binary arrays including n,d0',
      'solver':'Unchanged production 3x3 plus receiver starts, 200 local evaluations per start, same tolerances',
      'retention':'Every prescribed start; every finite recorded endpoint or fallback; separate incumbent; recomputed local objective; local statuses',
      'competitive_bands_db2':[0.01,0.001,0.0001],
      'outcomes':['distance from original full estimate to found competitive unchanged-receiver pool','signed J_U(original full estimate)-best found J_U','movement from original full zero-map estimate'],
      'strata':['all queries','target-exposed queries','exposed queries with fewer than 3 remaining receivers','exposed queries with at least 3 remaining receivers'],
      'aggregation':'Per field/policy/stratum median and P95; min/max of the four directional medians for each D,targetset,policy,stratum',
      'negative_signed_differences':'Retained without clipping; not a certified optimality gap',
      'calibration_region_K':{'definition':'Reference calibration bounding rectangle expanded by 1000 m','lower_m':[591559.2238088003,5670393.25164725],'upper_m':[602828.8447644523,5678034.892108071],'usage':'Outside-K flags only; removal solver remains unconstrained'},
      'fewer_than_3_remaining':'Mathematical diagnostic only, not operationally eligible; one/two receiver objectives can have continuum or multiple minimizers',
      'found_set_caution':'Finite found candidate sets, not complete near-optimal regions or true minimizer sets; distance to finite set does not establish distance to exact minimizers',
      'no_truth_solver':'Query reference coordinates are not loaded into the solve function or used to select candidates',
      'escalation':'None pre-authorized in this execution; primary found pools only; unresolved deficiencies remain explicit',
      'workers':1}
    pp=ROOT/'REMOVAL_PROTOCOL.json'
    if pp.exists():
        assert json.loads(pp.read_text())==proto,'Protocol/code changed; refuse resume'
    else:
        write_json(pp,proto)
        (ROOT/'REMOVAL_PROTOCOL.sha256').write_text(sha(pp)+'  REMOVAL_PROTOCOL.json\n')
    with np.load(ip,allow_pickle=False) as f:b={k:f[k] for k in f.files}
    with np.load(rp,allow_pickle=False) as f:r={k:f[k] for k in f.files}
    assert len(b['source_rows'])==512 and np.array_equal(b['source_rows'],r['source_rows'])
    target_sets=[(14,),(14,69)];mapping=[];cache={};new=0
    for ti,targets in enumerate(target_sets):
      for qi in range(512):
        mask=b['selected_mask'][qi].astype(bool);ids=b['selected_ids'][qi,mask].astype(int)
        keep=~np.isin(ids,targets);uid=ids[keep];lookup=uid-1
        a=np.ascontiguousarray(b['reference_anchors_m'][lookup]);s=np.ascontiguousarray(b['query_rssi_dbm'][qi,mask][keep]);c=np.ascontiguousarray(b['reference_intercepts_dbm'][lookup])
        assert len(a)>=1
        key=key_for(a,s,c);path=ROOT/'candidates'/(key+'.json')
        if key not in cache:
          if path.exists():
            cell=json.loads(path.read_text());assert cell['input_hash']==key and cell['solver_sha256']==sha(sp)
          else:
            out=solver.solve(a,s,c,n=4.7,d0=1.0)
            origin,aa,scale,starts=solver._geometry(a,3);args=(aa,s,c,4.7,1.0)
            pool=[]
            for j,x in enumerate(starts):
              pool.append({'kind':'start','start_index':j,'position_m':(x+origin).tolist(),'objective_db2':solver.objective(x,*args),'status':None,'nfev':0,'success':None})
              xend=np.asarray(out['local_position_m'][j])-origin
              val=solver.objective(xend,*args)
              if np.isfinite(xend).all() and np.isfinite(val):
                pool.append({'kind':'endpoint_or_fallback','start_index':j,'position_m':out['local_position_m'][j],'objective_db2':val,'status':out['local_status'][j],'nfev':out['local_nfev'][j],'success':out['local_converged'][j],'exception':out['local_exception'][j]})
            inc=np.asarray(out['position_m'])-origin
            pool.append({'kind':'incumbent','start_index':out['best_start_index'],'position_m':out['position_m'],'objective_db2':solver.objective(inc,*args),'status':None,'nfev':0,'success':None,'selected_source':out['best_candidate_source']})
            best=min(p['objective_db2'] for p in pool)
            cell={'input_hash':key,'solver_sha256':sha(sp),'anchors_m':a.tolist(),'rss_dbm':s.tolist(),'intercepts_dbm':c.tolist(),'n':4.7,'d0_m':1.0,'remaining_receivers':len(a),'solver_result':out,'candidates':pool,'best_found_objective_db2':best,'found_not_complete':True}
            write_json(path,cell);new+=1
          cache[key]=cell
        mapping.append({'target_set':','.join(map(str,targets)),'target_set_index':ti,'query_index':qi,'source_row':int(b['source_rows'][qi]),'original_receiver_count':len(ids),'target_exposure':int((~keep).sum()),'remaining_receiver_count':len(uid),'operationally_eligible_after_removal':len(uid)>=3,'input_hash':key})
        if len(mapping)%64==0:
            write_json(ROOT/'PROGRESS.json',{'mapped':len(mapping),'expected':1024,'unique_solved':len(cache),'new_solves':new,'seconds':time.monotonic()-start})
            print(json.dumps({'mapped':len(mapping),'unique_solved':len(cache),'seconds':round(time.monotonic()-start,2)}),flush=True)
    csv_write(ROOT/'REMOVAL_INPUT_MAPPING.csv',mapping)
    metrics=[]
    for m in mapping:
      qi=m['query_index'];ti=m['target_set_index'];targets=target_sets[ti];cell=cache[m['input_hash']]
      a=np.asarray(cell['anchors_m']);s=np.asarray(cell['rss_dbm']);c=np.asarray(cell['intercepts_dbm'])
      origin=a.mean(axis=0);aa=a-origin;args=(aa,s,c,4.7,1.0)
      pool=np.asarray([p['position_m'] for p in cell['candidates']]);values=np.array([p['objective_db2'] for p in cell['candidates']]);best=cell['best_found_objective_db2']
      zero=r['nlls_position_m'][0,0,qi]
      for fi in range(25):
        if fi and tuple(np.flatnonzero(b['field_target_mask'][fi])+1)!=targets:continue
        # U must be identical for both policies and all D/directions.
        lookup=(b['selected_ids'][qi,b['selected_mask'][qi]]).astype(int)-1
        lookup=lookup[~np.isin(lookup+1,targets)]
        assert np.array_equal(b['field_anchors_m'][fi,lookup],a)
        assert np.array_equal(b['field_refit_intercepts_dbm'][fi,lookup],c)
        for pi in range(2):
          pos=r['nlls_position_m'][fi,pi,qi]
          base={'target_set':m['target_set'],'query_index':qi,'source_row':m['source_row'],'field_index':fi,'D_m':float(b['field_D_m'][fi]),'draw':int(b['field_draw'][fi]),'policy':['frozen','refitted'][pi],'target_exposure':m['target_exposure'],'remaining_receiver_count':m['remaining_receiver_count'],'operationally_eligible_after_removal':m['operationally_eligible_after_removal'],'best_found_U_db2':best,'JU_at_full_db2':solver.objective(pos-origin,*args),'full_movement_from_zero_m':float(np.linalg.norm(pos-zero))}
          base['signed_JU_excess_vs_best_found_db2']=base['JU_at_full_db2']-best
          lo=np.asarray(proto['calibration_region_K']['lower_m']);hi=np.asarray(proto['calibration_region_K']['upper_m'])
          base['full_position_outside_K']=bool(np.any(pos<lo) or np.any(pos>hi))
          base['removal_incumbent_outside_K']=bool(np.any(np.asarray(cell['solver_result']['position_m'])<lo) or np.any(np.asarray(cell['solver_result']['position_m'])>hi))
          for band in (0.01,0.001,0.0001):
            pc=pool[values<=best+band]
            base[f'distance_to_found_U_band_{band}_m']=float(np.min(np.linalg.norm(pc-pos,axis=1)))
            base[f'found_U_band_{band}_diameter_m']=float(np.max(np.linalg.norm(pc[:,None]-pc[None,:],axis=2)))
          metrics.append(base)
    csv_write(ROOT/'REMOVAL_COMPARISONS.csv',metrics)
    metric_names=['distance_to_found_U_band_0.01_m','signed_JU_excess_vs_best_found_db2','full_movement_from_zero_m']
    strata={'all':lambda x:True,'exposed':lambda x:x['target_exposure']>0,'exposed_U_lt3':lambda x:x['target_exposure']>0 and x['remaining_receiver_count']<3,'exposed_U_ge3':lambda x:x['target_exposure']>0 and x['remaining_receiver_count']>=3}
    summaries=[]
    for target in ['14','14,69']:
      for fi in sorted({x['field_index'] for x in metrics if x['target_set']==target}):
        for policy in ('frozen','refitted'):
          group=[x for x in metrics if x['target_set']==target and x['field_index']==fi and x['policy']==policy]
          for name,pred in strata.items():
            part=[x for x in group if pred(x)]
            if not part:continue
            row={'target_set':target,'field_index':fi,'D_m':part[0]['D_m'],'draw':part[0]['draw'],'policy':policy,'stratum':name,'N':len(part),'negative_JU_difference_count':sum(x['signed_JU_excess_vs_best_found_db2']<0 for x in part),'material_negative_below_minus_1e8_count':sum(x['signed_JU_excess_vs_best_found_db2']<-1e-8 for x in part)}
            for metric in metric_names:
              z=np.array([x[metric] for x in part]);row[metric+'_median']=float(np.quantile(z,.5,method='linear'));row[metric+'_p95']=float(np.quantile(z,.95,method='linear'));row[metric+'_min']=float(z.min());row[metric+'_max']=float(z.max())
            summaries.append(row)
    csv_write(ROOT/'REMOVAL_FIELD_SUMMARIES.csv',summaries)
    ranges=[]
    for target in ('14','14,69'):
      for D in (100.,1000.,5000.):
        for policy in ('frozen','refitted'):
          for stratum in strata:
            part=[x for x in summaries if x['target_set']==target and x['D_m']==D and x['policy']==policy and x['stratum']==stratum]
            if not part:continue
            assert len(part)==4
            row={'target_set':target,'D_m':D,'policy':policy,'stratum':stratum,'N_per_direction':part[0]['N'],'directions':len(part)}
            for metric in metric_names:
              z=[x[metric+'_median'] for x in part];row[metric+'_median_min']=min(z);row[metric+'_median_max']=max(z)
            ranges.append(row)
    csv_write(ROOT/'REMOVAL_DIRECTION_MEDIAN_RANGES.csv',ranges)
    counts=[]
    for target in ('14','14,69'):
      for exposure in (0,1,2):
        for remaining in range(1,11):
          part=[x for x in mapping if x['target_set']==target and x['target_exposure']==exposure and x['remaining_receiver_count']==remaining]
          if part:counts.append({'target_set':target,'target_exposure':exposure,'remaining_receiver_count':remaining,'N':len(part),'operationally_eligible_after_removal':remaining>=3})
    csv_write(ROOT/'REMOVAL_RECEIVER_COUNTS.csv',counts)
    receipt={'status':'COMPLETE','mapped_objectives':len(mapping),'unique_numerical_inputs':len(cache),'new_solves':new,'comparison_rows_including_two_zero_policies':len(metrics),'candidate_records':sum(len(c['candidates']) for c in cache.values()),'unique_input_local_runs_with_nonconvergence':sum(c['solver_result']['local_runs']-c['solver_result']['local_runs_converged'] for c in cache.values()),'inputs_with_any_nonconvergence':sum(c['solver_result']['local_runs']>c['solver_result']['local_runs_converged'] for c in cache.values()),'signed_difference_min_db2':min(x['signed_JU_excess_vs_best_found_db2'] for x in metrics),'negative_below_minus_1e8_rows':sum(x['signed_JU_excess_vs_best_found_db2']<-1e-8 for x in metrics),'seconds':time.monotonic()-start,'inputs_unchanged':sha(ip)==proto['input_sha256'] and sha(rp)==proto['original_results_sha256'] and sha(sp)==proto['solver_sha256'],'protocol_sha256':sha(pp),'files':{p.name:sha(p) for p in sorted(ROOT.glob('*.csv'))},'limitations':['Found finite candidate pools only; no exact global minimum or full minimizer-region certification','One/two remaining receivers are a mathematical diagnostic, not an operational output','No stronger-search extension executed; signed differences retained and unresolved search limitations disclosed','Primary full estimates stay frozen; any candidate-branch sensitivity elsewhere must also qualify comparisons']}
    assert receipt['inputs_unchanged']
    write_json(ROOT/'REMOVAL_RECEIPT.json',receipt)
    print(json.dumps(receipt),flush=True)
if __name__=='__main__':run()
