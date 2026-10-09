#!/usr/bin/env python3
"""Small deterministic software tests, not the planned synthetic research grid."""
import importlib.util,sys,tempfile,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('raw_step2',ROOT/'src/reconstruct_and_score.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
vsp=importlib.util.spec_from_file_location('verify2',ROOT/'src/verify_raw_independently.py');v=importlib.util.module_from_spec(vsp);vsp.loader.exec_module(v)
class Tests(unittest.TestCase):
 def test_stable_raw_selection_and_sentinel(self):
  raw={'rssi':np.full((1,72),-200.),'valid':np.zeros((1,72),bool)}
  raw['rssi'][0,[1,4,13]]=[-80,-80,-70];raw['valid'][0,[1,4,13]]=True
  ids,rx=m.raw_selection(raw,np.array([0]),{'2':0,'5':0,'14':0},{'2':[0,0],'5':[1,0],'14':[0,1]})
  self.assertEqual(ids[0,:3].tolist(),[14,2,5]);self.assertTrue((ids[0,3:]==-1).all())
 def test_selection_does_not_depend_on_coordinate_value(self):
  raw={'rssi':np.full((1,72),-200.),'valid':np.zeros((1,72),bool)};raw['rssi'][0,:3]=[-70,-80,-90];raw['valid'][0,:3]=True
  a={'1':1,'2':3,'3':4};c={'1':[0,0],'2':[1,0],'3':[0,1]};d={'1':[5000,0],'2':[1,0],'3':[0,1]}
  self.assertTrue(np.array_equal(m.raw_selection(raw,np.array([0]),a,c)[0],m.raw_selection(raw,np.array([0]),a,d)[0]))
 def test_fit_recovers_constant_intercept(self):
  xy=np.column_stack([np.arange(12.),np.ones(12)]);c={'1':[0,0]};s=25.-47.*np.log10(np.linalg.norm(xy,axis=1)+1.)
  raw={'rssi':s[:,None],'valid':np.ones((12,1),bool),'xy':xy};a,count=m.fit_all(raw,np.arange(12),c)
  self.assertAlmostEqual(a['1'],25.,12);self.assertEqual(count['1'],12)
 def test_ten_reception_eligibility(self):
  raw={'rssi':np.full((9,1),-80.),'valid':np.ones((9,1),bool),'xy':np.zeros((9,2))}
  a,count=m.fit_all(raw,np.arange(9),{'1':[1,2]});self.assertEqual(a,{});self.assertEqual(count['1'],9)
 def test_shared_offset_cancels(self):
  ids=np.array([[1,2,3,-1]]);rx=np.array([[-70.,-80.,-90.,0.]])
  c={'1':[0,0],'2':[1,0],'3':[0,1]};a={'1':1.,'2':2.,'3':3.};t=np.array([[.2,.3]])
  x=m.score(ids,rx,c,a,t);y=m.score(ids,rx,c,{k:v+10 for k,v in a.items()},t)
  np.testing.assert_allclose(x['weights'],y['weights'],rtol=0,atol=1e-14);np.testing.assert_allclose(x['predictions'],y['predictions'],rtol=0,atol=1e-14)
 def test_populations_partition(self):
  h=np.array([True,True,False,False]);c=np.array([1,3,2,4]);p=m.populations(h,c)
  self.assertTrue(np.array_equal(p['eligible_min3']|p['ineligible_min3'],p['full']));self.assertFalse((p['eligible_min3']&p['ineligible_min3']).any())
  self.assertEqual(p['affected_eligible_min3'].sum(),1);self.assertEqual(p['affected_ineligible_min3'].sum(),1)
 def test_numerical_ties_not_practical_thresholds(self):
  a=np.array([1.,2.,3.]);b=np.array([1.+1e-8,1.,4.]);d=m.proportions(a,b)
  self.assertEqual([d[k] for k in ['right_help_n','right_harm_n','numeric_tie_n']],[1,1,1])
 def test_manual_quantile(self):
  for a in [[3,1,9,4],[0,0,0,8,8],[1],[2,2]]:
   for q in [0,.5,.9,.95,1]:self.assertAlmostEqual(v.quantile(a,q),float(np.quantile(a,q)),12)
 def test_empty_stat_rejected(self):
  with self.assertRaises(ValueError):m.stats([])
 def test_movement_identity_and_bound(self):
  x=np.array([[0.,0.],[10.,10.]]);f=np.array([[2.,0.],[8.,9.]]);r=np.array([[1.,0.],[12.,10.]]);u=np.array([[.5,.5],[10.,12.]])
  ef=np.linalg.norm(f-x,axis=1);er=np.linalg.norm(r-x,axis=1);eu=np.linalg.norm(u-x,axis=1);d=r-f
  np.testing.assert_allclose(er**2-ef**2,2*np.sum((f-x)*d,axis=1)+np.sum(d*d,axis=1),atol=1e-12)
  self.assertTrue((np.abs(er-eu)<=np.linalg.norm(r-u,axis=1)+1e-12).all())
 def test_deterministic_npz(self):
  with tempfile.TemporaryDirectory() as s:
   a=Path(s)/'a.npz';b=Path(s)/'b.npz';m.npz_out(a,thing=np.arange(8));m.npz_out(b,thing=np.arange(8));self.assertEqual(m.digest(a),m.digest(b))
 def test_nonfinite_score_rejected(self):
  with self.assertRaises(ValueError):m.close(np.array([np.nan]),np.array([np.nan]),'nonfinite')
if __name__=='__main__':unittest.main(verbosity=2)
