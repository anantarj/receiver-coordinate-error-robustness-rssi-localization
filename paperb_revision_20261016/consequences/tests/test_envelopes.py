"""Brute-force tiny worlds test the claims, independently of the data pipeline."""
import itertools,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common import contrast_envelope,transfer_bounds,transfer,bounds_sign,writej,HERE

def enumerate_vectors(pools):return np.array(list(itertools.product(*pools)),float)
def run():
    checks=[]
    # Each candidate assignment can change order statistics. Exhaustively enumerate
    # rather than compare the function with an algebraically identical implementation.
    left=[[0,70],[2,3,19],[8,35],[1,900]];right=[[5,20],[1,12],[8,9],[2,100]]
    lv=enumerate_vectors(left);rv=enumerate_vectors(right)
    for t in [.5,.95]:
        possible=np.quantile(lv,t,axis=1,method='linear')[:,None]-np.quantile(rv,t,axis=1,method='linear')[None,:]
        lo,hi=contrast_envelope(np.min(lv,axis=0),np.max(lv,axis=0),np.min(rv,axis=0),np.max(rv,axis=0),t)
        assert np.isclose(lo,possible.min()) and np.isclose(hi,possible.max())
        checks.append({'check':'exhaustive_independent_candidate_assignments','quantile':t,'assignments':possible.size,'pass':True})
    # Equal input IDs constrain alternatives; unconstrained envelopes remain safe,
    # but their extreme need not be a consistent algorithm's attained result.
    pools=[[1,100],[2,90],[1,100]]
    unconstrained=enumerate_vectors(pools)
    consistent=np.array([[pools[0][a],pools[1][b],pools[2][a]] for a,b in itertools.product(range(2),repeat=2)])
    for t in [.5,.95]:
        assert np.quantile(consistent,t,axis=1).min()>=np.quantile(unconstrained,t,axis=1).min()-1e-10
        assert np.quantile(consistent,t,axis=1).max()<=np.quantile(unconstrained,t,axis=1).max()+1e-10
    checks.append({'check':'repeated_input_consistency_subset','pass':True})
    # All possible source/destination branch quantiles must fit the transfer bound.
    for ws,wd in [(10,20),(0,100),(70,7)]:
        ns=[1,10,30];nd=[1,20,90]
        values=[transfer(ws,s,wd,d)[1] for s,d in itertools.product(ns,nd)]
        b=transfer_bounds(ws,min(ns),max(ns),wd,min(nd),max(nd),'wcl')
        assert b[2]<=min(values)+1e-10 and b[3]>=max(values)-1e-10
    # If policy inputs coincide, every consistent rule necessarily transfers at 0.
    assert transfer_bounds(10,1,30,10,1,30,'wcl',True)[:4]==(0.,0.,0.,0.)
    checks.append({'check':'transfer_bounds_bruteforce_and_identical_inputs','pass':True})
    # Geometric perturbation of each reference, with predictions fixed, validates
    # the 2delta margin certificate on ordered quantiles (not paired-error median).
    rng=np.random.default_rng(16102026);max_ratio=0.
    for trial in range(100):
        y=rng.normal(size=(8,2))*20;p=rng.normal(size=(8,2))*30;q=rng.normal(size=(8,2))*40
        displacement=rng.normal(size=(8,2));displacement/=np.maximum(1,np.linalg.norm(displacement,axis=1))[:,None]
        delta=7.;yp=y+delta*displacement
        for t in [.5,.95]:
            old=np.quantile(np.linalg.norm(p-y,axis=1),t)-np.quantile(np.linalg.norm(q-y,axis=1),t)
            new=np.quantile(np.linalg.norm(p-yp,axis=1),t)-np.quantile(np.linalg.norm(q-yp,axis=1),t)
            assert abs(new-old)<=2*delta+1e-10;max_ratio=max(max_ratio,abs(new-old)/(2*delta))
    checks.append({'check':'fixed_prediction_reference_geometry_bound','trials':200,'maximum_bound_fraction':max_ratio,'pass':True})
    # A sign-straddling interval is unresolved, not a demonstrated reversal.
    assert bounds_sign(-2,5)=='unresolved';assert bounds_sign(0,0)=='numerical_tie'
    assert bounds_sign(2,5)=='positive';assert bounds_sign(-5,-2)=='negative'
    checks.append({'check':'unresolved_and_numerical_tie_distinguished','pass':True})
    writej(HERE/'results/ENVELOPE_TESTS.json',{'status':'PASS','checks':checks});print('PASS',len(checks),'checks')
if __name__=='__main__':run()
