"""Small numerical tests; these do not replace the locked C1 research controls."""
import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from boundary_model import distances, fit_intercepts, normalize_log_weights, policy_intercepts, shifted_centroid

class BoundaryModelTests(unittest.TestCase):
    def setUp(self):
        self.a=np.array([[-3.,-1.],[2.,-2.],[1.,4.]])
        self.cal=np.array([[0.,0.],[1.,1.],[-1.,0.],[.5,-.7],[-2.,1.]])
        self.a0=np.array([-30.,-31.,-29.]); self.n=4.7; self.d0=1.
        self.raw=self.a0-10*self.n*np.log10(distances(self.cal,self.a)+1)
    def test_noiseless_reference_intercepts(self):
        np.testing.assert_allclose(fit_intercepts(self.raw,self.cal,self.a,self.n,1.),self.a0,atol=1e-12,rtol=0)
    def test_invalid_exponents(self):
        for n,k in [(0,1),(1,0),(-1,1),(1,-1)]:
            with self.assertRaises(ValueError):normalize_log_weights(self.raw,self.a0,n,k)
    def test_nonfinite_input_rejected(self):
        x=self.raw.copy();x[0,0]=np.nan
        with self.assertRaises(ValueError):normalize_log_weights(x,self.a0,self.n,1.)
    def test_reference_policies_coincide(self):
        for name in ['frozen','unrestricted','shared_update','bounded10','bounded30']:
            np.testing.assert_array_equal(policy_intercepts(name,self.a0,self.a0),self.a0)
    def test_shared_update_cancels(self):
        for k in [.5,1.,2.,4.7]:
            p=normalize_log_weights(self.raw,self.a0,self.n,k)
            pp=normalize_log_weights(self.raw,self.a0+37.5,self.n,k)
            np.testing.assert_allclose(p,pp,atol=2e-15,rtol=2e-14)
    def test_hard_limits(self):
        fit=self.a0+np.array([100.,-100.,3.])
        np.testing.assert_array_equal(policy_intercepts('bounded10',self.a0,fit)-self.a0,[10,-10,3])
        np.testing.assert_array_equal(policy_intercepts('bounded30',self.a0,fit)-self.a0,[30,-30,3])
    def test_policy_does_not_mutate(self):
        original=self.a0.copy();fit=self.a0+np.array([40.,2.,-8.]);oldfit=fit.copy()
        for name in ['frozen','unrestricted','shared_update','bounded10','bounded30']:
            policy_intercepts(name,self.a0,fit)
        np.testing.assert_array_equal(self.a0,original);np.testing.assert_array_equal(fit,oldfit)
    def test_unknown_policy_rejected(self):
        with self.assertRaises(ValueError):policy_intercepts('invented',self.a0,self.a0)
    def test_finite_mass_and_prediction_identity(self):
        p0=np.array([.8,.15,.05]);z=np.array([.002,1.,1.]);p=p0*z/(p0@z)
        u=shifted_centroid(np.array([[.75,.25]]),self.a[1:])[0]
        x=shifted_centroid(p[None,:],self.a)[0]
        np.testing.assert_allclose(x-u,p[0]*(self.a[0]-u),atol=1e-14,rtol=1e-14)
        self.assertAlmostEqual(p[0],p0[0]*z[0]/(.2+p0[0]*z[0]),places=14)
    def test_small_remaining_mass_prevents_small_target_mass(self):
        p=.999999;z=.001;b=p*z/(1-p+p*z)
        self.assertGreater(b,.99)
    def test_symmetric_cancellation(self):
        a=np.array([[-1e8,0],[1e8,0],[0,1],[0,-1]])
        p=np.array([[.4,.4,.1,.1]])
        # Use the already locked coordinate-scale tolerance, not a fixed 1e-12 m at 1e8 m.
        tol=1e-7+2e-12*float(np.max(np.abs(a)))
        np.testing.assert_allclose(shifted_centroid(p,a),[[0.,0.]],atol=tol,rtol=0)
    def test_single_target_tolerance_condition(self):
        # Algebraic requirement on one selected target, not an operational choice.
        p=.3; ell=100.;eps=2.;crit=eps*(1-p)/(p*(ell-eps))
        for z in [crit/2,crit,crit*2]:
            b=p*z/(1-p+p*z);I=b*ell
            self.assertEqual(I<=eps+1e-12,z<=crit+1e-12)
    def test_reverse_triangle(self):
        target=np.array([5.,1.]);u=np.array([.5,-1]);truth=np.array([1.5,2.]);b=.2
        x=u+b*(target-u)
        self.assertLessEqual(abs(np.linalg.norm(x-truth)-np.linalg.norm(u-truth)),np.linalg.norm(x-u)+1e-14)
    def test_log_normalization_extreme_offset(self):
        s=np.array([[-1e4,-1e4-1,-1e4-3]])
        p=normalize_log_weights(s,np.zeros(3),self.n,self.n)
        expected=10**np.array([0.,-.1,-.3]);expected/=expected.sum()
        np.testing.assert_allclose(p[0],expected,atol=2e-13,rtol=2e-12)

if __name__=='__main__':unittest.main()
