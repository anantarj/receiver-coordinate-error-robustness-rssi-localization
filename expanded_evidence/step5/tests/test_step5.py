import unittest,sys,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'vendor/step4'))
from exceedance import curve,thresholds_at
from model import weights,centroid,removal,policies
class TestCurves(unittest.TestCase):
 def test_equal(self):
  _,s=curve([1,2],[1,2]);self.assertEqual(s['curve_order'],'equal')
 def test_right_dominant(self):
  _,s=curve([4,5],[1,2]);self.assertEqual(s['curve_order'],'right_no_worse');self.assertAlmostEqual(s['finite_area_net_m'],3.)
 def test_left_dominant(self):
  _,s=curve([1,2],[4,5]);self.assertEqual(s['curve_order'],'left_no_worse');self.assertAlmostEqual(s['finite_area_net_m'],-3.)
 def test_crossing(self):
  _,s=curve([1,10],[2,8]);self.assertEqual(s['curve_order'],'crossing');self.assertAlmostEqual(s['positive_area_m'],1.);self.assertAlmostEqual(s['negative_area_m'],.5)
 def test_availability_tail(self):
  d,s=curve([3,10],[1,2],right_available=[True,False]);self.assertEqual(s['curve_order'],'crossing');self.assertEqual(s['terminal_benefit_fraction'],-.5);self.assertIsNone(s['mean_benefit_m_if_all_available'])
 def test_all_unavailable(self):
  _,s=curve([3,10],[1,2],right_available=[False,False]);self.assertEqual(s['curve_order'],'left_no_worse');self.assertEqual(s['right_available_n'],0)
 def test_pair_roundoff(self):
  d,s=curve([1.,2.],[1.+5e-7,2.]);self.assertEqual(s['curve_order'],'equal');self.assertEqual(s['canonicalized_pair_count'],1)
 def test_zero_breakpoint(self):
  d,_=curve([0.,1.],[0.,1.]);self.assertEqual(d['left_exceedance_count'][0],1)
 def test_direct_thresholds(self):
  e=np.array([1,1,2,10.]);t=np.array([0.,1.,1.5,2.,10.,11.]);p=thresholds_at(e,t)
  np.testing.assert_array_equal(p,np.array([(e>x).mean() for x in t]))
 def test_random_exact_ranks(self):
  rng=np.random.default_rng(3912)
  for _ in range(20):
   l=rng.integers(0,50,41).astype(float);r=rng.integers(0,50,41).astype(float);la=rng.random(41)>.2;ra=rng.random(41)>.3;d,s=curve(l,r,la,ra)
   for i,t in enumerate(d['threshold_m']):
    self.assertEqual(d['left_exceedance_count'][i],int(np.sum((~la)|(l>t))))
    self.assertEqual(d['right_exceedance_count'][i],int(np.sum((~ra)|(r>t))))
 def test_invalid_scores(self):
  with self.assertRaises(ValueError):curve([1,float('nan')],[2,3])
  with self.assertRaises(ValueError):curve([],[])
  with self.assertRaises(ValueError):curve([-1],[1])
class TestModel(unittest.TestCase):
 def test_nonzero_common_update(self):
  x=np.array([[-50.,-62.,-57.]]);a=np.array([-25.,-26.,-29.])
  np.testing.assert_allclose(weights(x,a,4.7),weights(x,a+7.5,4.7),atol=1e-14)
 def test_fixed_caps(self):
  a=np.array([-30.,-32.,-31.]);af=a+np.array([40.,-45.,0.]);p=policies(a,af)
  np.testing.assert_array_equal(p[3]-a,[10.,-10.,0.]);np.testing.assert_array_equal(p[4]-a,[30.,-30.,0.])
 def test_zero_update(self):
  a=np.array([-30.,-32.]);np.testing.assert_array_equal(policies(a,a),np.repeat(a[None,:],5,axis=0))
 def test_removal_no_refill(self):
  p=np.array([[.5,.3,.2]]);xy=np.array([[10.,0.],[0.,10.],[0.,0.]])
  u,d=removal(p,xy,np.array([[True,False,False]]));np.testing.assert_allclose(u,[[0.,6.]]);self.assertTrue(d[0])
 def test_removal_undefined(self):
  u,d=removal(np.array([[.5,.5]]),np.array([[1.,0.],[0.,1.]]),np.array([[True,True]]));self.assertFalse(d[0]);self.assertTrue(np.isnan(u).all())
 def test_removal_identity(self):
  p=np.array([[.2,.3,.5]]);xy=np.array([[10.,0.],[0.,10.],[3.,4.]]);tm=np.array([[True,False,False]]);u,d=removal(p,xy,tm)
  np.testing.assert_allclose(centroid(p,xy)-u,.2*(xy[0]-u),atol=1e-12)
class TestLocks(unittest.TestCase):
 def test_locked_registries(self):
  for stem in ['D3','EXCEEDANCE']:
   lock=json.loads((ROOT/'protocol'/f'{stem}_LOCK.json').read_text());h=hashlib.sha256((ROOT/'protocol'/f'{stem}_REGISTRY.json').read_bytes()).hexdigest();self.assertEqual(h,lock['registry_sha256'])
 def test_selected_training_ranks(self):
  r=json.loads((ROOT/'protocol/D3_REGISTRY.json').read_text());self.assertEqual(len(r['target_receivers']),6);self.assertEqual(len(set(r['target_receivers'])),6)
  for x in r['target_records']:
   self.assertGreaterEqual(x['calibration_receptions'],10);m=x['stratum_size'];self.assertIn(x['within_stratum_index_zero'],[(m-1)//3,2*(m-1)//3])
if __name__=='__main__':unittest.main()
