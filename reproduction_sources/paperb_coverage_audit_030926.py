#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, os, random, sys
from collections import Counter
from pathlib import Path

def mkey(m):
    return (round(float(m.x),3), round(float(m.y),3),
            tuple(sorted((rx.gid, round(float(rx.rssi),3)) for rx in m.receptions)))

def selected_sets(msgs, roster, w):
    roster=set(roster); out=[]
    for mm in msgs:
        rx=[r for r in mm.receptions if r.gid in roster]
        if len(rx)<3: continue
        rx=sorted(rx,key=lambda r:-float(r.rssi))[:w]
        out.append(tuple(r.gid for r in rx))
    return out

def coverage(ss,kmax):
    cnt=Counter(g for s in ss for g in s)
    order=sorted(cnt,key=lambda g:(-cnt[g],str(g)))
    total=sum(cnt.values()); rows=[]; prev=0.0
    for k in range(1,min(kmax,len(order))+1):
        top=set(order[:k])
        n=sum(1 for s in ss if set(s).issubset(top))
        C=n/max(len(ss),1); S=sum(cnt[g] for g in top)/max(total,1)
        rows.append((k,order[k-1],S,n,C,C-prev,tuple(order[:k])))
        prev=C
    return order,cnt,total,rows

def emit(label,ss,kmax,L):
    order,cnt,total,rows=coverage(ss,kmax)
    L += ['', '='*100, label, '='*100,
          f'messages={len(ss)} | selected appearances={total} | distinct receivers={len(order)}',
          'selection order: ' + ' '.join(f'{g}({cnt[g]})' for g in order),
          f"{'k':>3} {'added':>8} {'S(k)':>9} {'exhausted':>10} {'C(k)':>9} {'delta C':>9}  top-k IDs"]
    for k,a,S,n,C,d,top in rows:
        L.append(f'{k:>3} {str(a):>8} {100*S:>8.2f}% {n:>10} {100*C:>8.2f}% {100*d:>8.2f}%  '+','.join(map(str,top)))
    if rows:
        p=max(rows,key=lambda r:r[5])
        L.append(f'MAX EXHAUSTION JUMP: k={p[0]} | +{100*p[5]:.2f} percentage points | C={100*p[4]:.2f}%')
    return order,rows

def sigfox_sets(path,w=10):
    with open(path,newline='') as fh:
        r=csv.DictReader(fh); bs=[h for h in (r.fieldnames or []) if h.strip().startswith('BS ')]
        if not bs: raise RuntimeError(f'{path}: no BS columns')
        out=[]
        for row in r:
            vals=[]
            for c in bs:
                v=row.get(c,'')
                if v in ('','-200','-200.0',None): continue
                try: f=float(v)
                except: continue
                if f<=-199.999: continue
                vals.append((c.strip()[3:].strip(),f))
            if len(vals)<3: continue
            vals.sort(key=lambda z:-z[1]); out.append(tuple(g for g,_ in vals[:w]))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data',required=True)
    ap.add_argument('--map',required=True)
    ap.add_argument('--evaluator-dir',default='.')
    ap.add_argument('--train-frac',type=float,default=.30)
    ap.add_argument('--seed',type=int,default=1)
    ap.add_argument('--samples',type=int,default=2500)
    ap.add_argument('--kmax',type=int,default=14)
    ap.add_argument('--sigfox-urban')
    ap.add_argument('--sigfox-rural')
    ap.add_argument('--out',default='./paperb_coverage_audit')
    a=ap.parse_args()
    sys.path.insert(0,os.path.abspath(a.evaluator_dir))
    import deltamesh_antwerp_eval_v10_fixed_080826 as ev
    phys={str(k):v for k,v in json.load(open(a.map)).items()}; roster=set(phys)
    msgs=ev.load_antwerp_csv(a.data,min_gws=3)
    m=list(msgs); random.Random(a.seed).shuffle(m); nt=int(len(m)*a.train_frac); cal,pool=m[:nt],m[nt:]
    elig=[x for x in pool if sum(1 for r in x.receptions if r.gid in roster)>=3]
    EV=random.Random(9).sample(elig,min(a.samples,len(elig)))
    ck={mkey(x) for x in cal}; dup=[x for x in EV if mkey(x) in ck]; EV=[x for x in EV if mkey(x) not in ck]
    L=['PAPER B SELECTION-SET EXHAUSTION / COVERAGE AUDIT',f'loaded={len(msgs)} map={len(roster)} cal={len(cal)}',f'duplicates dropped={len(dup)} | final eval={len(EV)}']
    A={}
    for w in (10,5):
        ss=selected_sets(EV,roster,w); A[w]=emit(f'ANTWERP max_gws={w}',ss,a.kmax,L)
    t10=set(A[10][0][:7]); t5=set(A[5][0][:7])
    L += ['', 'CROSS-WINDOW TOP-7 CHECK', 'w10: '+','.join(A[10][0][:7]), 'w5 : '+','.join(A[5][0][:7]), f'same set={t10==t5} | overlap={len(t10&t5)}/7']
    for tag,p in [('SIGFOX URBAN',a.sigfox_urban),('SIGFOX RURAL',a.sigfox_rural)]:
        if p: emit(tag+' max_gws=10',sigfox_sets(p,10),a.kmax,L)
    out=Path(a.out+'.txt'); out.write_text('\n'.join(L)+'\n'); print('\n'.join(L)); print(f'\n-> {out}')
if __name__=='__main__': main()
