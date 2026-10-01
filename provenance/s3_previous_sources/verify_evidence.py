#!/usr/bin/env python3
"""Read-only integrity verification for the released package (standard library only)."""
from pathlib import Path, PurePosixPath
import argparse,hashlib,sys

def verify(root):
    root=Path(root).resolve()
    manifest=root/'PUBLIC_RELEASE_SHA256SUMS.txt'
    if not manifest.is_file():raise ValueError('Missing PUBLIC_RELEASE_SHA256SUMS.txt')
    expected={}
    for number,line in enumerate(manifest.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():continue
        parts=line.split(None,1)
        if len(parts)!=2 or len(parts[0])!=64 or any(c not in '0123456789abcdef' for c in parts[0]):
            raise ValueError('Malformed manifest line '+str(number))
        name=parts[1].lstrip('*')
        while name.startswith('./'):name=name[2:]
        q=PurePosixPath(name)
        if q.is_absolute() or '..' in q.parts or not name or '\\' in name:
            raise ValueError('Unsafe manifest path: '+name)
        normalized=q.as_posix()
        if normalized in expected:raise ValueError('Duplicate manifest path: '+normalized)
        expected[normalized]=parts[0]
    errors=[]
    for name,wanted in expected.items():
        p=root/name
        if p.is_symlink():errors.append('symlink '+name);continue
        try:p.resolve().relative_to(root)
        except ValueError:errors.append('escape '+name);continue
        if not p.is_file():errors.append('missing '+name);continue
        if hashlib.sha256(p.read_bytes()).hexdigest()!=wanted:errors.append('changed '+name)
    actual=set()
    for p in root.rglob('*'):
        rel=p.relative_to(root)
        if '.git' in rel.parts or '__pycache__' in rel.parts:continue
        if p.is_symlink():errors.append('symlink '+rel.as_posix());continue
        if p.is_file() and p.name!='PUBLIC_RELEASE_SHA256SUMS.txt':actual.add(rel.as_posix())
    errors+=['unlisted '+s for s in sorted(actual-set(expected))]
    if errors:raise ValueError('\n'.join(errors))
    print('PASS:',len(expected),'manifested files verified; manifest unchanged.')
    return len(expected)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).resolve().parent));args=ap.parse_args()
    try:verify(args.root)
    except (ValueError,OSError) as exc:print('FAIL:',exc,file=sys.stderr);raise SystemExit(1)
