#!/usr/bin/env python3
"""Read-only S5 source/binding and S4-preservation checks; no experiment rerun.
Optional --pdf-dir verifies the separately delivered PDFs against their binding.
"""
from pathlib import Path
import argparse,hashlib,json,re

def require(ok,message):
    if not ok: raise ValueError(message)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def expanded(path):
    def read_input(match):
        raw=match.group(1); rel=raw if raw.endswith('.tex') else raw+'.tex'
        p=(path.parent/rel).resolve()
        require(p.is_relative_to(path.parent.resolve()),'Unsafe source input')
        return p.read_text(encoding='utf-8')
    return re.sub(r'\\input\{([^}]+)\}',read_input,path.read_text(encoding='utf-8'))
def tables(text):
    return [re.findall(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?',m.group(0)) for m in re.finditer(r'\\begin\{(tabularx|tabular|longtable)\}.*?\\end\{\1\}',text,re.S)]
def declaration(text):
    a=text.index('During this study and preparation of the manuscript, the authors used')
    b=text.index('the manuscript and supplementary material.',a)+len('the manuscript and supplementary material.')
    return text[a:b].replace('’',"'")
def check(root,pdfs=None):
    exp=json.loads((root/'results/s5/DOCUMENT_EXPECTATIONS.json').read_text())
    keep=json.loads((root/'results/s5/PRESERVED_S4_FILES.json').read_text())
    binding=json.loads((root/'DOCUMENT_BINDING.json').read_text())
    for rel,expected in keep['expected_sha256'].items():
        require(digest(root/rel)==expected,'Protected S4 input changed: '+rel)
    for rel,expected in binding['current_source_dependencies'].items():
        require(digest(root/rel)==expected,'Current document dependency changed: '+rel)
    counts={}
    for item in binding['documents']:
        doc=item['document'];p=root/item['source'];text=expanded(p)
        require(digest(p)==item['source_sha256'],'Source binding '+doc)
        require(tables(text)==exp[doc]['numeric_table_tokens'],'Numerical table values changed '+doc)
        require(declaration(text)==exp[doc]['ai_text'],'Approved AI declaration changed '+doc)
        require(exp['contributions_latex'] in text,'Approved contributions changed '+doc)
        require(exp[doc]['title'] in text,'Title mismatch '+doc)
        require('No funding was received for this work.' in text,'Funding mismatch')
        require('None of the authors have a conflict of interest to disclose.' in text,'COI mismatch')
        require('PAPERB_SENSORS_EVIDENCE_v1.1.0_S5_300926.zip' in text,'Evidence filename mismatch')
        require('CLAIM_TO_ARTIFACT_SENSORS_S4.csv' not in text,'Stale active index')
        require('largest early' not in text.lower(),'Unspecified maximum remains')
        require('stable output' not in text.lower(),'Aggregate-error wording remains ambiguous')
        require('calibration transmitter truth' not in text,'Unsupported transmitter-truth label')
        if doc=='main':
            require('vkjha@bitmesra.ac.in' in text,'Confirmed email absent')
            require(text.index(r'\label{sec:pairedresults}')<text.index(r'\label{sec:weight}') if r'\label{sec:weight}' in text else text.index(r'\label{sec:pairedresults}')<text.index('What Refitting Changes'),'Result order')
            require(text.index('What Refitting Changes')<text.index(r'\label{sec:load}'),'Load context order')
            require(text.index('{paired_calibration_32_fields.pdf}')<text.index('{Fig1_Corruption_Load_Surface.pdf}'),'Figure order')
            require('symmetric-logarithmic' in text,'Scale caption missing')
            require('Her research interests' not in text and 'His research interests' not in text,'Biography wording')
        else:
            visible=re.sub(r'\\label\{[^}]+\}|\\includegraphics(?:\[[^]]*\])?\{[^}]+\}','',text)
            require('two-population' not in visible.lower(),'Mixed-error label mismatch')
            require('post-failure cause diagnostic' not in visible.lower(),'Cause label mismatch')
            require('positive harms' in text and 'positive helps' in text,'Contrast sign clarification missing')
            require(r'\shortstack{Controls with error\\above rotation}' in text,'Control-count heading missing')
        if pdfs is not None:
            require(digest(pdfs/item['delivered_pdf'])==item['pdf_sha256'],'Delivered PDF binding mismatch '+doc)
        counts[doc]=len(tables(text))
    return {'status':'PASS','protected_S4_files':len(keep['expected_sha256']),'source_dependencies':len(binding['current_source_dependencies']),'numeric_tables':counts,'approved_declarations_checked':True,'title_email_result_order_checked':True,'delivered_PDF_hashes_checked':pdfs is not None,'new_experiment':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--pdf-dir',type=Path);a=p.parse_args()
    print(json.dumps(check(a.root.resolve(),a.pdf_dir),indent=2))
if __name__=='__main__': main()
