PORTABLE REPLAY OF THE FINITE THEORY DIAGNOSTICS

Keep the two evidence directories beside each other under any extraction path:

  <extraction-root>/paperb_execution_20261015/
  <extraction-root>/paperb_revision_20261016/theory/

The original execution directory must contain the bound Study 1 primary input
and saved primary-array files. Together, the two directories must retain all
six original protocol-bound files and the original protocol/lock. These are original
evidence dependencies; the portable runner does not reconstruct missing inputs.

From the extraction root, first verify the exact original hashes and explicit
path mapping, without running the numerical reductions:

  python3 paperb_revision_20261016/theory/run_finite_diagnostics_portable.py --verify-only

To replay the diagnostic sweep in a DISPOSABLE COPY of the extracted evidence:

  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 paperb_revision_20261016/theory/run_finite_diagnostics_portable.py

This recomputes the diagnostic CSV/NPZ outputs and receipt in the copied theory
directory, preserving the original scientific calculation. It performs no
localization optimizations. Existing output files in that copy are replaced,
which is why the original released evidence should be retained separately.
NumPy is required. The original execution receipt reports its runtime; use the
same recorded numerical environment for a byte-comparison attempt. ZIP-member
timestamps and receipt timing/provenance can differ despite identical arrays.

The derived producer differs from the locked original only in explicit path
preflight, added portable provenance, and a verify-only command-line option.
The original protocol and run_finite_diagnostics.py are unchanged. The helper
recognizes exactly the two original /workspace/scratch/c3111535193a/ Paper B
directory prefixes and maps their suffixes to the corresponding directories
under the current extraction root. Other prefixes, traversal and paths escaping
those directories are rejected. Every original binding is verified before any
scientific calculation; no general filesystem redirect is installed.

Verification of portability itself:

  python3 paperb_revision_20261016/theory/verify_portability.py

This copies the bound dependencies into a temporary alternate extraction root,
runs the relocated verify-only preflight, checks rejection of unrelated and
traversing paths, and reverses the documented source transformations to verify
exact equality with the locked original calculation. It does not rerun the
scientific diagnostic sweep. PORTABLE_VERIFICATION.json records the result.
