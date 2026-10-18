"""Relocation smoke check and exact inverse-transform comparison; no rerun."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile
from portable_paths import portable_preflight,resolve_bound_path

P=Path(__file__).resolve().parent
original=(P/'run_finite_diagnostics.py').read_text()
derived=(P/'run_finite_diagnostics_portable.py').read_text()
header='# Portable derived version: only path preflight, provenance and CLI differ.\n# Original locked producer remains run_finite_diagnostics.py.\n'
assert derived.startswith(header)
back=derived[len(header):]
back=back.replace('from __future__ import annotations\nfrom portable_paths import portable_preflight\n',
                  'from __future__ import annotations\n',1)
old="""    protocol_path = ROOT/'FINITE_DIAGNOSTIC_PROTOCOL.json'
    protocol = json.loads(protocol_path.read_text())
    lock = json.loads((ROOT/'FINITE_DIAGNOSTIC_LOCK.json').read_text())
    assert sha(protocol_path) == lock['protocol_sha256']
    for item in protocol['bindings']:
        assert sha(item['path']) == item['sha256'], item['path']
"""
new="""    protocol_path = ROOT/'FINITE_DIAGNOSTIC_PROTOCOL.json'
    protocol = portable_preflight(ROOT)
"""
assert new in back;back=back.replace(new,old,1)
new="    receipt={'status':'completed','protocol_sha256':sha(protocol_path),'source_sha256':sha(__file__),\n        'portable_execution':protocol['_portable_execution'],"
old="    receipt={'status':'completed','protocol_sha256':sha(protocol_path),'source_sha256':sha(__file__),"
assert new in back;back=back.replace(new,old,1)
new="""if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Portable derived runner; original locked producer is preserved.')
    parser.add_argument('--verify-only', action='store_true', help='Verify original hashes and explicit path mapping without scientific calculations.')
    args = parser.parse_args()
    if args.verify_only:
        protocol = portable_preflight(ROOT)
        print(json.dumps({'status':'verified', 'scientific_reductions_executed':False,
                          'portable_execution':protocol['_portable_execution']}, indent=2))
    else:
        run()
"""
assert new in back;back=back.replace(new,"if __name__=='__main__':\n    run()\n",1)
assert back==original,'Derived producer contains an undisclosed calculation change'
verified=portable_preflight(P)
for bad in ['/etc/passwd','/workspace/scratch/c3111535193a/other/file',
            '/workspace/scratch/c3111535193a/paperb_execution_20261015/../../outside']:
    try:resolve_bound_path(bad,P.parent.parent)
    except ValueError:pass
    else:raise AssertionError('Unrecognized/traversing path was accepted')
qa=P/'qa';qa.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='portable_smoke_',dir=qa) as td:
    extraction=Path(td).resolve();target=extraction/'paperb_revision_20261016/theory'
    target.mkdir(parents=True)
    protocol=json.loads((P/'FINITE_DIAGNOSTIC_PROTOCOL.json').read_text())
    for binding in protocol['bindings']:
        source=Path(verified['_portable_execution']['recorded_to_resolved_paths'][binding['path']])
        destination=resolve_bound_path(binding['path'],extraction)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
    for name in ['FINITE_DIAGNOSTIC_PROTOCOL.json','FINITE_DIAGNOSTIC_LOCK.json',
                 'portable_paths.py','run_finite_diagnostics_portable.py']:
        shutil.copyfile(P/name,target/name)
    proc=subprocess.run([sys.executable,str(target/'run_finite_diagnostics_portable.py'),'--verify-only'],
                        check=True,capture_output=True,text=True)
    relocated=json.loads(proc.stdout)
    assert relocated['status']=='verified' and relocated['scientific_reductions_executed'] is False
    assert relocated['portable_execution']['extraction_root']==str(extraction)
    assert all(Path(x).is_relative_to(extraction) for x in relocated['portable_execution']['recorded_to_resolved_paths'].values())
    relocated_binding_count=relocated['portable_execution']['verified_original_bindings']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'status':'passed','original_protocol_unchanged':True,
        'original_locked_producer_sha256':sha(P/'run_finite_diagnostics.py'),
        'exact_inverse_transform_matches_original':True,
        'allowed_changes':['Explicit two-prefix path preflight','Portable execution provenance','Verify-only CLI'],
        'separate_relocation_original_bindings_verified':relocated_binding_count,
        'unrecognized_and_traversing_paths_rejected':True,'scientific_reductions_rerun':False,
        'files':{name:sha(P/name) for name in ['portable_paths.py','run_finite_diagnostics_portable.py',
                                           'verify_portability.py']}}
(P/'PORTABLE_VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
