import unittest,tempfile,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from model import *

class ModelTests(unittest.TestCase):
 def setUp(self):
  self.a=np.array([[-100,20],[400,-30],[10,300],[300,250]],float)
  self.x=np.array([[0,0],[70,80],[100,-40]],float)
  self.a0=np.array([-30,-32,-34,-29.])
  self.rx=self.a0-47*np.log10(np.linalg.norm(self.x[:,None,:]-self.a[None,:,:],axis=2)+1)
 def test_reference_fit(self):np.testing.assert_allclose(fit(self.rx,self.x,self.a),self.a0,atol=1e-12)
 def test_empty_equal(self):self.assertEqual(check_close([],[],'empty'),0.)
 def test_zero_policies(self):np.testing.assert_array_equal(policies(self.a0,self.a0),np.tile(self.a0,(5,1)))
 def test_shared_cancels(self):
  for k in KAPPAS:
   for c in [-100,0,100]:np.testing.assert_allclose(weights(self.rx,self.a0,k),weights(self.rx,self.a0+c,k),atol=1e-13)
 def test_bounds(self):
  a=policies(self.a0,self.a0+np.array([-50,-5,20,80]));self.assertLessEqual(np.max(np.abs(a[3]-self.a0)),10);self.assertLessEqual(np.max(np.abs(a[4]-self.a0)),30)
 def test_padding(self):
  r=np.c_[self.rx,np.ones(3)*999];v=np.ones_like(r,bool);v[:,-1]=False;p=weights(r,np.r_[self.a0,0],4.7,valid=v);np.testing.assert_allclose(p[:,:4],weights(self.rx,self.a0,4.7));self.assertTrue(np.all(p[:,-1]==0))
 def test_translation(self):
  p=weights(self.rx,self.a0,1.);np.testing.assert_allclose(centroid(p,self.a)+[200,-500],centroid(p,self.a+[200,-500]),atol=1e-10)
 def test_direct_centroid(self):
  p=weights(self.rx,self.a0,4.7);np.testing.assert_allclose(centroid(p,self.a),p@self.a,atol=1e-12)
 def test_removal_no_refill(self):
  p=weights(self.rx,self.a0,4.7);m=np.zeros_like(p,bool);m[:,0]=True;u,d=removal(p,self.a,m);q=p.copy();q[:,0]=0;q/=q.sum(axis=1,keepdims=True);np.testing.assert_allclose(u,q@self.a,atol=1e-12);self.assertTrue(d.all())
 def test_removal_undefined(self):
  p=weights(self.rx,self.a0,1.);u,d=removal(p,self.a,np.ones_like(p,bool));self.assertTrue(np.isnan(u).all());self.assertFalse(d.any())
 def test_finite_identity(self):
  p=weights(self.rx,self.a0,1.);m=np.zeros_like(p,bool);m[:,0]=True;u,_=removal(p,self.a,m);af=self.a0.copy();af[0]+=20;axy=self.a.copy();axy[0]+=[2000,400];pp=weights(self.rx,af,1.);pred=centroid(pp,axy);np.testing.assert_allclose(pred-u,pp[:,0,None]*(axy[0]-u),atol=1e-10)
 def test_error_bound(self):
  p=weights(self.rx,self.a0,1.);u,_=removal(p,self.a,np.array([[True,False,False,False]]*3));pred=centroid(p,self.a);err=np.linalg.norm(pred-self.x,axis=1);eu=np.linalg.norm(u-self.x,axis=1);self.assertTrue(np.all(np.abs(err-eu)<=np.linalg.norm(pred-u,axis=1)+1e-10))
 def test_same_inputs_are_numerical_ties(self):
  a=np.array([1,2,3]);c=compare_errors(a,a);self.assertEqual(c['numeric_tie_n'],3);self.assertEqual(c['p50_benefit_m'],0.)
 def test_different_medians(self):
  left=np.array([0,100,101.]);right=np.array([0,1,100.]);c=compare_errors(left,right);self.assertNotEqual(c['p50_benefit_m'],c['median_message_benefit_m'])
 def test_no_implicit_precision(self):self.assertIsNone(metrics(np.array([0.,1,2]),np.zeros(3))['p50_change_pct'])
 def test_invalid_kappa(self):
  with self.assertRaises(ValueError):weights(self.rx,self.a0,0)
 def test_serialization(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.npz';q=Path(t)/'b.npz';npz(p,b=np.arange(4.),a=np.array(['x','y']));npz(q,a=np.array(['x','y']),b=np.arange(4.));self.assertEqual(sha(p),sha(q))
if __name__=='__main__':unittest.main(verbosity=2)
