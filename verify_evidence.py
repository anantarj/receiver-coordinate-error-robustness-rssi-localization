#!/usr/bin/env python3
"""Read-only integrity check: scientific review package or complete preparation archive."""
from pathlib import Path
import hashlib,re,sys
R=Path(__file__).resolve().parent
manifest=R/'EVIDENCE_SHA256SUMS.txt'
if not manifest.is_file():manifest=R/'provenance/SHA256SUMS.txt'
if not manifest.is_file():raise SystemExit('No package manifest found; extract the complete package first.')
errors=[];listed=set();n=0
for line in manifest.read_text().splitlines():
 expected,name=line.split('  ',1);p=Path(name)
 if not re.fullmatch(r'[0-9a-f]{64}',expected) or p.is_absolute() or '..' in p.parts:raise SystemExit('Unsafe manifest')
 if name in listed:raise SystemExit('Duplicate manifest path')
 listed.add(name)
 if not (R/p).is_file():errors.append('MISSING '+name);continue
 with (R/p).open('rb') as f:
  h=hashlib.sha256()
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 if h.hexdigest()!=expected:errors.append('MISMATCH '+name)
 else:n+=1
actual={p.relative_to(R).as_posix() for p in R.rglob('*') if p.is_file() and p!=manifest and not any(x in p.parts for x in ['.git','__pycache__','.venv','venv']) and p.suffix!='.pyc' and p.name!='.DS_Store'}
errors += ['UNLISTED '+p for p in sorted(actual-listed)]
print('Verified: %s/%s files'%(n,len(listed)))
for e in errors:print(e)
print('STATUS: '+('INCOMPLETE_OR_MODIFIED' if errors else 'REVIEW_EVIDENCE_INTEGRITY_PASS'))
if not errors:print('Integrity only: not final author approval, public publication, independent replication or all scientific criteria passing.')
sys.exit(bool(errors))
