#!/usr/bin/env python3
"""Export the original 40 matched-exposure configurations without redesign or tuning.
Inputs are verified; the canonical scientific functions remain unchanged. Outputs
are assistant-runtime reporting-recovery derivatives, not author-machine evidence.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,pickle,random,sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; METHODS=['WCL','ABS','DIFF','Min-Max']; STATE={}
HASHES={'baseline_001_e123_pairfallback_040926.py':'6e8881f3a83b70c49ee2b1f3892b9a2cf65e5491717c336b3e1cbace01943b2f','deltamesh_antwerp_eval_v10_fixed_080826.py':'b14b35b5748e447971e5b22da7c39ededc8277aa04e5690eeff672bf1311cac5','data':'870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446','map':'cfddca4fc5a0ad51fb4d8717be807454c891ba3c4872ff1a4e6b9aec3f5ae2da'}
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_csv(p,rs):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0])); w.writeheader(); w.writerows(rs)
def imports():
 sys.path.insert(0,str(ROOT/'code'))
 import baseline_001_e123_pairfallback_040926 as h
 import deltamesh_antwerp_eval_v10_fixed_080826 as ev
 return h,ev

def prepare(data,work):
 for key in HASHES:
  p=data if key=='data' else ROOT/'maps/recovered29.json' if key=='map' else ROOT/'code'/key
  if digest(p)!=HASHES[key]: raise RuntimeError(f'Input identity mismatch: {p}')
 h,ev=imports(); msgs=ev.load_antwerp_csv(str(data),min_gws=3)
 import pandas as pd
 df=pd.read_csv(data); bs=[c for c in df if str(c).strip().lower().startswith('bs ')]
 v=df[bs].to_numpy(float); src=np.flatnonzero((np.isfinite(v)&(v>=-150)&(v<=-20)).sum(axis=1)>=3)
 assert len(msgs)==len(src)==55375
 for mm,row in zip(msgs,src): setattr(mm,'_source_row',int(row))
 seq=list(msgs);random.Random(1).shuffle(seq);cal,pool=seq[:16612],seq[16612:];keys={h.mkey(m) for m in cal}
 raw=json.loads((ROOT/'maps/recovered29.json').read_text());G=sorted(raw,key=int);C={g:np.asarray(raw[g],float) for g in G}
 held=[m for m in pool if sum(rx.gid in C for rx in m.receptions)>=3]
 EV=[m for m in random.Random(9).sample(held,2500) if h.mkey(m) not in keys];ids=[m._source_row for m in EV]
 idhash=hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
 assert idhash=='ebda5a2d559d0ae1102fc8b151937bed02dfc274f2a2b4d1d587531de10aabbf'
 assert set(C)==set(h.fit_a0(cal,C,4.7))
 selected={g:0 for g in G}
 for mm in EV:
  for rx in sorted([r for r in mm.receptions if r.gid in C],key=lambda r:-r.rssi)[:10]: selected[rx.gid]+=1
 total=sum(selected.values());assert total==10680
 rg=random.Random(6606);design=[];directions=[]
 for center in (.1,.2,.3,.4,.5):
  found=0;tries=0
  while found<8 and tries<4000:
   tries+=1;k=rg.randint(2,14);target=set(rg.sample(G,k));num=sum(selected[g] for g in target);S=num/total
   if abs(S-center)>.025:continue
   name=f'bin{int(center*100):02d}_subset{found}';seed=6700+found;field=np.random.default_rng(seed);offsets={}
   for g in G:
    if g in target:
     th=field.uniform(0,2*np.pi);delta=5000*np.array([np.cos(th),np.sin(th)]);offsets[g]=delta.tolist()
     directions.append(dict(case_id=name,receiver=g,seed=seed,theta_radians=th,dx_m=delta[0],dy_m=delta[1]))
   design.append(dict(case_id=name,bin_center=center,tolerance=.025,accepted_index=found,proposal_index=tries,k=k,exact_S=S,selected_reception_numerator=num,denominator=total,receiver_ids=';'.join(sorted(target,key=int)),displacement_m=5000,direction_seed=seed,direction_realizations_per_subset=1,subset_rng_seed=6606,offsets=offsets));found+=1
  assert found==8
 work.mkdir(parents=True,exist_ok=True); cache=work/'private_cache.pkl';cache.write_bytes(pickle.dumps(dict(C=C,cal=cal,EV=EV,ids=ids)))
 return cache,design,directions,idhash

def init(cache):
 h,ev=imports();STATE.update(pickle.loads(Path(cache).read_bytes()),h=h,ev=ev)
def score(task):
 row,out=task;h,ev=STATE['h'],STATE['ev'];mp={g:v+np.asarray(row['offsets'].get(g,[0.,0.])) for g,v in STATE['C'].items()};a0=h.fit_a0(STATE['cal'],mp,4.7);errors=[]
 for mm in STATE['EV']:
  rx=sorted([r for r in mm.receptions if r.gid in mp and r.gid in a0],key=lambda r:-r.rssi)[:10]
  if len(rx)<3:raise RuntimeError('Changed population')
  gg=np.vstack([mp[r.gid] for r in rx]);rr=np.array([r.rssi-a0[r.gid] for r in rx]);t=np.array([mm.x,mm.y])
  preds=(h.wcl(ev,gg,rr),h.lattice(ev,gg,rr,4.7,'abs','mean'),h.lattice(ev,gg,rr,4.7,'diff','median'),h.minmax(gg,rr,4.7))
  errors.append([np.linalg.norm(x-t) for x in preds])
 a=np.array(errors);assert a.shape==(2498,4) and np.isfinite(a).all() and (a>=0).all()
 p=Path(out)/'raw'/f"{row['case_id']}.npz";p.parent.mkdir(exist_ok=True);np.savez_compressed(p,error_m=a,source_row=np.asarray(STATE['ids']),methods=np.asarray(METHODS))
 return row['case_id'],np.median(a,axis=0).tolist(),digest(p)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,required=True);ap.add_argument('--out',type=Path,default=ROOT/'results/rc5/matched_exposure');ap.add_argument('--work',type=Path,required=True);ap.add_argument('--workers',type=int,default=6);a=ap.parse_args()
 a.out.mkdir(parents=True,exist_ok=True);cache,design,dirs,idhash=prepare(a.data,a.work)
 serial=[{k:v for k,v in row.items() if k!='offsets'} for row in design]
 write_csv(a.out/'subset_register.csv',serial);write_csv(a.out/'direction_register.csv',dirs)
 (a.out/'RECOVERY_SPEC.json').write_text(json.dumps(dict(purpose='Reporting recovery of existing 40 configurations; no new hypothesis test',execution='assistant-runtime derivative, not author-machine rerun',data_sha256=HASHES['data'],population_sha256=idhash,configuration_count=40,draws_per_subset=1,code_hashes=HASHES),indent=2)+'\n')
 tasks=[({'case_id':'reference','offsets':{}},str(a.out))]+[(r,str(a.out)) for r in design];got={}
 with ProcessPoolExecutor(max_workers=a.workers,initializer=init,initargs=(str(cache),)) as ex:
  for fut in as_completed([ex.submit(score,t) for t in tasks]):
   name,v,hs=fut.result();got[name]=(v,hs);print(f'{len(got)}/{len(tasks)} {name}: {v}',flush=True)
 ref=np.asarray(got['reference'][0]);rows=[]
 for r in serial:
  vals=np.array(got[r['case_id']][0]);pp=100*(vals-ref)/ref
  for j,m in enumerate(METHODS):rows.append(dict(**r,method=m,reference_m=ref[j],median_error_m=vals[j],change_pct=pp[j],raw_npz='raw/'+r['case_id']+'.npz',raw_sha256=got[r['case_id']][1],provenance='RC5 same-design reporting recovery; assistant runtime'))
 write_csv(a.out/'subset_results.csv',rows)
 with (ROOT/'results/figure_data/paperb_matched_exposure.csv').open() as f:original=list(csv.DictReader(f))
 checks=[];summary=[]
 for b in original:
  cen=float(b['S_bin']);rr=[r for r in rows if r['bin_center']==cen];s={'bin_center':cen,'n_subsets':8}
  for m,label in zip(METHODS,['WCL','ABS','DIFF','MinMax']):
   vals=np.array([r['change_pct'] for r in rr if r['method']==m]);mid=float(np.median(vals));s[label+'_median_pct']=mid;s[label+'_min_pct']=float(vals.min());s[label+'_max_pct']=float(vals.max());field=label+'_med_pct'
   checks.append(dict(bin_center=cen,field=field,expected=float(b[field]),recovered=mid,pass_at_printed_precision=(f'{mid:.1f}'==f'{float(b[field]):.1f}')))
   if m=='WCL':
    for stat,field in [('min','WCL_min_pct'),('max','WCL_max_pct')]:
     v=float(vals.min() if stat=='min' else vals.max());checks.append(dict(bin_center=cen,field=field,expected=float(b[field]),recovered=v,pass_at_printed_precision=(f'{v:.1f}'==f'{float(b[field]):.1f}')))
  summary.append(s)
 write_csv(a.out/'bin_results.csv',summary);write_csv(a.out/'aggregate_parity.csv',checks)
 status=dict(status='PASS' if all(r['pass_at_printed_precision'] for r in checks) else 'REVIEW',matched_fields=len(checks),population_n=2498,configuration_count=40,baseline=ref.tolist(),interpretation='Original one-decimal aggregate parity only; historical per-subset outputs were not retained. No claim of per-subset historical bitwise parity.',new_inference=False)
 (a.out/'RECOVERY_STATUS.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
 if status['status']!='PASS':sys.exit(2)
if __name__=='__main__':main()
