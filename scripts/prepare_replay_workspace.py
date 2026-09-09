#!/usr/bin/env python3
"""Copy pinned inputs into the unchanged author replay layout. No scientific execution."""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile,stat
R=Path(__file__).resolve().parents[1]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--csv',type=Path,required=True);ap.add_argument('--catalogue',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve()
 if out.exists() or out==R or R in out.parents:raise SystemExit('Use a NEW directory outside this package.')
 pins=json.loads((R/'provenance/rc7/SCOPE_LOCK.json').read_text())['numerical_and_source_pins']
 raw=json.loads((R/'coordinate_provenance/EXTERNAL_INPUTS.json').read_text())['files']
 for kind,p in [('csv',a.csv),('catalogue',a.catalogue)]:
  if not p.is_file() or sha(p)!=raw[kind]['sha256']:raise SystemExit('Raw input fingerprint mismatch: '+kind)
 names=['baseline_001_e123_pairfallback_040926.py','deltamesh_antwerp_eval_v10_fixed_080826.py'];arc=R/'results/archives/PAPERB_B9C_REMAINING_REPLAY_050926.zip'
 for rel in ['code/'+n for n in names]+['maps/'+p.name for p in (R/'maps').glob('*.json')]+['results/archives/'+arc.name]:
  if sha(R/rel)!=pins[rel]:raise SystemExit('Pinned input mismatch: '+rel)
 with zipfile.ZipFile(arc) as z:
  for i in z.infolist():
   p=Path(i.filename)
   if p.is_absolute() or '..' in p.parts or stat.S_ISLNK(i.external_attr>>16):raise SystemExit('Unsafe ZIP member')
  out.mkdir(parents=True);z.extractall(out)
 dest=out/'PAPERB_STAGE_B5_040926/scripts';dest.mkdir(parents=True)
 for n in names:shutil.copy2(R/'code'/n,dest/n)
 shutil.copy2(a.csv,dest/'lorawan_antwerp_2019_dataset.csv');shutil.copy2(a.catalogue,dest/'lorawan_antwerp_gateway_locations.json')
 m=out/'PAPERB_B9C_OFFICIAL33_CORE_050926/inputs';m.mkdir(parents=True)
 for p in (R/'maps').glob('*.json'):shutil.copy2(p,m/p.name)
 # Some legacy diagnostic entry points address the recovered map by this name.
 shutil.copy2(R/'maps/recovered29.json',dest/'bs_to_utm_extended.json')
 receipt={'status':'WORKSPACE_PREPARED','scientific_execution':False,'source_package':str(R),'workspace':str(out),'replay_zip_sha256':sha(arc),'pinned_inputs':{p.relative_to(out).as_posix():sha(p) for p in list(dest.iterdir())+list(m.iterdir()) if p.is_file()},'warning':'This workspace contains private source payload copies. Do not redistribute it or upload execution caches.'}
 (out/'WORKSPACE_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt,indent=2));print('Next (separate action): PREFLIGHT_ONLY=1 bash '+str(out/'PAPERB_B9C_REMAINING_REPLAY_050926/run_b9c_remaining.sh'))
if __name__=='__main__':main()
