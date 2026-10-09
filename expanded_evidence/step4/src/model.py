"""Step-4 WCL kernels. Positions in metres; selected slots are explicit and fixed.
No automatic exclusion, replacement receiver, tuning, or missing-value omission.
"""
from __future__ import annotations
import hashlib, io, json, zipfile
from pathlib import Path
from typing import Any
import numpy as np
ATOL=1e-6
RTOL=1e-12
WTOL=1e-12
POLICIES=('frozen','unrestricted','shared_update','bounded10','bounded30')
KAPPAS=(0.5,1.,2.,4.7)

def need(ok: bool,msg: str):
    if not ok: raise ValueError(msg)

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def js(path: Path,obj: Any):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')

def npz(path: Path,**arrays):
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for k in sorted(arrays):
            a=np.asarray(arrays[k]);need(a.dtype.kind!='O','Object array prohibited')
            s=io.BytesIO();np.lib.format.write_array(s,a,allow_pickle=False)
            zi=zipfile.ZipInfo(k+'.npy',(1980,1,1,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o600<<16
            z.writestr(zi,s.getvalue())

def policies(a0: np.ndarray,af: np.ndarray) -> np.ndarray:
    change=af-a0
    return np.stack([a0,af,a0+np.median(change),a0+np.clip(change,-10,10),a0+np.clip(change,-30,30)])

def weights(rx: np.ndarray,intercepts: np.ndarray,kappa: float,n: float=4.7,valid: np.ndarray|None=None) -> np.ndarray:
    """rx Q,S, intercepts S or Q,S; zero padding only, all selected weights positive."""
    need(n>0 and kappa>0,'Positive exponents required')
    if valid is None:valid=np.ones_like(rx,dtype=bool)
    need(np.all(valid.sum(axis=-1)>0),'No selected receiver')
    logw=np.where(valid,(np.log(10)*kappa/(10*n))*(rx-intercepts),-np.inf)
    v=np.exp(logw-np.max(logw,axis=-1,keepdims=True));p=v/v.sum(axis=-1,keepdims=True)
    need(np.all(np.isfinite(p)) and np.all(p[valid]>0),'Nonfinite or underflowed selected weight')
    need(np.max(np.abs(p.sum(axis=-1)-1))<WTOL,'Normalization')
    return p

def centroid(p: np.ndarray,xy: np.ndarray) -> np.ndarray:
    """Coordinates Q,S,2 or S,2. Summation about a local origin reduces cancellation."""
    if xy.ndim==2:
        o=xy.mean(axis=0)
        return p@(xy-o)+o
    # First selected slot is valid by contract; padding coordinates have zero weight.
    o=xy[:,0,:]
    return np.sum(p[:,:,None]*(xy-o[:,None,:]),axis=1)+o

def fit(rx: np.ndarray,calxy: np.ndarray,axy: np.ndarray,n: float=4.7) -> np.ndarray:
    ds=np.linalg.norm(calxy[:,None,:]-axy[None,:,:],axis=2)
    out=np.median(rx+10*n*np.log10(ds+1.),axis=0)
    need(np.isfinite(out).all(),'Bad fit')
    return out

def removal(p: np.ndarray,xy: np.ndarray,targetslots: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    u=np.where(targetslots,0.,p);mass=u.sum(axis=1);defined=mass>0
    pred=np.full((len(p),2),np.nan)
    if defined.any():pred[defined]=centroid(u[defined]/mass[defined,None],xy if xy.ndim==2 else xy[defined])
    return pred,defined

def metrics(errors: np.ndarray,reference: np.ndarray) -> dict:
    need(len(errors)>0 and np.isfinite(errors).all(),'Metric denominator/nonfinite')
    q=np.quantile(errors,[.5,.9,.95],method='linear')
    rq=np.quantile(reference,[.5,.9,.95],method='linear')
    eps=ATOL+RTOL*np.maximum(np.abs(reference),np.abs(errors));d=reference-errors
    return {'n':len(errors),'p50_m':float(q[0]),'p90_m':float(q[1]),'p95_m':float(q[2]),'mean_m':float(errors.mean()),'max_m':float(errors.max()),'p50_change_pct':float(100*(q[0]/rq[0]-1)) if rq[0]>0 else None,'help_n_vs_reference':int(np.sum(d>eps)),'harm_n_vs_reference':int(np.sum(d< -eps)),'tie_n_vs_reference':int(np.sum(np.abs(d)<=eps))}

def compare_errors(left: np.ndarray,right: np.ndarray) -> dict:
    eps=ATOL+RTOL*np.maximum(np.abs(left),np.abs(right));d=left-right
    ql=np.quantile(left,[.5,.9,.95],method='linear');qr=np.quantile(right,[.5,.9,.95],method='linear')
    return {'p50_benefit_m':float(ql[0]-qr[0]),'p90_benefit_m':float(ql[1]-qr[1]),'p95_benefit_m':float(ql[2]-qr[2]),'right_help_n':int(np.sum(d>eps)),'right_harm_n':int(np.sum(d< -eps)),'numeric_tie_n':int(np.sum(np.abs(d)<=eps)),'median_message_benefit_m':float(np.median(d))}

def check_close(a,b,label,atol=ATOL,rtol=RTOL):
    a=np.asarray(a);b=np.asarray(b);need(a.shape==b.shape,label+' shape')
    need(np.isfinite(a).all() and np.isfinite(b).all(),label+' nonfinite')
    err=np.abs(a-b);maximum=float(err.max()) if err.size else 0.;need(np.all(err<=atol+rtol*np.maximum(np.abs(a),np.abs(b))),label+f' mismatch {maximum}')
    return float(err.max()) if err.size else 0.
