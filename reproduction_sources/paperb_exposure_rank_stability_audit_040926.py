#!/usr/bin/env python3
"""Audit whether exposure rankings learned from calibration traffic reproduce on held-out traffic."""
from __future__ import annotations
import argparse,csv,json,os,random,sys
from pathlib import Path
import numpy as np

def mkey(m):
    return (round(float(m.x),3),round(float(m.y),3),tuple(sorted((r.gid,round(float(r.rssi),3)) for r in m.receptions)))

def sets_counts(msgs, roster, max_gws):
    sets=[]; counts={g:0 for g in roster}
    for m in msgs:
        rx=[r for r in m.receptions if r.gid in roster]
        if len(rx)<3: continue
        ss=tuple(r.gid for r in sorted(rx,key=lambda r:-float(r.rssi))[:max_gws]); sets.append(ss)
        for g in ss: counts[g]+=1
    base=sorted(roster,key=lambda g:int(g) if str(g).isdigit() else str(g))
    order=sorted(base,key=lambda g:-counts.get(g,0))  # stable tie order matches the harness
    return sets,counts,order

def spearman(order_a,order_b):
    ra={g:i for i,g in enumerate(order_a)}; rb={g:i for i,g in enumerate(order_b)}
    common=[g for g in order_a if g in rb]
    if len(common)<3:return float('nan')
    return float(np.corrcoef([ra[g] for g in common],[rb[g] for g in common])[0,1])

def coverage(eval_sets,order,k):
    top=set(order[:k]); return 100*sum(set(s).issubset(top) for s in eval_sets)/max(len(eval_sets),1)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',required=True); ap.add_argument('--map',required=True)
    ap.add_argument('--evaluator-dir',default='.'); ap.add_argument('--max-gws',type=int,default=10)
    ap.add_argument('--kmax',type=int,default=14); ap.add_argument('--samples',type=int,default=2500)
    ap.add_argument('--seed',type=int,default=1); ap.add_argument('--out',default='./paperb_exposure_rank_stability')
    args=ap.parse_args(); sys.path.insert(0,os.path.abspath(args.evaluator_dir))
    import deltamesh_antwerp_eval_v10_fixed_080826 as ev
    roster=set(map(str,json.load(open(args.map)).keys())); msgs=ev.load_antwerp_csv(args.data,min_gws=3)
    m=list(msgs); random.Random(args.seed).shuffle(m); nt=int(len(m)*.30); cal,pool=m[:nt],m[nt:]
    eligible=[x for x in pool if sum(r.gid in roster for r in x.receptions)>=3]
    EV=random.Random(9).sample(eligible,min(args.samples,len(eligible))); ck={mkey(x) for x in cal}; EV=[x for x in EV if mkey(x) not in ck]
    cA,cB=cal[0::2],cal[1::2]
    populations={'evaluation':EV,'calibration':cal,'cal_half_A':cA,'cal_half_B':cB}
    parsed={name:sets_counts(ms,roster,args.max_gws) for name,ms in populations.items()}
    eval_sets=parsed['evaluation'][0]
    rankings={name:v[2] for name,v in parsed.items()}
    rows=[]
    for source,order in rankings.items():
        for k in range(1,min(args.kmax,len(order))+1):
            rows.append(dict(ranking_source=source,k=k,top_ids=';'.join(order[:k]),C_eval_pct=coverage(eval_sets,order,k)))
    with open(args.out+'.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    lines=[f'eval_messages={len(EV)} calibration_messages={len(cal)} roster={len(roster)} max_gws={args.max_gws}',
           'pair,spearman,top7_overlap,top7_jaccard']
    names=list(rankings)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            A=set(rankings[a][:7]);B=set(rankings[b][:7]); ov=len(A&B)
            lines.append(f'{a} vs {b},{spearman(rankings[a],rankings[b]):.4f},{ov}/7,{ov/len(A|B):.4f}')
    lines+=['','ranking_source,k,C_eval_pct,top_ids']
    for r in rows: lines.append(f"{r['ranking_source']},{r['k']},{r['C_eval_pct']:.4f},{r['top_ids']}")
    Path(args.out+'.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines[:8]));print('->',args.out+'.csv');print('->',args.out+'.txt')
if __name__=='__main__':main()
