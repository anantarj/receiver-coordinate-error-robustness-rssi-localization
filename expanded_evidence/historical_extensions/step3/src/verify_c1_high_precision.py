"""70-digit check of a fixed diagnostic subset of the C1 deterministic outputs.

Selection covers all four powers and five policies for one single-target layout,
plus weak-support, coherent zero-support, and symmetric-cancellation controls.
The subset is a numerical verification selection, not a held-out scientific test.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
import mpmath as mp


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--registry',type=Path,required=True)
    ap.add_argument('--lock',type=Path,required=True)
    ap.add_argument('--results',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists():raise FileExistsError('Use a fresh verification output.')
    reg=json.loads(args.registry.read_text());lock=json.loads(args.lock.read_text())
    assert hashlib.sha256(args.registry.read_bytes()).hexdigest()==lock['registry_sha256']
    mp.mp.dps=70
    def m(x):return mp.mpf(str(x))
    def point(p):return list(map(m,p))
    def hypot(x,y):return mp.sqrt(mp.fsum((a-b)**2 for a,b in zip(x,y)))
    def median(v):
        s=sorted(v);n=len(s)
        return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2
    def norm(s,A,k,n):
        logs=[k*(x-y)/(10*n) for x,y in zip(s,A)];hi=max(logs)
        vals=[mp.power(10,l-hi) for l in logs];sm=mp.fsum(vals)
        return [v/sm for v in vals]
    def center(p,a):return [mp.fsum(w*x[j] for w,x in zip(p,a)) for j in range(2)]
    conditions=[]
    for ratio in [10.,1e8]:
        for k in reg['kappa']:
            for pol in reg['calibration_policies']:
                conditions.append(('spread_k1_coherent_weak0',0,k,pol,ratio))
    for cid in ['spread_k1_coherent_weak40','spread_k6_coherent_weak0','symmetric_two_opposite']:
        for k in reg['kappa']:conditions.append((cid,0,k,'unrestricted',1e8))
    needed=set(conditions);rows={}
    with (args.results/'c1_all_rows.csv').open(newline='') as f:
        for r in csv.DictReader(f):
            key=(r['case'],int(r['query']),float(r['kappa']),r['policy'],float(r['D_over_L']))
            if key in needed:rows[key]=r
    assert len(rows)==len(needed)
    cases={c['id']:c for c in reg['cases']};reports=[]
    for key in conditions:
        cid,qi,k0,pol,ratio=key;c=cases[cid];n=m(reg['n_fit']);d0=m(reg['d0_m']);k=m(k0)
        a=[point(x) for x in reg['layouts_m'][c['layout']]];q=point(c['queries'][qi]);cal=[point(x) for x in reg['calibration_positions_m']]
        true=list(map(m,[-30.]*6 if c['shared_A_true'] else reg['A_true_dbm']))
        raw=[[true[i]-10*m(reg['n_true'])*mp.log10((hypot(x,a[i])+d0)/d0) for i in range(6)] for x in cal]
        sq=[true[i]-10*m(reg['n_true'])*mp.log10((hypot(q,a[i])+d0)/d0)+m(c['query_bias_db'][i]) for i in range(6)]
        def fit(amap):return [median([raw[j][i]+10*n*mp.log10((hypot(x,amap[i])+d0)/d0) for j,x in enumerate(cal)]) for i in range(6)]
        a0=fit(a);D=m(reg['L_m'])*m(ratio);targets=set(c['targets']);U=[i for i in range(6) if i not in targets]
        aa=[[x[j]+(D*m(c['directions'][i][j]) if i in targets else 0) for j in range(2)] for i,x in enumerate(a)]
        un=fit(aa);d=[v-u for v,u in zip(un,a0)]
        if pol=='frozen':A=a0
        elif pol=='unrestricted':A=un
        elif pol=='shared_update':
            sh=median(d);A=[v+sh for v in a0]
        else:
            B=m(pol.replace('bounded',''));A=[v+min(B,max(-B,dd)) for v,dd in zip(a0,d)]
        p=norm(sq,A,k,n);pred=center(p,aa);e=hypot(pred,q);r=rows[key]
        diff=max(abs(pred[j]-m(r[f'prediction_{"xy"[j]}_m'])) for j in range(2))
        de=abs(e-m(r['error_m']));scale=max(m(1),max(abs(v) for x in aa for v in x))
        tol=m(reg['analysis']['absolute_coordinate_tolerance_m'])+m(reg['analysis']['relative_coordinate_tolerance'])*scale
        assert diff<=tol and de<=2*tol
        p0=norm(sq,a0,k,n)
        if U:
            pu=mp.fsum(p0[i] for i in U);u=center([p0[i]/pu for i in U],[a[i] for i in U])
            z=[mp.fsum(p[i]*(aa[i][j]-u[j]) for i in targets) for j in range(2)]
            influence=mp.sqrt(mp.fsum(v*v for v in z));ie=abs(influence-m(r['influence_to_removal_m']))
            assert ie<=2*tol
            rel=float(ie/influence) if influence>mp.mpf('1e-60') else None
            if cid!='symmetric_two_opposite':assert rel is not None and rel<1e-10
        else:influence=None;ie=None;rel=None
        reports.append({'case':cid,'query':qi,'kappa':k0,'policy':pol,'D_over_L':ratio,
                        'prediction_component_error_m':float(diff),'score_error_m':float(de),
                        'high_precision_influence_m':mp.nstr(influence,50) if influence is not None else None,
                        'influence_absolute_error_m':float(ie) if ie is not None else None,
                        'nonzero_influence_relative_error':rel,
                        'within_locked_coordinate_tolerance':True})
    out={'status':'PASS','mpmath_version':mp.__version__,'decimal_digits':70,'cases_checked':len(reports),
         'selection':'fixed numerical diagnostic coverage; not outcome-blind research validation',
         'registry_sha256':lock['registry_sha256'],
         'max_prediction_component_error_m':max(v['prediction_component_error_m'] for v in reports),
         'max_score_error_m':max(v['score_error_m'] for v in reports),
         'max_noncancelled_influence_relative_error':max(v['nonzero_influence_relative_error'] or 0 for v in reports),
         'rows':reports}
    args.out.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
