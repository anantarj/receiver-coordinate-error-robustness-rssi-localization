#!/usr/bin/env python3
"""Read-only S8 release/DOI/document checks; no experiment rerun or DOI operation."""
from pathlib import Path
import argparse,hashlib,json,re,ast
from check_s5_documentation import expanded,tables,declaration

def require(ok,msg):
    if not ok: raise ValueError(msg)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def check(root,pdfs=None):
    exp=json.loads((root/'results/s8/S8_RELEASE_EXPECTATIONS.json').read_text())
    preserved=json.loads((root/'results/s8/PRESERVED_S7_FILES.json').read_text())
    # All S7 files not explicitly superseded remain byte-identical.
    for rel,sha in preserved['expected_sha256'].items():
        p=root/rel
        require(p.is_file(),'Missing preserved S7 file: '+rel)
        require(digest(p)==sha,'Protected S7 file changed: '+rel)
    for rel,record in preserved['superseded'].items():
        require(digest(root/record['preserved_path'])==record['sha256'],'Superseded S7 bytes changed: '+rel)
    binding=json.loads((root/'DOCUMENT_BINDING.json').read_text())
    require(binding['revision']=='S8','Document revision is not S8')
    require(binding['evidence_archive']==exp['archive'],'Evidence archive binding mismatch')
    require(binding.get('zenodo_doi')==exp['doi'],'Document binding DOI mismatch')
    # Validate source dependency pins and document-level invariants.
    for rel,sha in binding['current_source_dependencies'].items():
        require(digest(root/rel)==sha,'Current document dependency changed: '+rel)
    s5=json.loads((root/'results/s5/DOCUMENT_EXPECTATIONS.json').read_text())
    s6=json.loads((root/'results/s6/DOCUMENT_EXPECTATIONS.json').read_text())
    docs={x['document']:x for x in binding['documents']}
    main=expanded(root/docs['main']['source']); supp=expanded(root/docs['supplement']['source'])
    for doc,text in [('main',main),('supplement',supp)]:
        item=docs[doc]
        original=root/'provenance/s8_previous_metadata'/item['source']
        previous_text=original.read_text()
        expected_text=previous_text.replace(exp['previous_archive'],exp['archive']).replace(exp['previous_index'],exp['current_index'])
        require((root/item['source']).read_text()==expected_text,'Unexpected scientific-source delta: '+doc)
        require(digest(root/item['source'])==item['source_sha256'],'Source hash mismatch: '+doc)
        require(tables(text)==s5[doc]['numeric_table_tokens'],'Numerical table values changed: '+doc)
        require(declaration(text)==s5[doc]['ai_text'],'Approved AI declaration changed: '+doc)
        require(s5['contributions_latex'] in text,'Author Contributions changed: '+doc)
        require(s5[doc]['title'] in text,'Title mismatch: '+doc)
        require('No funding was received for this work.' in text,'Funding mismatch')
        require('None of the authors have a conflict of interest to disclose.' in text,'COI mismatch')
        require(exp['archive'] in text,'Current evidence filename absent: '+doc)
        require(exp['doi'] in text,'Reserved v1.1.0 DOI absent: '+doc)
        require(exp['baseline_doi'] in text,'Baseline DOI distinction absent: '+doc)
        if pdfs is not None:
            require(digest(Path(pdfs)/item['delivered_pdf'])==item['pdf_sha256'],'Delivered PDF mismatch: '+doc)
            require(digest(Path(pdfs)/item['source_zip']['filename'])==item['source_zip']['sha256'],'Delivered source ZIP mismatch: '+doc)
    # S6 scientific reporting requirements remain present.
    require(s6['main_constraints'] in main,'Explicit calibration constraints missing')
    require(s6['main_scope'] in main,'Calibration/weighting scope missing')
    require(s6['main_literature'] in main,'Focused literature comparison missing')
    require(s6['supp_constraints'] in supp and s6['supp_scope'] in supp,'Supplement calibration concordance missing')
    require('full-precision author-exported arrays and displayed to one decimal place' in supp,'S14.2 precision statement missing')
    require('S2 and main Figure 2 remain unchanged' in supp,'S16.2 main Figure 2 pointer missing')
    # Release metadata and citation identity.
    cff=(root/'CITATION.cff').read_text()
    require('version: "1.1.0"' in cff and f'doi: "{exp["doi"]}"' in cff,'CITATION.cff DOI/version mismatch')
    require(exp['title'] in cff,'CITATION.cff title mismatch')
    rel=json.loads((root/'RELEASE_INFO.json').read_text())
    require(rel['target_release']=='v1.1.0' and rel['zenodo_doi']==exp['doi'],'RELEASE_INFO DOI/tag mismatch')
    require(rel['baseline_zenodo_doi']==exp['baseline_doi'],'Baseline DOI missing in RELEASE_INFO')
    require(rel['evidence_archive']==exp['archive'],'RELEASE_INFO archive mismatch')
    doi_rec=json.loads((root/'results/s8/DOI_RESERVATION.json').read_text())
    require(doi_rec['reserved_zenodo_doi']==exp['doi'] and doi_rec['preceding_doi']==exp['baseline_doi'],'DOI reservation record mismatch')
    for relpath in ['README.md','START_HERE.md','ZENODO_NEXT_STEP.md']:
        t=(root/relpath).read_text()
        require(exp['doi'] in t and exp['baseline_doi'] in t,'DOI lineage missing in '+relpath)
    require((root/'results'/exp['current_index']).read_bytes()==(root/'results'/exp['previous_index']).read_bytes(),'Claim index contents changed')
    require(exp['current_index'] in (root/'results/README.md').read_text(),'Wrong active result index')
    for docpath in ['README.md','START_HERE.md','results/README.md']:
        t=(root/docpath).read_text()
        require('Current documents and archive are S6.' not in t,'Stale active revision label')
        require(not re.search(r'python3?\s+scripts/check_s[567]_(?:documentation|release_metadata)\.py',t),'Historical checker still advertised as current')
    # Calibration implementation remains exact and unconstrained as documented.
    record=json.loads((root/'results/s6/CALIBRATION_IMPLEMENTATION_CHECK.json').read_text())
    for f in record['source_functions']:
        p=root/f['path']; require(digest(p)==f['file_sha256'],'Inspected calibration/scoring source changed: '+f['path'])
        text=p.read_text(); nodes=[n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name==f['function']]
        require(len(nodes)==1,'Ambiguous inspected function')
        node=nodes[0]; segment=ast.get_source_segment(text,node)
        require(node.lineno==f['first_line'] and node.end_lineno==f['last_line'],'Source locator changed')
        require(hashlib.sha256(segment.encode()).hexdigest()==f['source_sha256'],'Inspected function body changed')
    return {
        'status':'PASS','revision':'S8','version':'1.1.0','reserved_zenodo_doi':exp['doi'],
        'baseline_doi':exp['baseline_doi'],'protected_S7_files':len(preserved['expected_sha256']),
        'numeric_tables':{'main':len(tables(main)),'supplement':len(tables(supp))},
        'doi_lineage_checked':True,'source_dependencies_checked':len(binding['current_source_dependencies']),
        'delivered_PDF_hashes_checked':pdfs is not None,
        'delivered_source_ZIP_hashes_checked':pdfs is not None,
        'exact_scientific_source_preservation_checked':True,
        'superseded_S7_files_preserved':len(preserved['superseded']),
        'new_experiment':False,
        'scope':'Release metadata, document binding, preserved science and DOI lineage; no new localization, fit, bootstrap, raw-data join or remote publication.'
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--pdf-dir',type=Path)
    a=ap.parse_args()
    print(json.dumps(check(a.root.resolve(),a.pdf_dir),indent=2))
if __name__=='__main__':main()
