#!/usr/bin/env python3
"""Project frozen rebuilt identities without any legacy-map dependency.

Exports all available catalogue coordinates and two explicit calibration-count
subsets. These are evidence products, not automatic replacements for an existing
benchmark population. The 20-observation subset is a post-review support rule,
not a claim about the unknown historical vote-generation process.
"""
import argparse,json
from pathlib import Path
import pandas as pd
from pyproj import Transformer

def main():
 p=argparse.ArgumentParser();p.add_argument('--join',type=Path,required=True);p.add_argument('--catalogue',type=Path,required=True);a=p.parse_args()
 mp=json.loads((a.join/'rebuilt_full_identities.json').read_text());cat=json.loads(a.catalogue.read_text());ev=pd.read_csv(a.join/'column_evidence.csv',dtype={'bs':str}).set_index('bs');tf=Transformer.from_crs(4326,32631,always_xy=True)
 full={}
 for bs,e in mp.items():
  if e in cat:
   x,y=tf.transform(cat[e]['longitude'],cat[e]['latitude']);full[bs]=[round(x,1),round(y,1)]
 for name,subset in [('catalogue_all39',full),('calibration_ge10_35',{b:v for b,v in full.items() if ev.loc[b,'calibration_receptions']>=10}),('calibration_ge20_33',{b:v for b,v in full.items() if ev.loc[b,'calibration_receptions']>=20})]:
  (a.join/f'rebuilt_{name}.json').write_text(json.dumps(subset,indent=2,sort_keys=True)+'\n')
 print({name:len(json.loads((a.join/f'rebuilt_{name}.json').read_text())) for name in ['catalogue_all39','calibration_ge10_35','calibration_ge20_33']})
if __name__=='__main__':main()
