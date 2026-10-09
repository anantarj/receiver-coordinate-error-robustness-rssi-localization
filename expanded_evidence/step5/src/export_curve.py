#!/usr/bin/env python3
"""Export any complete finite empirical curve from a retained error-vector NPZ."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from analyze_exceedance import scores,write_curve
from exceedance import curve
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/step4'))
from step2_raw_helpers import populations

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--npz',type=Path,required=True);ap.add_argument('--D',type=float,required=True);ap.add_argument('--draw',type=int,required=True);ap.add_argument('--kappa',type=float,required=True);ap.add_argument('--left',default='frozen');ap.add_argument('--right',default='unrestricted');ap.add_argument('--population',default='full');ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 if a.out.exists():raise ValueError('Refusing existing output')
 with np.load(a.npz,allow_pickle=False) as z:v={k:z[k] for k in ['errors','reference_errors','removal_errors','affected','remaining_count','field_D_m','field_draw','kappa','policies']}
 fi=int(np.flatnonzero((v['field_D_m']==a.D)&(v['field_draw']==a.draw))[0]);ki=list(v['kappa']).index(a.kappa);mask=populations(v['affected'],v['remaining_count'])[a.population]
 l=scores(v,fi,ki,a.left)[mask];r=scores(v,fi,ki,a.right)[mask];n=len(l)
 la=v['remaining_count'][mask]>=3 if a.left=='removal_operational' else np.ones(n,bool);ra=v['remaining_count'][mask]>=3 if a.right=='removal_operational' else np.ones(n,bool)
 c,s=curve(l,r,la,ra);write_curve(a.out,c,n);print(json.dumps(s,indent=2))
if __name__=='__main__':main()
