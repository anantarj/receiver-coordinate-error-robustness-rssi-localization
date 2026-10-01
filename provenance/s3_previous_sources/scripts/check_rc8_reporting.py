#!/usr/bin/env python3
"""Read-only RC8 scalar/geometry/document checks. No localization, fit, bootstrap or raw join.
Optional --csv recomputes the transmitter centroid from the pinned CSV and saved row IDs.
An --out destination must be new and outside this package. Expected manifests are never rewritten.
"""
from pathlib import Path
import argparse,ast,csv,hashlib,json,re
import numpy as np
R=Path(__file__).resolve().parents[1]
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def check(root=R,source_csv=None):
 d=root/'results/rc8'; binding=json.loads((d/'REPORTING_SOURCE_BINDING.json').read_text())
 for name in ['source_csv','source_cases']:
  x=binding[name]; assert digest(root/x['path'])==x['sha256'],name
 cases=json.loads((root/binding['source_cases']['path']).read_text()); c={(x['substrate'],x['arm'],x['a0_mode']):x for x in cases}
 rows=list(csv.DictReader((d/'rotation_refit_frozen.csv').open()));assert len(cases)==16 and len(rows)==6
 for x in rows:
  s,a=x['substrate'],x['arm'];ref=c[s,'reference','refit']['median_error_m'];v=c[s,a,'refit']['median_error_m'];f=c[s,a,'frozen']['median_error_m']
  for key,val in [('reference_m',ref),('refit_median_m',v),('frozen_median_m',f),('refit_minus_frozen_m',v-f),('refit_minus_frozen_pp',100*(v-f)/ref)]:
   assert abs(float(x[key])-val)<1e-8,(key,x)
  assert int(x['N'])==c[s,a,'refit']['N']==c[s,a,'frozen']['N']==2498
 rad=json.loads((d/'bounded_check_sources.json').read_text())
 for key in ['map','population']:assert digest(root/rad[key]['path'])==rad[key]['sha256'],key
 center=np.array(rad['centroid_E_N']);map_={k:np.array(v) for k,v in json.loads((root/rad['map']['path']).read_text()).items()}
 csv_done=False
 if source_csv:
  import pandas as pd
  from pyproj import Transformer
  assert digest(source_csv)==rad['csv']['payload_sha256'],'CSV fingerprint'
  df=pd.read_csv(source_csv,usecols=['Latitude','Longitude']);ids=json.loads((root/rad['population']['path']).read_text());assert len(ids)==2498
  xy=np.column_stack(Transformer.from_crs(4326,32631,always_xy=True).transform(df.iloc[ids].Longitude.to_numpy(),df.iloc[ids].Latitude.to_numpy()))
  c2=xy.mean(axis=0);assert np.allclose(center,c2,rtol=0,atol=1e-7),(center,c2);csv_done=True
 rr={x['receiver']:float(x['initial_radius_m']) for x in csv.DictReader((d/'radial_reference_radii.csv').open())};assert set(rr)==set(map_)
 radii=np.array([np.linalg.norm(map_[k]-center) for k in rr]);assert np.allclose(radii,list(rr.values()),rtol=0,atol=1e-7)
 # Extract the actual nested build function without running the scientific harness.
 code=root/'code/baseline_001_e123_pairfallback_040926.py'
 tree=ast.parse(code.read_text());nodes=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='build'];assert len(nodes)==1
 env={'np':np,'tx_centroid':center,'coh_theta':0.,'coh_theta_at':0.}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[nodes[0]],type_ignores=[])),str(code),'exec'),env)
 counts=list(csv.DictReader((d/'radial_geometry_check.csv').open()));assert len(counts)==6
 for x in counts:
  D=float(x['D_m']);n=int(x['receivers']);assert n==29
  assert int(x['centroid_crossings'])==int((radii<D).sum())
  assert int(x['final_radius_exceeds_initial'])==int((2*radii<D).sum())
  assert int(x['centroid_coincident'])==int((radii==0).sum())
  for mode,sign in [('inward',-1),('outward',1)]:
   out=env['build'](map_,set(map_),D,1,mode)
   for k in map_:
    r=np.linalg.norm(map_[k]-center);expect=map_[k]+sign*D*(map_[k]-center)/r if r>0 else map_[k]
    assert np.allclose(out[k],expect,rtol=0,atol=1e-7)
   assert np.allclose(env['build']({'0':center},{'0'},D,1,mode)['0'],center,rtol=0,atol=0)
 labels=list(csv.DictReader((d/'corrupted_count_labels.csv').open()));assert [int(x['receiver_count']) for x in labels]==[1,3,7,14,21,29]
 for x in labels:assert abs(float(x['exact_percentage'])-100*int(x['receiver_count'])/29)<1e-12
 supp=(root/'manuscript/paper_b_supplement.tex').read_text()
 for x in rows:
  for key in ['refit_median_m','frozen_median_m']:assert f'{float(x[key]):.2f}' in supp
  assert f'{float(x["refit_minus_frozen_m"]):+.2f}' in supp
  assert f'{float(x["refit_minus_frozen_pp"]):+.2f}' in supp
 return {'status':'PASS','rotation_pairs':6,'saved_scalar_cases':16,'radial_receivers':29,'radial_magnitudes':6,'actual_build_function_checked':True,'CSV_centroid_recomputed':csv_done,'new_localization':False,'new_intercept_fit':False,'new_bootstrap':False,'fresh_raw_CSV_JSON_join':False,'frozen_arm_message_errors_rederived':False}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--csv',type=Path);ap.add_argument('--out',type=Path);a=ap.parse_args()
 if a.out:
  p=a.out.resolve();assert not p.exists(),'Refuse existing output';assert p!=R and R not in p.parents,'Output must be outside package'
 result=check(R,a.csv);text=json.dumps(result,indent=2)+'\n';print(text)
 if a.out:a.out.mkdir(parents=True);(a.out/'RC8_REPORTING_CHECK.json').write_text(text)
if __name__=='__main__':main()
