#!/usr/bin/env python3
"""Read-only hash/coverage verification of an explicitly versioned package.

No hash is generated or updated by this verifier. Use a separate, reviewed
release-build operation to change a manifest after an intentional revision.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys

MANIFESTS = ('PUBLIC_RELEASE_SHA256SUMS.txt', 'EVIDENCE_SHA256SUMS.txt',
             'provenance/SHA256SUMS.txt')
IGNORED = {'.git', '__pycache__', '.venv', 'venv'}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def parse_manifest(root: Path, manifest: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(manifest.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', line)
        if match is None:
            raise ValueError(f'Malformed manifest line {number}')
        value, original = match.groups()
        path = PurePosixPath(original)
        if path.is_absolute() or '..' in path.parts or '\\' in original or path.as_posix() == '.':
            raise ValueError(f'Unsafe path on line {number}')
        # ./file and file identify the same member. Normalize before checking
        # duplicates and comparing manifest coverage with the actual inventory.
        name = path.as_posix()
        resolved = (root / name).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f'Path escapes package: {name}')
        if resolved == manifest:
            raise ValueError('A checksum manifest cannot contain its own hash')
        if name in entries:
            raise ValueError(f'Duplicate normalized path: {name}')
        entries[name] = value.lower()
    if not entries:
        raise ValueError('Empty manifest')
    return entries


def inventory(root: Path, manifest: Path) -> set[str]:
    out = set()
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if any(part in IGNORED for part in rel.parts) or path.suffix == '.pyc' or path.name == '.DS_Store':
            continue
        if path.is_file() and path.resolve() != manifest:
            if not path.resolve().is_relative_to(root):
                raise ValueError(f'File escapes package: {rel.as_posix()}')
            out.add(rel.as_posix())
    return out


def verify(root: Path, manifest: Path) -> tuple[int, int, list[str]]:
    entries = parse_manifest(root, manifest)
    good = 0
    errors = []
    for name, expected in entries.items():
        p = root / name
        if not p.is_file():
            errors.append('MISSING ' + name)
        elif sha256(p) != expected:
            errors.append('MISMATCH ' + name)
        else:
            good += 1
    errors.extend('UNLISTED ' + name for name in sorted(inventory(root, manifest) - set(entries)))
    return good, len(entries), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--manifest', type=Path, help='Manifest path relative to package root')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.manifest is not None:
        manifest = (root / args.manifest).resolve()
        if not manifest.is_relative_to(root):
            parser.error('Manifest must be within the package')
    else:
        found = [root/n for n in MANIFESTS if (root/n).is_file()]
        if len(found) != 1:
            parser.error('Exactly one recognized manifest is required; use --manifest to disambiguate')
        manifest = found[0].resolve()
    try:
        good, total, errors = verify(root, manifest)
    except (OSError, ValueError) as exc:
        print(f'STATUS: FAIL\n{exc}', file=sys.stderr)
        return 2
    print(f'Manifest: {manifest.relative_to(root)}')
    print(f'Verified: {good}/{total} files')
    for e in errors:
        print(e)
    print('STATUS: ' + ('INCOMPLETE_OR_MODIFIED' if errors else 'PACKAGE_INTEGRITY_PASS'))
    if not errors:
        print('Integrity only; not proof of scientific validity, independent replication or author approval.')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
