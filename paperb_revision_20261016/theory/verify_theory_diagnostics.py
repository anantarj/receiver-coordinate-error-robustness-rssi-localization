"""Synthetic implementation checks, not numerical proof of the propositions."""
import json
from pathlib import Path
import numpy as np
from run_finite_diagnostics import contribution, interval_bounds, residual


def check():
    rng=np.random.default_rng(20261016)
    a=np.array([[20.,15.],[-30.,0.],[0.,-25.]])
    s=np.array([-80.,-70.,-90.]); A=np.array([-35.,-28.,-40.])
    points=np.array([[.5,1.],[-5.,8.],[15.,-10.]])
    v,g,undef=contribution(points,a,s,A)
    assert not undef.any()
    h=1e-4; gn=np.zeros_like(g)
    for j in range(2):
        step=np.zeros(2);step[j]=h
        gn[:,j]=(contribution(points+step,a,s,A)[0]-contribution(points-step,a,s,A)[0])/(2*h)
    jac_error=float(np.max(np.abs(g-gn)))
    assert jac_error<1e-6
    lo=np.array([-10.,-12.]);hi=np.array([12.,14.])
    lb,ub=interval_bounds(lo,hi,a,s,A)
    p=rng.uniform(lo,hi,size=(10000,2));values=contribution(p,a,s,A)[0]
    assert np.min(values)>=lb-1e-8 and np.max(values)<=ub+1e-8
    # Means, medians and a fixed 2-per-tail trimmed mean.
    funs=[np.mean,np.median,lambda y:np.mean(np.sort(y)[2:-2])]
    eqerr=0.;lip_excess=0.
    for _ in range(1000):
        y=rng.normal(size=11);z=y+rng.normal(size=11);b=float(rng.normal())
        for F in funs:
            eqerr=max(eqerr,abs(F(y+b)-F(y)-b))
            lip_excess=max(lip_excess,abs(F(y)-F(z))-np.max(np.abs(y-z)))
    assert eqerr<1e-12 and lip_excess<=1e-12
    # Exact one-dimensional quadratic objectives verify the finite comparison.
    u,v=-.7,.9;xstar=(u+v)/2;omega=max((-2-v)**2,(2-v)**2)
    lemma_slack=[]
    for x in np.linspace(-2,2,101):
        J=lambda y:(y-u)**2+(y-v)**2
        eta=J(x)-J(xstar)
        lemma_slack.append(omega+eta-(x-u)**2)
    assert min(lemma_slack)>=-1e-12
    # Explicit derivative-undefined convention is recorded, not silently zeroed.
    _,gc,uc=contribution(a[:1],a,s,A)
    assert uc[0] and np.isnan(gc[0]).all()
    out={'status':'passed','gradient_finite_difference_max_error_db2_per_m':jac_error,
         'interval_bounds_contain_10000_random_points':True,
         'functional_translation_max_error':eqerr,'functional_lipschitz_excess':lip_excess,
         'finite_lemma_quadratic_check_min_slack':min(lemma_slack),
         'undefined_derivative_preserved':True,
         'scope':'Synthetic implementation checks; mathematical proofs reside in THEORY_EXTENSION.tex.'}
    Path(__file__).with_name('SYNTHETIC_VERIFICATION.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out))

if __name__=='__main__':check()
