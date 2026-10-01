#!/usr/bin/env python3
"""Render all specified direction-level paired calibration contrasts."""
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();out=a.out.resolve()
    if out.is_relative_to(root) or out.exists():raise SystemExit('Use a fresh directory outside the input package')
    out.mkdir(parents=True)
    data=pd.read_csv(root/'results/paired_results.csv')
    groups=[('recovered29',1,'R29\nTop one'),('recovered29',2,'R29\nTop two'),
            ('official32_minus71',1,'O32−71\nTop one'),('official32_minus71',2,'O32−71\nTop two')]
    values=[data.loc[(data['map']==name)&(data.k==k)].sort_values('draw').delta_m.to_numpy() for name,k,_ in groups]
    if any(len(v)!=32 for v in values):raise ValueError('Expected32 fields in each of4 cells')
    fig,ax=plt.subplots(figsize=(10,6))
    ax.boxplot(values,positions=range(1,5),widths=.35,whis=(0,100),showfliers=False)
    for position,y in enumerate(values,1):
        ax.scatter(position+np.linspace(-.1,.1,len(y)),y,s=20,alpha=.75,zorder=3)
    ax.axhline(0,linestyle='--',linewidth=1)
    ax.set_xticks(range(1,5),[x[2] for x in groups])
    ax.set_ylabel('Frozen median error − refitted median error (m)')
    ax.set_title('Effect of receiver-intercept refitting\n32 matched direction fields per configuration; displacement 5 km')
    ax.text(.55,.98,'Above zero: refitting reduces median error\nBelow zero: refitting increases median error',transform=ax.transAxes,va='top',fontsize=10)
    ax.grid(axis='y',alpha=.25)
    fig.text(.5,.015,'Points: individual fields. Boxes: interquartile range and median. Whiskers: full range.\nThese are finite-design paired contrasts, not independent deployments or confidence intervals.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.09,1,1))
    for suffix in ['png','svg','pdf']:fig.savefig(out/f'paired_calibration_32_fields.{suffix}',dpi=180 if suffix=='png' else None)
    plt.close(fig)

if __name__=='__main__':main()
