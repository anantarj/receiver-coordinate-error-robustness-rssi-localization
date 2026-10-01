#!/usr/bin/env python3
"""Regenerate the four descriptive paired-calibration cells; no localization is rerun."""
from pathlib import Path
import csv,json,statistics,math
root=Path(__file__).resolve().parent
p=root/'calibration_extension/results/paired_results.csv'
rows=list(csv.DictReader(p.open()))
if len(rows)!=128:raise SystemExit('FAIL: expected 128 complete pairs')
expected={('recovered29',1):(192.92,5.83,226.89,32,0),('recovered29',2):(587.87,327.07,736.86,32,0),('official32_minus71',1):(169.03,-25.25,248.24,28,4),('official32_minus71',2):(307.93,123.24,448.39,32,0)}
summary=[]
for (name,k),target in expected.items():
    cell=[r for r in rows if r['map']==name and int(float(r['k']))==k]
    if sorted(int(float(r['draw'])) for r in cell)!=list(range(32)):raise SystemExit('FAIL: incomplete/duplicate fields')
    v=[float(r['delta_m']) for r in cell]
    if not all(math.isfinite(x) for x in v):raise SystemExit('FAIL: nonfinite')
    got=(statistics.median(v),min(v),max(v),sum(x>0 for x in v),sum(x<0 for x in v))
    if any(abs(got[i]-target[i])>0.011 for i in range(3)) or got[3:]!=target[3:]:raise SystemExit('FAIL: summary mismatch '+name+str(k))
    summary.append(dict(map=name,k=k,fields=32,median_benefit_m=got[0],min_m=got[1],max_m=got[2],positive=got[3],negative=got[4]))
print(json.dumps({'status':'PASS','scope':'128 stored paired differences and four descriptive summaries; not a localization rerun','cells':summary},indent=2))
