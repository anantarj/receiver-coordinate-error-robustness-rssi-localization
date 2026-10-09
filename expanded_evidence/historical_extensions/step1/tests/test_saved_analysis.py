"""Small numerical unit tests; not new localization study results."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from analyze_saved_pairs import removal,help_harm,stats,close

class Tests(unittest.TestCase):
    def setUp(self):
        self.xy=np.array([[[0.,0.],[2.,0.],[0.,4.]]])
        self.w=np.array([[.2,.3,.5]])
    def test_fixed_selection_removal(self):
        p,ok=removal(self.w,self.xy,np.array([[True,False,False]]))
        self.assertTrue(ok[0]);np.testing.assert_allclose(p,[[.75,2.5]])
    def test_empty_targets(self):
        p,ok=removal(self.w,self.xy,np.zeros((1,3),bool))
        np.testing.assert_allclose(p,[[.6,2.]]);self.assertTrue(ok[0])
    def test_all_targets_undefined(self):
        p,ok=removal(self.w,self.xy,np.ones((1,3),bool))
        self.assertFalse(ok[0]);self.assertTrue(np.isnan(p).all())
    def test_one_survivor(self):
        p,ok=removal(self.w,self.xy,np.array([[True,True,False]]))
        np.testing.assert_allclose(p,[[0,4]]);self.assertTrue(ok[0])
    def test_finite_identity(self):
        t=np.array([[True,False,False]])
        w=self.w*np.array([[.001,1,1]]);w/=w.sum(axis=1,keepdims=True)
        u,ok=removal(self.w,self.xy,t)
        p=np.einsum('qi,qij->qj',w,self.xy)
        rhs=np.einsum('qi,qij->qj',w*t,self.xy-u[:,None,:])
        np.testing.assert_allclose(p-u,rhs,atol=1e-15)
    def test_numerical_ties(self):
        hp,hm,t=help_harm(np.array([2.,2.,2.]),np.array([1.,3.,2.+1e-8]))
        self.assertEqual(hp.tolist(),[True,False,False]);self.assertEqual(hm.tolist(),[False,True,False]);self.assertEqual(t.tolist(),[False,False,True])
    def test_linear_quantile(self):
        self.assertEqual(stats([0,1,2,3])['q25'],.75)
    def test_pair_aggregation_not_commuted(self):
        a=np.array([0.,100.,101.]);b=np.array([0.,1.,101.])
        self.assertNotEqual(np.median(a)-np.median(b),np.median(a-b))
    def test_bad_identity_fails(self):
        with self.assertRaises(ValueError):close([1.],[2.],'bad')

if __name__=='__main__':unittest.main(verbosity=2)
