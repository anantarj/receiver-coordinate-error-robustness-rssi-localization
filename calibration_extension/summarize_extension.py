#!/usr/bin/env python3
"""Regenerate cell/secondary/contrary tables from all retained pairs.
Writes only to a fresh output directory. Run verification first.
"""
from pathlib import Path
import argparse,json
import pandas as pd
import numpy as np

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();out=a.out.resolve()
    if out.is_relative_to(root) or out.exists():raise SystemExit('Use a fresh output directory outside the input package')
    out.mkdir(parents=True)
    df=pd.read_csv(root/'extension/paired_results.csv');summary=[];secondary=[]
    for name in ['recovered29','official32_minus71']:
        for k in [1,2]:
            g=df[(df['map']==name)&(df.k==k)].sort_values('draw');d=g.delta_m.to_numpy()
            if len(g)!=32 or set(g.draw)!=set(range(32)):raise ValueError('Incomplete cell')
            summary.append(dict(map=name,k=k,fields=32,refit_pct_median=np.median(g.refit_pct),frozen_pct_median=np.median(g.frozen_pct),
                paired_delta_m_median=np.median(d),paired_delta_m_q25=np.quantile(d,.25),paired_delta_m_q75=np.quantile(d,.75),
                paired_delta_m_min=d.min(),paired_delta_m_max=d.max(),beneficial_fields=int((d>0).sum()),
                harmful_fields=int((d<0).sum()),zero_fields=int((d==0).sum()),touched_messages=int(g.touched_n.iloc[0]),
                evaluation_messages=2498,touched_paired_delta_m_median=np.median(g.touched_delta_m),
                difference_of_arm_medians_m=np.median(g.frozen_m)-np.median(g.refit_m)))
            intercepts=[]
            for row in g.itertuples():
                meta=json.loads((root/'extension/pairs'/f'{row.case}.json').read_text())
                for target in meta['field']['offsets']:
                    delta=meta['refit_a0'][target]-meta['reference_a0'][target]
                    intercepts.append(dict(case=row.case,map=name,k=k,target=int(target),delta_a0_db=delta,
                        unnormalized_weight_ratio=10**(-delta/10)))
            idf=pd.DataFrame(intercepts);idf.to_csv(out/f'{name}_top{k}_intercepts.csv',index=False)
            secondary.append(dict(map=name,k=k,pairs=32,touched_n=int(g.touched_n.iloc[0]),touched_pct=100*g.touched_n.iloc[0]/2498,
                touched_refit_median_across_fields=np.median(g.touched_refit_m),touched_frozen_median_across_fields=np.median(g.touched_frozen_m),
                touched_delta_positive=int((g.touched_delta_m>0).sum()),touched_delta_negative=int((g.touched_delta_m<0).sum()),
                frozen_target_mass_median=np.median(g.touched_frozen_target_weight_median),refit_target_mass_median=np.median(g.touched_refit_target_weight_median),
                min_delta_a0_db=idf.delta_a0_db.min(),max_delta_a0_db=idf.delta_a0_db.max()))
    pd.DataFrame(summary).to_csv(out/'cell_summary.csv',index=False)
    pd.DataFrame(secondary).to_csv(out/'secondary_diagnostics.csv',index=False)
    df[df.delta_m<0].to_csv(out/'contrary_cases.csv',index=False)
    print('Reconstructed four complete cells and all four contrary cases:',out)

if __name__=='__main__':main()
