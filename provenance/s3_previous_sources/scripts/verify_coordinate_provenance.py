#!/usr/bin/env python3
"""Verify frozen coordinate inputs; optional raw CSV/JSON identity replay.

No map, estimator, population, or checksum manifest is modified. A new output
folder outside the package is required. --rebuild additionally needs the original
CSV, message JSON and catalogue (plain files or single-payload ZIPs).
"""
from __future__ import annotations
import argparse,csv,hashlib,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def load(p:Path):return json.loads(p.read_text())
def save(p:Path,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def maps(root:Path):return {p.stem:load(p) for p in (root/'maps').glob('*.json') if p.name!='B9C_MAP_MANIFEST.json'}
def saved_check(root:Path)->dict:
 p=root/'coordinate_provenance';source=load(p/'SOURCE_MANIFEST.json');checks=[]
 for item in source['copies']:
  f=root/item['destination'];assert f.is_file() and digest(f)==item['sha256'],item['destination']
  checks.append({'source_copy':item['destination'],'sha256':item['sha256'],'matches':True})
 m=maps(root);r=m['recovered29'];o=m['official33_published'];s=dict(o);s['71']=r['71'];shared=set(r)&set(o)
 expected={'official33_repaired71':s,'official32_minus71':{k:v for k,v in o.items() if k!='71'},
 'recovered27_common':{k:v for k,v in r.items() if k in shared},'official27_common':{k:v for k,v in s.items() if k in shared},
 'recovered26_common_minus71':{k:v for k,v in r.items() if k in shared and k!='71'},'official26_common_minus71':{k:v for k,v in s.items() if k in shared and k!='71'}}
 for name,e in expected.items():assert m[name]==e,name
 assert m['official27_common']['71']==r['71']!=o['71']
 full=load(p/'source_records/rebuilt_full_identities.json');cal=load(p/'source_records/rebuilt_calibration_identities.json')
 with (p/'used_receiver_crosswalk.csv').open() as f:records=list(csv.DictReader(f))
 used=set().union(*(set(x) for x in m.values()))
 assert len(records)==len(used)==35 and {x['bs'] for x in records}==used
 for row in records:
  bs=row['bs'];assert full[bs]==cal[bs]==row['gateway_id'],bs
 source_map=load(p/'source_records/rebuilt_reference_same_legacy33.json');assert o==source_map,'catalogue map values versus source record'
 for a,b in [('recovered27_common','official27_common'),('recovered26_common_minus71','official26_common_minus71')]:
  f=root/f'results/rc5/populations/{a}_ordered_source_rows.json';g=root/f'results/rc5/populations/{b}_ordered_source_rows.json'
  assert load(f)==load(g),f'{a}/{b} populations'
 lock=load(root/'provenance/rc7/SCOPE_LOCK.json'); map_pins={k:v for k,v in lock['numerical_and_source_pins'].items() if k.startswith('maps/')}
 for rel,h in map_pins.items():assert digest(root/rel)==h,rel
 return {'source_copies_checked':len(checks),'source_copy_checks':checks,'used_identities':35,'metadata_pairs':33,'derived_map_constructions':list(expected),'common27_BS71_held_at_R29':True,'map_hashes_unchanged':True,'common_roster_population_pairing':True,'raw_join_reexecuted':False,'scope':'Saved-source identities, map algebra, exact pairs, hashes and population pairing; not historical selection reconstruction or physical validation.'}
def payload(path:Path,expected:str,work:Path,name:str)->Path:
 if zipfile.is_zipfile(path):
  with zipfile.ZipFile(path) as z:
   candidates=[i for i in z.infolist() if not i.is_dir() and not Path(i.filename).name.startswith('.') and '__MACOSX' not in i.filename]
   if len(candidates)!=1:raise ValueError(f'{path}: expected exactly one payload, found {len(candidates)}')
   dest=work/name
   with z.open(candidates[0]) as src,dest.open('wb') as out:
    while block:=src.read(1<<20):out.write(block)
   path=dest
 if digest(path)!=expected:raise ValueError(f'Input fingerprint mismatch: {path.name}')
 return path.resolve()
def main():
 if not __debug__:raise ValueError('Do not disable assertion checks with Python optimization flags')
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--rebuild',action='store_true');ap.add_argument('--csv',type=Path);ap.add_argument('--json',type=Path);ap.add_argument('--catalogue',type=Path);args=ap.parse_args()
 out=args.out.resolve()
 if out==ROOT or ROOT in out.parents:raise ValueError('Output must be outside the package')
 if out.exists():raise ValueError('Output already exists; refusing overwrite')
 if args.rebuild and not all([args.csv,args.json,args.catalogue]):raise ValueError('--rebuild requires --csv, --json and --catalogue')
 result=saved_check(ROOT);out.mkdir(parents=True,exist_ok=False)
 if args.rebuild:
  spec=load(ROOT/'coordinate_provenance/EXTERNAL_INPUTS.json')['files'];raw=out/'raw_inputs';raw.mkdir()
  inputs={k:payload(getattr(args,k),spec[k]['sha256'],raw,spec[k]['filename']) for k in ['csv','json','catalogue']}
  cmd=[sys.executable,str(ROOT/'coordinate_provenance/sources/rebuild_join.py'),'--csv',str(inputs['csv']),'--json',str(inputs['json']),'--out',str(out/'join')]
  with (out/'join.stdout.txt').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  from pyproj import Transformer
  identities=load(out/'join/rebuilt_full_identities.json');cat=load(inputs['catalogue']);m=maps(ROOT);tf=Transformer.from_crs(4326,32631,always_xy=True)
  projected={}
  for bs,xy in m['official33_published'].items():
   eui=identities[bs];assert eui in cat
   x,y=tf.transform(cat[eui]['longitude'],cat[eui]['latitude']);projected[bs]=[round(x,1),round(y,1)];assert projected[bs]==xy,bs
  saved=load(ROOT/'coordinate_provenance/source_records/rebuilt_full_identities.json')
  for bs in set().union(*(set(x) for x in m.values())):assert identities[bs]==saved[bs],bs
  result.update(raw_join_reexecuted=True,raw_input_hashes={k:digest(v) for k,v in inputs.items()},reconstructed_33_pairs_match=True,scope='Fresh raw identity replay plus projection compared against frozen supplied inputs; no receiver refit or localization producer execution.')
 save(out/'COORDINATE_CHECK.json',result);print(json.dumps(result,indent=2))
 print('PASS — input verification only. No scientific result, package file or approval changed.')
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,AssertionError,subprocess.CalledProcessError,KeyError) as exc:
  print(f'FAIL: {exc}',file=sys.stderr);raise SystemExit(2)
