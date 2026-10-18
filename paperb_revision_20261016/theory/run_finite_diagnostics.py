"""Read-only finite mechanism reductions; no localization optimizations.

Protocol and file hashes must be locked before this script is executed.
Only the current script's directory receives outputs. One process, no workers.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import time

for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[key] = "1"
import numpy as np

ROOT = Path(__file__).resolve().parent
N, D0 = 4.7, 1.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def residual(points, anchors, rss, intercepts):
    delta = np.asarray(points)[:, None, :] - np.asarray(anchors)[None, :, :]
    distance = np.linalg.norm(delta, axis=2)
    value = rss[None, :] - intercepts[None, :] + 10*N*np.log10((distance+D0)/D0)
    return value, distance, delta


def contribution(points, anchors, rss, intercepts):
    """Squared term and true derivative away from every receiver involved."""
    if len(anchors) == 0:
        return np.zeros(len(points)), np.zeros((len(points), 2)), np.zeros(len(points), bool)
    r, distance, delta = residual(points, anchors, rss, intercepts)
    undefined = np.any(distance == 0., axis=1)
    jac = np.divide(delta, (distance*(distance+D0))[:, :, None],
                    out=np.zeros_like(delta), where=distance[:, :, None] > 0)
    jac *= 10*N/np.log(10.)
    grad = 2*np.sum(r[:, :, None]*jac, axis=1)
    grad[undefined] = np.nan
    return np.sum(r*r, axis=1), grad, undefined


def interval_bounds(lo, hi, anchors, rss, intercepts):
    if len(anchors) == 0:
        return 0., 0.
    near = np.maximum(np.maximum(lo-anchors, anchors-hi), 0.)
    far = np.maximum(np.abs(lo-anchors), np.abs(hi-anchors))
    dmin, dmax = np.linalg.norm(near, axis=1), np.linalg.norm(far, axis=1)
    rmin = rss-intercepts+10*N*np.log10((dmin+D0)/D0)
    rmax = rss-intercepts+10*N*np.log10((dmax+D0)/D0)
    lower = np.where((rmin <= 0) & (rmax >= 0), 0., np.minimum(rmin*rmin, rmax*rmax))
    upper = np.maximum(rmin*rmin, rmax*rmax)
    return float(np.sum(lower)), float(np.sum(upper))


def qstat(a, p):
    a = np.asarray(a)
    a = a[np.isfinite(a)]
    return float(np.quantile(a, p, method="linear")) if len(a) else None


def run():
    start = time.monotonic()
    protocol_path = ROOT/'FINITE_DIAGNOSTIC_PROTOCOL.json'
    protocol = json.loads(protocol_path.read_text())
    lock = json.loads((ROOT/'FINITE_DIAGNOSTIC_LOCK.json').read_text())
    assert sha(protocol_path) == lock['protocol_sha256']
    for item in protocol['bindings']:
        assert sha(item['path']) == item['sha256'], item['path']
    inp = np.load(protocol['input_path'])
    old = np.load(protocol['primary_array_path'])
    assert np.array_equal(inp['source_rows'], old['source_rows'])
    assert np.array_equal(inp['field_D_m'], old['field_D_m'])

    lo = np.asarray(protocol['region']['lower_m'])
    hi = np.asarray(protocol['region']['upper_m'])
    expect_lo = np.min(inp['cal_xy_m_flat'], axis=0)-1000.
    expect_hi = np.max(inp['cal_xy_m_flat'], axis=0)+1000.
    assert np.array_equal(lo, expect_lo) and np.array_equal(hi, expect_hi)
    axisx, axisy = [np.linspace(lo[j], hi[j], protocol['grid_side']) for j in range(2)]
    grid = np.array([(x,y) for x in axisx for y in axisy])
    F, Q = len(inp['field_D_m']), len(inp['source_rows'])
    candidate_names = ['original_zero_map_nlls', 'frozen_primary_nlls', 'refitted_primary_nlls']
    shape = (F, 2, Q, len(candidate_names))
    arrays = {
        'target_objective_db2': np.zeros(shape),
        'unchanged_objective_db2': np.zeros(shape),
        'target_gradient_db2_per_m': np.zeros(shape+(2,)),
        'unchanged_gradient_db2_per_m': np.zeros(shape+(2,)),
        'target_derivative_undefined': np.zeros(shape, bool),
        'unchanged_derivative_undefined': np.zeros(shape, bool),
        'candidate_inside_K': np.zeros((F,Q,len(candidate_names)), bool),
        'candidate_positions_m': np.zeros((F,Q,len(candidate_names),2)),
    }
    rows = []
    summary = []
    checks = {'identity_max_error_db': 0., 'own_output_objective_max_error_db2': 0.,
              'interval_enclosure_max_violation_db2': 0.,
              'unexposed_target_nonzero_count': 0}
    # Unchanged-objective grids repeat across magnitudes/directions/policies.
    ucache = {}
    for fi in range(F):
        row_start = len(rows)
        for qi in range(Q):
            use = inp['selected_mask'][qi]
            ids = inp['selected_ids'][qi,use].astype(int)-1
            rss = inp['query_rssi_dbm'][qi,use]
            target = inp['field_target_mask'][fi,ids]
            a = inp['field_anchors_m'][fi,ids]
            a0 = inp['reference_anchors_m'][ids]
            A0 = inp['reference_intercepts_dbm'][ids]
            AR = inp['field_refit_intercepts_dbm'][fi,ids]
            points = np.stack((old['nlls_position_m'][0,0,qi],
                               old['nlls_position_m'][fi,0,qi],
                               old['nlls_position_m'][fi,1,qi]))
            arrays['candidate_positions_m'][fi,qi] = points
            arrays['candidate_inside_K'][fi,qi] = np.all((points >= lo)&(points <= hi),axis=1)
            rbase, _, _ = residual(points,a0,rss,A0)
            rrefit, _, _ = residual(points,a,rss,AR)
            geometric_change = 10*N*np.log10((np.linalg.norm(points[:,None,:]-a[None,:,:],axis=2)+D0)/
                                             (np.linalg.norm(points[:,None,:]-a0[None,:,:],axis=2)+D0))
            checks['identity_max_error_db'] = max(checks['identity_max_error_db'],
                float(np.max(np.abs((rrefit-rbase)-(geometric_change-(AR-A0)[None,:])))))
            key = (qi, tuple(ids[~target].tolist()))
            if key not in ucache:
                ur, _, _ = residual(grid, a[~target], rss[~target], A0[~target])
                uvalues = np.sum(ur*ur,axis=1)
                ucache[key] = float(np.max(uvalues)-np.min(uvalues))
            for pi,A in enumerate((A0, AR)):
                gr, _, _ = residual(grid,a[target],rss[target],A[target])
                gv = np.sum(gr*gr,axis=1)
                gmin, gmax = float(gv.min()),float(gv.max())
                lower,upper = interval_bounds(lo,hi,a[target],rss[target],A[target])
                checks['interval_enclosure_max_violation_db2'] = max(
                    checks['interval_enclosure_max_violation_db2'],lower-gmin,gmax-upper,0.)
                tv,tg,tu = contribution(points,a[target],rss[target],A[target])
                uv,ug,uu = contribution(points,a[~target],rss[~target],A[~target])
                arrays['target_objective_db2'][fi,pi,qi]=tv
                arrays['unchanged_objective_db2'][fi,pi,qi]=uv
                arrays['target_gradient_db2_per_m'][fi,pi,qi]=tg
                arrays['unchanged_gradient_db2_per_m'][fi,pi,qi]=ug
                arrays['target_derivative_undefined'][fi,pi,qi]=tu
                arrays['unchanged_derivative_undefined'][fi,pi,qi]=uu
                own_point = 1 if pi==0 else 2
                checks['own_output_objective_max_error_db2'] = max(
                    checks['own_output_objective_max_error_db2'],
                    abs(float(tv[own_point]+uv[own_point])-float(old['nlls_objective_db2'][fi,pi,qi])))
                if not np.any(target):
                    checks['unexposed_target_nonzero_count'] += int(np.any(tv!=0) or np.any(tg!=0) or gmax!=0)
                rows.append({'field_index':fi,'D_m':float(inp['field_D_m'][fi]),
                    'draw':int(inp['field_draw'][fi]),'field_target_count':int(inp['field_target_count'][fi]),
                    'policy':['frozen','refit'][pi],'query_index':qi,'source_row':int(inp['source_rows'][qi]),
                    'selected_target_n':int(target.sum()),'selected_unchanged_n':int((~target).sum()),
                    'target_grid_min_db2':gmin,'target_grid_max_db2':gmax,
                    'target_grid_variation_db2':gmax-gmin,'target_interval_lower_db2':lower,
                    'target_interval_upper_db2':upper,'target_variation_upper_bound_db2':upper-lower,
                    'unchanged_grid_variation_db2':ucache[key]})
        field_rows=rows[row_start:]
        for pi,policy in enumerate(('frozen','refit')):
            current=[r for r in field_rows if r['policy']==policy and r['selected_target_n']>0]
            qi=np.array([r['query_index'] for r in current],dtype=int)
            entry={'field_index':fi,'D_m':float(inp['field_D_m'][fi]),'draw':int(inp['field_draw'][fi]),
                   'target_count':int(inp['field_target_count'][fi]),'policy':policy,
                   'all_queries':Q,'exposed_queries':len(qi)}
            for key in ('target_grid_variation_db2','target_variation_upper_bound_db2','unchanged_grid_variation_db2'):
                values=[r[key] for r in current]
                entry[key+'_p50']=qstat(values,.5)
                entry[key+'_p95']=qstat(values,.95)
            for ci,name in enumerate(candidate_names):
                gt=arrays['target_gradient_db2_per_m'][fi,pi,qi,ci]
                gu=arrays['unchanged_gradient_db2_per_m'][fi,pi,qi,ci]
                for key,value in [('target_penalty_db2',arrays['target_objective_db2'][fi,pi,qi,ci]),
                                  ('target_gradient_norm_db2_per_m',np.linalg.norm(gt,axis=-1)),
                                  ('unchanged_gradient_norm_db2_per_m',np.linalg.norm(gu,axis=-1))]:
                    entry[name+'_'+key+'_p50']=qstat(value,.5)
                    entry[name+'_'+key+'_p95']=qstat(value,.95)
                entry[name+'_outside_K_n']=int(np.count_nonzero(~arrays['candidate_inside_K'][fi,qi,ci]))
            summary.append(entry)
        print(json.dumps({'completed_field':fi,'fields':F,'rows':len(rows)}),flush=True)
    assert checks['identity_max_error_db'] < 1e-10
    assert checks['own_output_objective_max_error_db2'] < 1e-7
    assert checks['interval_enclosure_max_violation_db2'] < 1e-7
    assert checks['unexposed_target_nonzero_count'] == 0
    for name,data in [('FINITE_FIELD_QUERY_DIAGNOSTICS.csv',rows),('FINITE_FIELD_SUMMARIES.csv',summary)]:
        with (ROOT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    arrays.update(source_rows=inp['source_rows'],field_D_m=inp['field_D_m'],field_draw=inp['field_draw'],
                  field_target_count=inp['field_target_count'],candidate_names=np.asarray(candidate_names),
                  region_lower_m=lo,region_upper_m=hi,grid_points_m=grid)
    np.savez_compressed(ROOT/'FINITE_POINT_DIAGNOSTICS.npz',**arrays)
    receipt={'status':'completed','protocol_sha256':sha(protocol_path),'source_sha256':sha(__file__),
        'input_sha256':sha(protocol['input_path']),'primary_array_sha256':sha(protocol['primary_array_path']),
        'field_query_policy_rows':len(rows),'candidate_points_per_state':3,'checks':checks,
        'elapsed_seconds':time.monotonic()-start,'optimization_calls':0,
        'global_certificates_claimed':False,'region_calibration_defined':True,
        'floating_point_bound_scope':'Analytical interval formula evaluated in float64, not directed-rounding certificate',
        'output_hashes':{p.name:sha(p) for p in [ROOT/'FINITE_FIELD_QUERY_DIAGNOSTICS.csv',
                         ROOT/'FINITE_FIELD_SUMMARIES.csv',ROOT/'FINITE_POINT_DIAGNOSTICS.npz']}}
    (ROOT/'FINITE_DIAGNOSTIC_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    run()
