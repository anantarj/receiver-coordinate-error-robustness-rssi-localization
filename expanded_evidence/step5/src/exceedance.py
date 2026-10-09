"""Exact finite-empirical error exceedance calculations, with explicit availability.
The curves are conditional descriptions of retained messages, not population CIs.
No estimate counts as failure at every finite threshold. Numerical ties may be
canonicalized for pair comparisons only; stored original errors remain unchanged.
"""
from __future__ import annotations
import numpy as np
ATOL=1e-6;RTOL=1e-12

def curve(left,right,left_available=None,right_available=None,canonicalize=True):
 l=np.asarray(left,float);r=np.array(right,float,copy=True)
 if l.ndim!=1 or l.shape!=r.shape or not l.size:raise ValueError('Nonempty equal one-dimensional populations required')
 if not(np.isfinite(l).all() and np.isfinite(r).all() and (l>=0).all() and (r>=0).all()):raise ValueError('Nonnegative finite error scores required')
 n=len(l);la=np.ones(n,bool) if left_available is None else np.asarray(left_available,bool)
 ra=np.ones(n,bool) if right_available is None else np.asarray(right_available,bool)
 if la.shape!=l.shape or ra.shape!=l.shape:raise ValueError('Availability shape')
 eq=(np.abs(l-r)<=ATOL+RTOL*np.maximum(l,r))&la&ra
 snap=(eq & (l!=r)) if canonicalize else np.zeros(n,bool)
 maxsnap=float(np.max(np.abs(l[snap]-r[snap]))) if snap.any() else 0.
 if canonicalize:r[eq]=l[eq]
 a=l[la];b=r[ra]
 v=np.concatenate(([0.],a,b));t,inv=np.unique(v,return_inverse=True)
 inc_l=np.bincount(inv[1:1+len(a)],minlength=len(t)).astype(np.int64)
 inc_r=np.bincount(inv[1+len(a):],minlength=len(t)).astype(np.int64)
 sl=np.cumsum(inc_l);sr=np.cumsum(inc_r);diff=sr-sl # exceedance_left minus exceedance_right
 widths=np.diff(t);positive=np.maximum(diff[:-1],0)/n;negative=np.maximum(-diff[:-1],0)/n
 area_p=float(np.dot(positive,widths));area_n=float(np.dot(negative,widths))
 lo=int(diff.min());hi=int(diff.max())
 category='equal' if lo==hi==0 else ('crossing' if lo<0<hi else ('right_no_worse' if lo>=0 else 'left_no_worse'))
 signs=np.sign(diff[diff!=0]);trans=int(np.sum(signs[1:]!=signs[:-1])) if len(signs)>1 else 0
 meanbenefit=float(np.mean(l-r)) if la.all() and ra.all() else None
 residual=abs((area_p-area_n)-meanbenefit) if meanbenefit is not None else None
 if residual is not None and residual>1e-6+1e-12*max(abs(meanbenefit),area_p,area_n):raise ValueError('Exceedance integral identity')
 return {'threshold_m':t,'left_exceedance_count':n-sl,'right_exceedance_count':n-sr,'benefit_count':diff}, {'n':n,'left_available_n':int(la.sum()),'right_available_n':int(ra.sum()),'curve_order':category,'max_benefit_count':hi,'max_harm_count':-lo,'max_benefit_fraction':hi/n,'max_harm_fraction':-lo/n,'positive_interval_length_m':float(widths[diff[:-1]>0].sum()),'negative_interval_length_m':float(widths[diff[:-1]<0].sum()),'positive_area_m':area_p,'negative_area_m':area_n,'finite_area_net_m':area_p-area_n,'max_finite_threshold_m':float(t[-1]),'terminal_benefit_fraction':float(diff[-1]/n),'nonzero_sign_changes':trans,'event_count':len(t),'canonicalized_pair_count':int(snap.sum()),'max_canonicalization_m':maxsnap,'mean_benefit_m_if_all_available':meanbenefit,'integral_identity_residual_m':residual}

def thresholds_at(errors,thresholds,available=None):
 e=np.asarray(errors,float);a=np.ones(len(e),bool) if available is None else np.asarray(available,bool)
 if e.ndim!=1 or a.shape!=e.shape or not len(e):raise ValueError('Population')
 return 1-np.searchsorted(np.sort(e[a]),np.asarray(thresholds,float),side='right')/len(e)
