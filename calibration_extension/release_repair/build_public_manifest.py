#!/usr/bin/env python3
"""Explicit release-build command; never called by the read-only verifier.

A previous manifest and exact authorized change/addition lists are mandatory.
Dry-run is default. This writes only PUBLIC_RELEASE_SHA256SUMS.txt with --write.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from verify_evidence import parse_manifest, inventory, sha256


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--previous-manifest',type=Path,required=True)
    p.add_argument('--change-plan',type=Path,required=True,
                   help='JSON with exact approved_changes and approved_additions paths')
    p.add_argument('--write',action='store_true')
    a=p.parse_args();root=a.root.resolve();target=root/'PUBLIC_RELEASE_SHA256SUMS.txt'
    previous=a.previous_manifest.resolve()
    if previous==target:
        p.error('Keep the previous manifest outside the new release; do not overwrite the baseline record')
    old=parse_manifest(root,previous)
    plan=json.loads(a.change_plan.read_text())
    allowed_changed=set(plan['approved_changes']);allowed_new=set(plan['approved_additions'])
    actual=inventory(root,target)
    missing=set(old)-actual
    changed={n for n in set(old)&actual if sha256(root/n)!=old[n]}
    added=actual-set(old)
    problems=[]
    if missing:problems.append('Missing inherited files: '+', '.join(sorted(missing)))
    if changed-allowed_changed:problems.append('Unauthorized changes: '+', '.join(sorted(changed-allowed_changed)))
    if added-allowed_new:problems.append('Unauthorized additions: '+', '.join(sorted(added-allowed_new)))
    if problems:
        print('\n'.join(problems),file=sys.stderr);return 1
    # Every current byte is covered after the explicitly authorized transition.
    text=''.join(sha256(root/n)+'  '+n+'\n' for n in sorted(actual))
    if a.write:
        temp=target.with_name(target.name+'.tmp')
        if temp.exists():p.error('Temporary manifest already exists; inspect it before retrying')
        temp.write_text(text,encoding='utf-8');temp.replace(target)
    print(json.dumps({'status':'MANIFEST_WRITTEN' if a.write else 'DRY_RUN_VALIDATED',
        'previous_manifest_sha256':sha256(previous),'changed':sorted(changed),'added':sorted(added),
        'files':len(actual),'writes_performed':a.write},indent=2))
    return 0

if __name__=='__main__':sys.exit(main())
