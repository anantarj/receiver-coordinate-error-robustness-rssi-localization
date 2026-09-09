#!/usr/bin/env python3
"""Fresh CSV/JSON identity reconstruction; no legacy-map input and no GPS use.

Reads plain scientific payloads. The legacy cleaned mapping is intentionally not
an argument. Gateway-coordinate projection/comparison is a later operation.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, random, re
from pathlib import Path
import numpy as np
import pandas as pd

def digest(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def dump(p: Path,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')

def integral(v):
    x=float(v)
    if not np.isfinite(x) or not x.is_integer():raise ValueError('Nonintegral or nonfinite RSSI')
    return int(x)

def jkey(m):
    gw=m['gateways']
    if not gw:raise ValueError('Empty JSON gateway list')
    return (str(gw[0]['rx_time']['time']),int(m['sf']),round(float(m['hdop']),2),tuple(sorted(integral(g['rssi']) for g in gw)))

def signatures(a,indices):
    # Hash to propose equality, verify each candidate with exact array equality.
    return [hashlib.sha256(np.ascontiguousarray(a[indices,k],dtype='<i2').tobytes()).hexdigest() for k in range(a.shape[1])]

def matches(a,b,rows):
    ha,hb=signatures(a,rows),signatures(b,rows);out={}
    for k,s in enumerate(ha):
        out[k]=[j for j,t in enumerate(hb) if t==s and np.array_equal(a[rows,k],b[rows,j])]
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--csv',type=Path,required=True);ap.add_argument('--json',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    # No coordinates loaded from the CSV; JSON coordinates are never accessed.
    head=pd.read_csv(a.csv,nrows=0)
    cols=sorted([c for c in head if re.fullmatch(r'BS\s+\d+',c)],key=lambda s:int(s.split()[-1]))
    d=pd.read_csv(a.csv,usecols=cols+['RX Time','SF','HDOP'])
    raw=d[cols].to_numpy(float)
    if not (np.isfinite(raw).all() and np.equal(raw,np.rint(raw)).all()):raise ValueError('RSSI schema differs')
    arr=raw.astype(np.int16);present=arr!=-200
    if np.any(arr[present]<=-200):raise ValueError('Unexpected missing sentinel')
    js=json.loads(a.json.read_text());groups={};keycounts=collections.Counter()
    euis=sorted({str(g['id']) for m in js for g in m['gateways']});ej={e:i for i,e in enumerate(euis)}
    for i,m in enumerate(js):
        key=jkey(m);pairs=tuple(sorted((str(g['id']),integral(g['rssi'])) for g in m['gateways']))
        if len(set(p[0] for p in pairs))!=len(pairs):raise ValueError('Duplicate JSON gateway ID')
        if key in groups:
            if groups[key]['pairs']!=pairs:raise ValueError('Alignment collision with disagreeing receptions')
            groups[key]['indices'].append(i)
        else:groups[key]={'pairs':pairs,'indices':[i]}
        keycounts[key]+=1
    aligned=np.full((len(d),len(euis)),-200,dtype=np.int16);used=collections.Counter();align=[]
    for i,(time,sf,hdop) in enumerate(d[['RX Time','SF','HDOP']].itertuples(index=False,name=None)):
        key=(str(time),int(sf),round(float(hdop),2),tuple(sorted(map(int,arr[i,present[i]]))))
        if key not in groups:raise ValueError(f'Unmatched CSV row {i}')
        group=groups[key];used[key]+=1
        if used[key]>keycounts[key]:raise ValueError('CSV multiplicity exceeds JSON')
        for e,r in group['pairs']:aligned[i,ej[e]]=r
        align.append((i,group['indices'][used[key]-1],len(group['indices'])))
    allrows=np.arange(len(d));full=matches(arr,aligned,allrows)
    # Exactly the historical census validity rule, without reading GPS values.
    valid=(arr>=-150)&(arr<=-20);working=np.flatnonzero(valid.sum(axis=1)>=3)
    order=list(map(int,working));random.Random(1).shuffle(order);cal=np.array(order[:int(.3*len(order))],int)
    cf=matches(arr,aligned,cal);comp=np.setdiff1d(allrows,cal)
    records=[];fullmap={};calmap={}
    for k,c in enumerate(cols):
        num=str(int(c.split()[-1]));nr=int(present[:,k].sum());nc=int(present[cal,k].sum())
        fq=full[k];cq=cf[k]
        if nr>0 and len(fq)==1:fullmap[num]=euis[fq[0]]
        if nc>0 and len(cq)==1:calmap[num]=euis[cq[0]]
        mm=int(np.sum(arr[comp,k]!=aligned[comp,cq[0]])) if nc>0 and len(cq)==1 else None
        records.append({'bs':num,'release_receptions':nr,'calibration_receptions':nc,'full_candidate_count':len(fq),'full_candidates':';'.join(euis[j] for j in fq),'calibration_candidate_count':len(cq),'calibration_candidates':';'.join(euis[j] for j in cq),'out_of_calibration_mismatches':mm})
    if len(set(fullmap.values()))!=len(fullmap):raise ValueError('Nonbijective active mapping')
    if any(r['out_of_calibration_mismatches'] not in (None,0) for r in records):raise ValueError('Calibration mapping fails validation')
    surplus=[]
    for key,n in keycounts.items():
        if n>used[key]:
            for i in groups[key]['indices'][used[key]:]:
                m=js[i];surplus.append({'json_index0':i,'time':key[0],'sf':key[1],'hdop':key[2],'reception_count':len(m['gateways']),'gateway_rssi':groups[key]['pairs'],'counter':m.get('counter')})
    pd.DataFrame(records).to_csv(a.out/'column_evidence.csv',index=False)
    pd.DataFrame(align,columns=['csv_row_index0','json_index0_occurrence_representative','group_multiplicity']).to_csv(a.out/'alignment.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    dump(a.out/'rebuilt_full_identities.json',fullmap);dump(a.out/'rebuilt_calibration_identities.json',calmap)
    dump(a.out/'surplus_json_records.json',surplus)
    csvcount=collections.Counter(map(int,present.sum(axis=1)));jcount=collections.Counter(len(m['gateways']) for m in js)
    result={'inputs':{'csv_sha256':digest(a.csv),'json_sha256':digest(a.json)},'construction_inputs_exclude_legacy_map_and_coordinates':True,'csv_rows':len(d),'json_rows':len(js),'matched_csv_rows':len(align),'csv_working_ge3':len(working),'json_ge3':sum(n for k,n in jcount.items() if k>=3),'csv_count_distribution':dict(csvcount),'json_count_distribution':dict(jcount),'distinct_gateway_ids':len(euis),'active_csv_columns':int(np.sum(present.any(axis=0))),'unambiguous_full_identities':len(fullmap),'unambiguous_calibration_identities':len(calmap),'calibration_rows':len(cal),'duplicate_key_group_sizes':dict(collections.Counter(len(v['indices']) for v in groups.values())),'surplus_json_count':len(surplus),'calibration_identified_holdout_mismatches':sum(r['out_of_calibration_mismatches'] or 0 for r in records),'map_sha256':digest(a.out/'rebuilt_full_identities.json')}
    dump(a.out/'construction_summary.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
