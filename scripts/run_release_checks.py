#!/usr/bin/env python3
"""Run all advertised no-raw-data checks; reports go to a new external directory.
This is not a localization rerun, intercept fit, raw identity join or remote DOI operation.
"""
from pathlib import Path
import argparse,json,subprocess,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    out=a.out.resolve()
    if out==ROOT or ROOT in out.parents or out.exists():raise SystemExit('Choose a new output directory outside the package')
    out.mkdir(parents=True)
    mf=ROOT/'PUBLIC_RELEASE_SHA256SUMS.txt';before=hashlib.sha256(mf.read_bytes()).hexdigest()
    commands=[
        ('integrity',['verify_evidence.py']),
        ('calibration_summaries',['verify_calibration_tables.py']),
        ('baseline_arrays',['scripts/check_rc5_reporting.py']),
        ('rotation_geometry_document',['scripts/check_rc8_reporting.py']),
        ('coordinate_sources',['scripts/verify_coordinate_provenance.py','--out',str(out/'coordinate')]),
        ('extension_integrity',['calibration_extension/release_repair/verify_evidence.py','--root','calibration_extension','--manifest','ARTIFACT_SHA256SUMS.txt']),
        ('complete_paired_arrays',['calibration_extension/verify_public_wcl_extension.py','--root','calibration_extension']),
        ('reporting_tables',['scripts/check_s4_reporting.py']),
        ('s8_release_metadata',['scripts/check_s8_release_metadata.py']),
        ('integrity_after',['verify_evidence.py']),
    ]
    outcomes=[]
    for label,cmd in commands:
        run=subprocess.run([sys.executable]+cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (out/(label+'.txt')).write_text(run.stdout)
        outcomes.append({'check':label,'returncode':run.returncode,'log':label+'.txt'})
        print(label+': '+('PASS' if run.returncode==0 else 'FAIL'),flush=True)
    after=hashlib.sha256(mf.read_bytes()).hexdigest()
    ok=all(x['returncode']==0 for x in outcomes) and before==after
    (out/'RELEASE_CHECK.json').write_text(json.dumps({'status':'PASS' if ok else 'FAIL','checks':outcomes,'manifest_unchanged':before==after,'manifest_sha256':after,'scope':'Integrity, stored arrays, scalar/geometry/document support and saved coordinate sources; no new producer run, fit, bootstrap or raw CSV-JSON join.'},indent=2)+'\n')
    raise SystemExit(0 if ok else 1)
if __name__=='__main__':main()
