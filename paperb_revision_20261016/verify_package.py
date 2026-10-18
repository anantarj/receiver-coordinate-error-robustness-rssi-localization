#!/usr/bin/env python3
"""Verify the delivered manifest without modifying evidence or expected hashes."""
from pathlib import Path
import hashlib, json, sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'FILE_MANIFEST.json').read_text())
fail=[]
for entry in manifest['files']:
    rel=Path(entry['path'])
    if rel.is_absolute() or '..' in rel.parts:
        fail.append({'path':str(rel),'reason':'unsafe manifest path'});continue
    p=root/rel
    if not p.is_file():
        fail.append({'path':str(rel),'reason':'missing'});continue
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    if p.stat().st_size!=entry['bytes'] or digest!=entry['sha256']:
        fail.append({'path':str(rel),'reason':'size or hash mismatch'})
print(json.dumps({'status':'PASS' if not fail else 'FAIL',
                  'checked_files':len(manifest['files']),'failures':fail},indent=2))
sys.exit(bool(fail))
