"""Descriptive consequences; all distances in metres, losses in dB squared."""
from pathlib import Path
import csv, hashlib, json
import numpy as np

HERE = Path(__file__).resolve().parents[1]
ORIGINAL = HERE.parents[1] / 'paperb_execution_20261015'
LEVELS = [('p50', .5), ('p95', .95)]
METHODS = ['wcl', 'nlls']
POLICIES = ['frozen', 'refit']

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def readz(path):
    with np.load(path, allow_pickle=False) as z: return {k:z[k] for k in z.files}
def native(x):
    if isinstance(x, dict): return {str(k):native(v) for k,v in x.items()}
    if isinstance(x, (list, tuple)): return [native(v) for v in x]
    if isinstance(x, np.ndarray): return native(x.tolist())
    if isinstance(x, np.generic): return native(x.item())
    if isinstance(x, float) and not np.isfinite(x): return None
    return x
def writej(path, x):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(native(x),indent=2,allow_nan=False)+'\n')
def writecsv(path, rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(native(rows))
def quantile(x,t): return float(np.quantile(x,t,method='linear')) if len(x) else None
def norm(x): return np.linalg.norm(x,axis=-1)
def tol(a,b): return 1e-6+1e-12*max(abs(a),abs(b))
def sign(a,b):
    if a is None or b is None: return 'unavailable'
    return 'positive' if a-b>tol(a,b) else 'negative' if a-b < -tol(a,b) else 'numerical_tie'
def bounds_sign(lo,hi):
    if lo is None or hi is None: return 'unavailable'
    eps=1e-6+1e-12*max(abs(lo),abs(hi))
    if lo>eps:return 'positive'
    if hi< -eps:return 'negative'
    if lo>=-eps and hi<=eps:return 'numerical_tie'
    return 'unresolved'
def winner(a,b): return 'wcl' if a<=b else 'nlls'
def rank_category(w,n): return {'positive':'nlls_lower','negative':'wcl_lower','numerical_tie':'numerical_tie','unavailable':'not_estimable'}[sign(w,n)]
def strict_reversal(a,b): return {a,b}=={'wcl_lower','nlls_lower'}
def contrast_envelope(left_min,left_max,right_min,right_max,t):
    return quantile(left_min,t)-quantile(right_max,t),quantile(left_max,t)-quantile(right_min,t)
def reference_boundary(margin): return abs(margin)/2 if margin is not None else None
def transfer(w_source,n_source,w_destination,n_destination):
    selected=winner(w_source,n_source)
    chosen=w_destination if selected=='wcl' else n_destination
    return selected, chosen-min(w_destination,n_destination)
def transfer_bounds(w_source,n_source_lo,n_source_hi,w_dest,n_dest_lo,n_dest_hi,primary_choice,same_states=False):
    if same_states:return (0.,0.,0.,0.,'wcl,nlls' if n_source_lo<=w_source<=n_source_hi else ('wcl' if w_source<n_source_lo else 'nlls'))
    choices=[]
    if w_source<=n_source_hi: choices.append('wcl')
    if n_source_lo<w_source: choices.append('nlls')
    def one(choice):
        if choice=='wcl':return max(0.,w_dest-n_dest_hi),max(0.,w_dest-n_dest_lo)
        return max(0.,n_dest_lo-w_dest),max(0.,n_dest_hi-w_dest)
    fixed=one(primary_choice); intervals=[one(c) for c in choices]
    return fixed+(min(v[0] for v in intervals),max(v[1] for v in intervals),','.join(choices))
def block_files(): return sorted((ORIGINAL/'inputs/blocks').glob('*.npz'))
def verify_source():
    receipt=ORIGINAL/'receipts/PRIMARY_RUN_RECEIPT.json';r=json.loads(receipt.read_text())
    if r['status']!='COMPLETE':raise ValueError('Incomplete original execution')
    lock=ORIGINAL/'protocol/EXECUTION_LOCK.json'
    if sha(lock)!=r['lock_sha256']:raise ValueError('Original lock changed')
    for p in block_files():
        out=ORIGINAL/'results/arrays'/p.name
        if sha(out)!=r['output_arrays'][p.name]:raise ValueError('Original output changed '+p.name)
    return {'primary_receipt_sha256':sha(receipt),'original_lock_sha256':sha(lock),'blocks':len(block_files())}
def load_block(path):
    b=readz(path);r=readz(ORIGINAL/'results/arrays'/path.name);m=json.loads(path.with_suffix('.json').read_text())
    if not np.array_equal(b['source_rows'],r['source_rows']):raise ValueError('Row alignment')
    if not np.array_equal(r['query_indices'],np.arange(len(b['source_rows']))):raise ValueError('Query order')
    for key in ['field_D_m','field_draw','field_target_count']:
        if not np.array_equal(b[key],r[key]):raise ValueError('Field alignment '+key)
    e={k:norm(r[k+'_position_m']-b['query_xy_m'][None,None]) for k in METHODS}
    f={k:np.isfinite(r[k+'_position_m']).all(axis=-1) for k in METHODS}
    return b,r,m,e,f
def fields(path,b,m):
    for fi in range(len(b['field_D_m'])):
        targets=np.flatnonzero(b['field_target_mask'][fi])+1
        ids=b['selected_ids'];mask=b['selected_mask']
        exposure=np.sum(b['field_target_mask'][fi][np.maximum(ids-1,0)]&mask,axis=1)
        ident={'block':path.stem,**m['identity'],'field_index':fi,'D_m':float(b['field_D_m'][fi]),'draw':int(b['field_draw'][fi]),'target_ids':','.join(map(str,targets)),'target_count':len(targets)}
        pops=[('full_sample',np.ones(len(ids),bool))]
        if b['field_D_m'][fi]>0:pops.append(('selected_target_affected',exposure>0))
        for pop,mask in pops:yield fi,{**ident,'population':pop,'scheduled_n':int(mask.sum())},mask
