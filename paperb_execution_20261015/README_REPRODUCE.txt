PAPER B: BROADER VALIDATION, 15 OCTOBER 2026

This is an additive scientific evidence package. It does not replace the frozen
v1.1.0 baseline or PAPERB_REPRODUCIBILITY_v1.2.0.zip. The revised manuscript
continues to use those earlier results, whose exact archive identities are in
Supplement S8. This package supplies the additional matched WCL/RSS-NLS study,
the four spatial-fold calibration-budget study, and the computational tests accompanying the conditional RSS-NLS
residual-flattening analysis. It is not a public repository release or a new DOI.

The package directory is paperb_execution_20261015. All commands below run
inside that directory. Use a disposable COPY for any replay: several original
verification scripts write their receipts, whose historical bytes are bound by
the execution lock. Do not overwrite the preserved evidence or recreate its
lock.

EVIDENCE ROUTES

1. Integrity and interpretation, without rerunning an estimator:
   Read protocol/EXECUTION_LOCK.json, protocol/ANALYSIS_SPECIFICATION.json,
   inputs/INPUT_REGISTRY.json, receipts/PRIMARY_RUN_RECEIPT.json,
   results/analysis/SUMMARY.json and the numerical-audit receipts. The lock was
   created locally before these new comparisons, with earlier WCL outcomes
   already known. It is not external preregistration.

2. Recalculate scientific summaries from preserved predictions:
   python3 src/analyze_studies.py
   The program checks the execution lock and all producing array identities,
   then writes results/analysis/. It retains scheduled/finite denominators and
   keeps quantile differences separate from quantiles of paired differences.

3. Replay the finite estimators from prepared, locked inputs:
   In a disposable copy, remove only results/shards/, results/arrays/ and the
   copy's receipts/PRIMARY_RUN_RECEIPT.json and PRIMARY_PROGRESS.json, then run:
   OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
     python3 src/run_studies.py --workers 6 --chunk 32
   python3 src/analyze_studies.py
   Every prescribed start runs. Exact-identical inputs can reuse a computed
   prediction, with all scheduled outputs retained. Repeated evaluations are
   not independent observations. A finite prediction is not proof of local or
   global convergence. Shard resume is provenance-checked.

4. Reproduce the prespecified numerical spot checks:
   In the disposable copy remove results/numerical_audits/ and its corresponding
   numerical-audit progress/receipt files before running:
   OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
     python3 src/run_numerical_audits.py --workers 6
   The 376 scheduled cells and escalation rule were fixed before comparison.
   Audited outputs do not replace the primary estimates. Numerically guarded
   objective-gap calculations are not directed-rounding proofs, positional
   uniqueness certificates or localization-accuracy guarantees.

5. Independently reconstruct inputs from the raw observation source:
   Obtain lorawan_antwerp_2019_dataset.csv from the original dataset release,
   DOI 10.5281/zenodo.3904158. Required SHA-256:
   870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446
   In a disposable directory place a COPY of this evidence directory alongside
   paperb_development_20261015/inputs/lorawan_antwerp_2019_dataset.csv. Then run
   python3 tests/test_input_contract.py inside the evidence copy. That script
   independently checks all rows, splits, calibration records, selections,
   budgets and 6,061 receiver-field fits against the raw CSV. It rewrites the
   copy's INPUT_REVIEW receipt; restore the preserved receipt before using that
   same copy for a locked production replay. The alternative preparation script
   accepts --csv, --map-official and --map-r29 for reconstruction in a separate
   workspace. Do not run preparation over locked original inputs.

The raw CSV and earlier large archives are not duplicated here. The inputs/
directory DOES include derived RSSI/reference-coordinate slices required to
replay these new studies, with original source-row identifiers and attribution.
The two .npz.5.tmp files were leftover input-preparation fragments inadvertently
included in the input manifest before locking. They are retained solely to
preserve that historical lock; no study loads them. The pre-lock truncated
NE-all archive is retained in receipts/ for the recorded packaging correction;
the corrected active input was independently verified before any study ran.

SCIENTIFIC BOUNDARIES

Both studies reuse one Antwerp campaign. R29 is a historical-map sensitivity
analysis, not a second deployment or surveyed truth. Spatial quadrants and the
250-m exclusion buffer do not establish stochastic independence. The ten-reception fits
used 297-319 distinct labelled messages in these realizations.
The scenario reuses historical calibration records after a metadata change;
it does not simulate physical receiver motion. The 5-km stress is a gross
metadata discrepancy. Targets, directions, calibration policy, receiver roster
and the fixed exponent n=4.7 delimit the finite results.

The proof concerns the specified mathematical RSS-residual objective and exact
global minimizer sets. Primary empirical outputs come from a finite multistart
algorithm. These are explicitly different claims. Smaller prediction movement,
lower localization error, unchanged model rankings and output availability are
also different quantities.

PUBLIC DISTRIBUTION
Current manuscript PDFs, their sources and prose fragments are private.
Numerical methods and analysis specifications are retained. See ../README.md
for the exact evidence-only scope, public adapters, and dependency archive.
NumPy, SciPy, pandas and pyproj are required; figure scripts use matplotlib.
