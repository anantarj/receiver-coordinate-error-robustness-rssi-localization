"""Independent scalar check of the locked C1 registry and all retained output rows.

Does not import the primary model. Python math/statistics are used for all scalar
reference values; selected extreme cases are additionally checked at 70 digits.
This verifies deterministic controls, not independent deployment or novelty.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, statistics, time
from pathlib import Path
from functools import lru_cache


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--registry', type=Path, required=True)
    ap.add_argument('--lock', type=Path, required=True)
    ap.add_argument('--results', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise FileExistsError('The verification output must be new.')
    reg = json.loads(args.registry.read_text())
    lock = json.loads(args.lock.read_text())
    if digest(args.registry) != lock['registry_sha256']:
        raise ValueError('Registry hash no longer matches its lock.')
    n, d0, L = reg['n_fit'], reg['d0_m'], reg['L_m']
    cases = {c['id']: c for c in reg['cases']}
    cal = reg['calibration_positions_m']
    stats = {'rows_checked': 0, 'reference_errors': 0, 'removal_rows': 0,
             'undefined_removal_rows': 0, 'rate_rows': 0}
    worst = dict.fromkeys(['prediction_coordinate_m', 'error_m', 'target_mass',
                          'reference_remaining_mass', 'removal_error_m',
                          'influence_abs_m', 'noncancelled_influence_rel',
                          'intercept_db', 'rate_slope_difference'], 0.)
    t0 = time.monotonic()

    def h(x, y):
        return math.hypot(x[0]-y[0], x[1]-y[1])

    def fit(raw, positions, amap):
        return [statistics.median([raw[j][i] + 10*n*math.log10((h(x, ai)+d0)/d0)
                                  for j, x in enumerate(positions)])
                for i, ai in enumerate(amap)]

    def norm(raw, intercepts, kappa):
        # Base-10 powers, distinct from the primary NumPy exp implementation.
        lw = [kappa*(s-A)/(10*n) for s, A in zip(raw, intercepts)]
        shift = max(lw)
        w = [10**(v-shift) for v in lw]
        den = math.fsum(w)
        return [v/den for v in w]

    def center(p, amap):
        return [math.fsum(w*x[j] for w, x in zip(p, amap)) for j in range(2)]

    @lru_cache(None)
    def base(cid):
        c=cases[cid]; a=reg['layouts_m'][c['layout']]
        true = [-30.]*6 if c['shared_A_true'] else reg['A_true_dbm']
        raw = [[true[i]-10*reg['n_true']*math.log10((h(x,a[i])+d0)/d0)
                for i in range(6)] for x in cal]
        qr = [[true[i]-10*reg['n_true']*math.log10((h(x,a[i])+d0)/d0)+c['query_bias_db'][i]
               for i in range(6)] for x in c['queries']]
        return a, raw, qr, fit(raw,cal,a)

    @lru_cache(None)
    def shifted(cid, ratio):
        c=cases[cid]; a, raw, qr, a0=base(cid)
        targets=set(c['targets']); D=ratio*L
        newa=[[x[j]+(D*c['directions'][i][j] if i in targets else 0.) for j in range(2)]
              for i,x in enumerate(a)]
        return newa, fit(raw,cal,newa)

    @lru_cache(None)
    def ref(cid, qi, kappa):
        a,raw,qr,a0=base(cid); c=cases[cid]; t=set(c['targets'])
        p0=norm(qr[qi],a0,kappa); x0=center(p0,a)
        U=[i for i in range(6) if i not in t]
        pu=math.fsum(p0[i] for i in U)
        u=center([p0[i]/pu for i in U],[a[i] for i in U]) if U else None
        erem=h(u,c['queries'][qi]) if U else None
        return p0, h(x0,c['queries'][qi]), U, pu, u, erem

    rate_groups={}
    with (args.results/'c1_all_rows.csv').open(newline='') as f:
        for row in csv.DictReader(f):
            cid=row['case']; qi=int(row['query']); k=float(row['kappa'])
            ratio=float(row['D_over_L']); pol=row['policy']; c=cases[cid]
            a,raw,qr,a0=base(cid); newa,unr=shifted(cid,ratio)
            delta=[u-v for u,v in zip(unr,a0)]
            if pol=='frozen': aa=a0
            elif pol=='unrestricted': aa=unr
            elif pol=='shared_update':
                sh=statistics.median(delta); aa=[v+sh for v in a0]
            else:
                B=float(pol.replace('bounded','')); aa=[v+min(B,max(-B,d)) for v,d in zip(a0,delta)]
            p=norm(qr[qi],aa,k); pred=center(p,newa); err=h(pred,c['queries'][qi])
            p0,e0,U,pu,u,erem=ref(cid,qi,k)
            scale=max(1.,max(abs(v) for x in newa for v in x))
            tol=reg['analysis']['absolute_coordinate_tolerance_m']+reg['analysis']['relative_coordinate_tolerance']*scale
            # Unchanged registry identity and every field are checked, not sampled.
            assert int(row['targets'])==len(c['targets']) and int(row['remaining'])==len(U)
            assert (row['removal_operational_eligible']=='True')==(len(U)>=3)
            dp=max(abs(pred[j]-float(row[f'prediction_{"xy"[j]}_m'])) for j in range(2))
            de=abs(err-float(row['error_m']))
            assert dp<=tol and de<=2*tol,(cid,ratio,k,pol,qi,dp,de,tol)
            worst['prediction_coordinate_m']=max(worst['prediction_coordinate_m'],dp)
            worst['error_m']=max(worst['error_m'],de)
            bt=math.fsum(p[i] for i in c['targets'])
            masserr=abs(bt-float(row['target_mass']))
            puerr=abs(pu-float(row['reference_remaining_mass']))
            assert masserr<2e-13 and puerr<2e-13
            worst['target_mass']=max(worst['target_mass'],masserr)
            worst['reference_remaining_mass']=max(worst['reference_remaining_mass'],puerr)
            assert abs(e0-float(row['reference_error_m']))<=1e-7+2e-12*max(e0,1.)
            stats['reference_errors']+=1
            da=[v-w for v,w in zip(aa,a0)]
            maxd=max([da[i] for i in c['targets']],default=0.)
            ida=max(abs(maxd-float(row['max_target_intercept_change_db'])),abs(statistics.mean(da)-float(row['mean_intercept_change_db'])))
            assert ida<1e-10
            worst['intercept_db']=max(worst['intercept_db'],ida)
            if U:
                assert row['removal_status']=='defined'
                remerr=abs(erem-float(row['removal_error_m']))
                assert remerr<1e-7+2e-12*max(erem,1.)
                worst['removal_error_m']=max(worst['removal_error_m'],remerr)
                v=[math.fsum(p[i]*(newa[i][j]-u[j]) for i in c['targets']) for j in range(2)]
                infl=math.hypot(*v); old=float(row['influence_to_removal_m'])
                ie=abs(infl-old); worst['influence_abs_m']=max(worst['influence_abs_m'],ie)
                assert ie<=2*tol
                if c['targets'] and cid!='symmetric_two_opposite':
                    rel=ie/max(old,infl,1e-300)
                    assert rel<1e-10,(cid,ratio,k,pol,qi,rel)
                    worst['noncancelled_influence_rel']=max(worst['noncancelled_influence_rel'],rel)
                stats['removal_rows']+=1
            else:
                assert row['removal_status']=='undefined_no_untargeted_support'
                assert row['influence_to_removal_m']=='' and row['removal_error_m']==''
                infl=None; stats['undefined_removal_rows']+=1
            if ratio>=1e5:
                rate_groups.setdefault((cid,qi,k,pol),[]).append((ratio,infl,math.hypot(*pred)))
            stats['rows_checked']+=1
    assert stats['rows_checked']==lock['query_evaluations']
    with (args.results/'c1_rate_checks.csv').open(newline='') as f:
        for r in csv.DictReader(f):
            vals=rate_groups[(r['case'],int(r['query']),float(r['kappa']),r['policy'])]
            xs=[math.log10(v[0]) for v in vals]
            ys=[math.log10(v[2] if r['measure']=='prediction_norm' else v[1]) for v in vals]
            mx,my=statistics.mean(xs),statistics.mean(ys)
            slope=math.fsum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.fsum((x-mx)**2 for x in xs)
            diff=abs(slope-float(r['slope']))
            assert diff<1e-10 and abs(slope-float(r['expected']))<=reg['analysis']['rate_tolerance']
            worst['rate_slope_difference']=max(worst['rate_slope_difference'],diff)
            stats['rate_rows']+=1
    out={'status':'PASS','scope':'Independent scalar implementation; same locked deterministic inputs, not independent experimental replication.',
         'registry_sha256':digest(args.registry),'input_rows_sha256':digest(args.results/'c1_all_rows.csv'),
         'checks':stats,'maxima':worst,'timing_seconds':time.monotonic()-t0,
         'precision_boundary':'Tolerances address arithmetic at artificial coordinates up to 1e11 m, not physical precision.'}
    args.out.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__':
    main()
