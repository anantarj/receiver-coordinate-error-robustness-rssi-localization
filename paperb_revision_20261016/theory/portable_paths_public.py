"""Resolve only the two explicit original Paper B archive roots.

This is not a filesystem redirect. Original protocol bytes and bindings remain
unchanged. A portable derived producer calls this preflight before calculations.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

PREFIXES = (
    ("/workspace/scratch/c3111535193a/paperb_execution_20261015/", "paperb_execution_20261015"),
    ("/workspace/scratch/c3111535193a/paperb_revision_20261016/", "paperb_revision_20261016"),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_bound_path(recorded_path, extraction_root):
    """Explicit prefix substitution with traversal and symlink-escape checks."""
    if not isinstance(recorded_path, str):
        raise ValueError("Protocol paths must be strings")
    extraction_root = Path(extraction_root).resolve()
    for prefix, dirname in PREFIXES:
        if recorded_path.startswith(prefix):
            suffix = recorded_path[len(prefix):]
            parts = PurePosixPath(suffix).parts
            if not suffix or suffix.startswith('/') or '..' in parts:
                raise ValueError("Invalid suffix under an allowed archive root")
            expected_root = (extraction_root / dirname).resolve()
            if not expected_root.is_relative_to(extraction_root):
                raise ValueError("Archive root resolves outside the extraction directory")
            path = expected_root.joinpath(*parts).resolve()
            if not path.is_relative_to(expected_root):
                raise ValueError("Resolved bound path escapes its known archive root")
            return path
    raise ValueError("Path does not begin with either allowed original Paper B prefix")


def portable_preflight(theory_directory):
    theory_directory = Path(theory_directory).resolve()
    if theory_directory.name != 'theory' or theory_directory.parent.name != 'paperb_revision_20261016':
        raise ValueError("Keep the paperb_revision_20261016/theory directory layout")
    extraction_root = theory_directory.parent.parent
    protocol_path = theory_directory / 'FINITE_DIAGNOSTIC_PROTOCOL.json'
    lock_path = theory_directory / 'FINITE_DIAGNOSTIC_LOCK.json'
    protocol = json.loads(protocol_path.read_text())
    lock = json.loads(lock_path.read_text())
    if sha(protocol_path) != lock['protocol_sha256']:
        raise ValueError("Original protocol bytes do not match the original lock")
    binding_map = {}
    withheld = []
    exclusions = {x['path']: x['sha256'] for x in json.loads(
        (extraction_root/'PUBLIC_DOCUMENT_EXCLUSIONS.json').read_text())['files']}
    for binding in protocol['bindings']:
        resolved = resolve_bound_path(binding['path'], extraction_root)
        rel = str(resolved.relative_to(extraction_root))
        if rel == 'paperb_revision_20261016/theory/THEORY_EXTENSION.tex':
            if exclusions.get(rel) != binding['sha256']:
                raise ValueError('Withheld proof binding does not match the original lock')
            withheld.append({'path': binding['path'], 'sha256': binding['sha256']})
            continue
        if sha(resolved) != binding['sha256']:
            raise ValueError(f"Bound file hash mismatch: {resolved}")
        binding_map[binding['path']] = str(resolved)
    answer = copy.deepcopy(protocol)
    for key in ('input_path', 'primary_array_path'):
        if protocol[key] not in binding_map:
            raise ValueError(f"Numerical input missing from original binding list: {key}")
        answer[key] = binding_map[protocol[key]]
    answer['_portable_execution'] = {
        'mode': 'public_evidence_known_prefix_mapping',
        'withheld_document_bindings_not_reverified': withheld,
        'extraction_root': str(extraction_root),
        'original_protocol_sha256': sha(protocol_path),
        'verified_original_bindings': len(binding_map),
        'recorded_to_resolved_paths': binding_map,
        'locked_calculation_producer': str(theory_directory / 'run_finite_diagnostics.py'),
        'locked_calculation_producer_sha256': sha(theory_directory / 'run_finite_diagnostics.py'),
        'path_helper_sha256': sha(Path(__file__)),
        'numerical_calculation_modified': False,
    }
    return answer
