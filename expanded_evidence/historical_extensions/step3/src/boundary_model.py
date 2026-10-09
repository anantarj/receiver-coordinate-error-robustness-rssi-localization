"""Canonical positive-weight WCL and independently specified calibration policies.
All positions are metres. Selection is an explicit immutable input.
"""
from __future__ import annotations
import numpy as np

def distances(x: np.ndarray, a: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.asarray(x,dtype=np.float64)[:,None,:]-np.asarray(a,dtype=np.float64)[None,:,:],axis=2)

def fit_intercepts(raw: np.ndarray, x: np.ndarray, a: np.ndarray, n: float, d0: float) -> np.ndarray:
    if n<=0 or d0<=0: raise ValueError('Positive n and d0 required.')
    y=np.asarray(raw,dtype=np.float64)+10*n*np.log10((distances(x,a)+d0)/d0)
    if not np.isfinite(y).all(): raise ValueError('Nonfinite calibration values.')
    return np.median(y,axis=0)

def normalize_log_weights(raw: np.ndarray, intercepts: np.ndarray, n: float, kappa: float) -> np.ndarray:
    if n<=0 or kappa<=0: raise ValueError('Positive exponents required.')
    logw=(np.log(10)*kappa/(10*n))*(np.asarray(raw,dtype=np.float64)-intercepts)
    if not np.isfinite(logw).all(): raise ValueError('Nonfinite log weight.')
    exp=np.exp(logw-np.max(logw,axis=1,keepdims=True))
    p=exp/exp.sum(axis=1,keepdims=True)
    if not np.isfinite(p).all() or np.any(p<=0): raise ValueError('Nonfinite or underflowed selected weight.')
    return p

def policy_intercepts(name: str, a0: np.ndarray, fitted: np.ndarray) -> np.ndarray:
    change=fitted-a0
    if name=='frozen': return a0.copy()
    if name=='unrestricted': return fitted.copy()
    if name=='shared_update': return a0+np.median(change)
    if name in ['bounded10','bounded30']:
        B=float(name.replace('bounded',''))
        return a0+np.clip(change,-B,B)
    raise ValueError(f'Unknown policy: {name}')

def shifted_centroid(p: np.ndarray, a: np.ndarray, origin: np.ndarray | None=None) -> np.ndarray:
    """Translation-centered summation; checks use a separate scalar implementation."""
    if origin is None: origin=np.mean(a,axis=0)
    return (p@(a-origin))+origin
