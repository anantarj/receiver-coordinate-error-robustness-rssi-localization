#!/usr/bin/env python3
"""Read-only S6 document, calibration-source and preservation checks.
This checks saved source and outputs. It does not execute a new intercept fit or localization run.
"""
from pathlib import Path
import argparse,ast,hashlib,json,re
from check_s5_documentation import check as previous_check, expanded

def require(ok,msg):
    if not ok:raise ValueError(msg)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check(root,pdfs=None):
    inherited=previous_check(root,pdfs)
    exp=json.loads((root/'results/s6/DOCUMENT_EXPECTATIONS.json').read_text())
    keep=json.loads((root/'results/s6/PRESERVED_S5_FILES.json').read_text())
    for rel,sha in keep['expected_sha256'].items():
        require((root/rel).is_file(),'Missing preserved S5 file: '+rel)
        require(digest(root/rel)==sha,'Protected S5 file changed: '+rel)
    binding=json.loads((root/'DOCUMENT_BINDING.json').read_text())
    require(binding['revision']=='S6' and binding['evidence_archive']==exp['archive'],'S6 version mismatch')
    main=expanded(root/'document_sources/main/paper_b_sensors.tex')
    supp=expanded(root/'document_sources/supplement/paper_b_supplement_sensors.tex')
    require(exp['main_constraints'] in main,'Explicit calibration constraints missing')
    require(exp['main_scope'] in main,'Constrained calibration/weighting boundary missing')
    require(exp['main_literature'] in main,'Focused primary-literature comparison missing')
    require(exp['supp_constraints'] in supp and exp['supp_scope'] in supp,'Supplement calibration concordance missing')
    s142=supp.split('S14.2 Principal high-participation')[1].split('S14.3')[0]
    require('full-precision author-exported arrays and displayed to one decimal place' in s142,'Table S34 precision mismatch')
    require('displayed here at two decimals' not in s142,'Stale precision sentence')
    s162=supp.split('S16.2 Earlier 5-km fraction slice')[1].split('S16.3')[0]
    require('S2 and main Figure 2 remain unchanged' in s162,'Load surface figure pointer mismatch')
    require('S2 and Figure 1' not in s162,'Stale load figure reference')
    require(main.index('{paired_calibration_32_fields.pdf}')<main.index('{Fig1_Corruption_Load_Surface.pdf}'),'Main figure ordering changed')
    for text in [main,supp]:
        require(exp['archive'] in text,'Wrong accompanying archive')
        require('PAPERB_SENSORS_EVIDENCE_v1.1.0_S5_300926.zip' not in text,'Stale active evidence name')
    record=json.loads((root/'results/s6/CALIBRATION_IMPLEMENTATION_CHECK.json').read_text())
    for f in record['source_functions']:
        p=root/f['path'];require(digest(p)==f['file_sha256'],'Inspected calibration/scoring source changed: '+f['path'])
        text=p.read_text();nodes=[n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name==f['function']]
        require(len(nodes)==1,'Ambiguous inspected function')
        node=nodes[0];segment=ast.get_source_segment(text,node)
        require(node.lineno==f['first_line'] and node.end_lineno==f['last_line'],'Source locator changed')
        require(hashlib.sha256(segment.encode()).hexdigest()==f['source_sha256'],'Inspected function changed')
    d=record['paired_driver'];require(digest(root/d['path'])==d['sha256'],'Paired producer changed')
    # Match producer/evaluator identities against the original executed protocol.
    protocol=json.loads((root/'calibration_extension/protocol/PROTOCOL.json').read_text())
    for key,rel in [('harness','code/baseline_001_e123_pairfallback_040926.py'),('evaluator','code/deltamesh_antwerp_eval_v10_fixed_080826.py')]:
        require(digest(root/rel)==protocol['immutable_inputs'][key]['sha256'],'Execution protocol/source mismatch')
    return {'status':'PASS','S5_protected_files':len(keep['expected_sha256']),'inspected_functions':len(record['source_functions']),
        'figure_reference_checked':True,'precision_description_checked':True,'calibration_constraints_and_scope_checked':True,
        'focused_literature_paragraph_checked':True,'exact_evidence_filename_checked':True,'inherited_document_checks':inherited,
        'scope':'Static source identity and document/reporting consistency; no new calibration or localization execution.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--pdf-dir',type=Path);a=ap.parse_args()
    print(json.dumps(check(a.root.resolve(),a.pdf_dir),indent=2))
if __name__=='__main__':main()
