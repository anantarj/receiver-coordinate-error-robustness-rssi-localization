PAPER B ADDITIVE CANDIDATE RECOVERY — 16 OCTOBER 2026

No original primary prediction, source, input or numerical result is changed.
RECOVERY_LOCK.json binds code, numerical inputs, primary expectations, mappings,
and protocol before pilot/full candidate recovery. The unchanged original
solver is imported; a read-only observer retains its _local_search return.

inputs/UNIQUE_INPUTS.npz
  Rows indexed by input_id. anchors_m [U,10,2], rss_dbm [U,10],
  intercepts_dbm [U,10], receiver_count [U]. First receiver_count entries valid;
  padding is NaN. input_sha256 gives exact-input identity. n=4.7,d0_m=1.
  No query reference positions, calibration labels, source identities or WCL
  estimates enter this solver-input file.

inputs/EXPECTED_PRIMARY.npz
  Position, objective, status and old competitive diameter for each global
  input_id, from its first occurrence in the immutable primary results.
  Original identical-input expectations are checked for consistency.

mappings/<original-block>.npz
  input_id[field,policy,query], source_rows[query], field_D_m[field],
  field_draw[field], field_target_count[field]. policy0=frozen,1=refit.
  Field0 is the own baseline. Scoring references remain only in the original
  inputs/blocks/<block>.npz query_xy_m file and are not given to the solver.

candidates/*.npz
  Include BOTH pilot_*.npz and shard_*.npz files. Each global input appears
  once. Names index the work-list offset, not a contiguous input_id interval.
  Always use each shard's explicit input_id to scatter into global arrays.

  candidate_position_m [B,39,2]: absolute UTM positions.
  candidate_local_position_m [B,39,2]: exact local coordinates captured from
    the original algorithm; search_origin_m transforms to absolute positions.
  candidate_objective_db2 [B,39]: objective recomputed at captured local point.
  candidate_recorded_objective_db2: original initial/endpoint/incumbent value.
  candidate_valid: valid finite candidate slots. NaN padding is not a failure.
  candidate_kind: 0 prescribed initial,1 local endpoint or recorded fallback,
    2 explicit selected incumbent. Incumbent repeats its original candidate.
  candidate_start_index: original start identity; starts preserve original order.
  candidate_local_status/converged/exception: meaningful for kind1 only.
    Kind0/kind2 are not additional local optimizations.
  candidate_count: finite candidate slots; raw duplicates are retained.
  selected_candidate_slot: explicit incumbent slot.
  selected_position_m/objective_db2/source_kind/start_index: unchanged solver
    choice, whose values are checked against the frozen primary expectation.
  original_status,local_runs,local_converged,local_nfev_total: replay diagnostics.
  position_discrepancy_m,objective_discrepancy_db2: reproduction checks.
  objective_recompute_discrepancy_db2: maximum candidate recomputation difference.
  recovered_endpoint_diameter_m: original solver's endpoint-only diagnostic.

Candidate sets use valid objectives <= their finite minimum + delta for
delta=.01(primary),.001,.0001 dB^2. These are found candidates, not complete
near-optimal regions or confidence sets. Use local coordinates for precise
objective checks and absolute coordinates for localization-reference scoring.
No reference coordinate may select a production candidate.

receipts/PILOT_RECEIPT.json and RUN_RECEIPT.json together cover the whole run.
Per-shard JSON receipts bind NPZ bytes. Hashes and original invariance are
verified before and after each full command. Progress receipts are temporary
status summaries, not a substitute for final completeness/integrity checks.

Reproduce in a separate copy; prepare does not overwrite an existing lock.
  python recover_candidates.py prepare
  python recover_candidates.py pilot --workers 4
  python recover_candidates.py run --workers 6
The run command resumes verified completed shards. BLAS threads are fixed to1.

Strong numerical-bound audits are a separate operation and do not replace
the primary candidate pools or primary estimator outputs.

COMPLETED RECOVERY AND FOLLOW-UP
119045 distinct numerical inputs; 195200 original stored contexts.
934 recovery shards (4 pilot and 930 full-run); 3358385 retained raw candidates.
All original selected positions/objectives reproduced exactly.
398 targeted audits; 104 escalated; 502 stages; 33555 stronger candidate records.
Numerical final-stage gap <= .01 dB2 for 141 inputs; 257 gaps remain unresolved.
All original bound files and 18 primary arrays remain unchanged.

targeted_audits/input_<input_id>_stage<stage>.npz
  scalar input_id,stage,search_origin_m; variable C candidate records.
  candidate_local_position_m[C,2],candidate_position_m[C,2],
  candidate_objective_db2[C],candidate_recorded_objective_db2[C].
  All rows finite; no padded candidate_valid mask.
  candidate_kind:0 stronger initial,1 endpoint/fallback,2 primary incumbent,
    3 strictly improving objective evaluation,4 final audit incumbent.
  candidate_start_index/local_status/local_converged have local-run meaning
    for kind1. Strictly improving bound-centre evaluations are included;
    not every evaluated bound centre is retained.
  Matching stage JSON gives the unchanged audit's complete diagnostics.
  Per-input receipt gives stage count/checksums,best incumbent,and last-stage
    numerical gap. Last-stage gap is not automatically the best-stage gap.

Enhanced pool = recovered primary pool UNION every completed stronger-stage
pool, then objective-band filtering around the joint found minimum. An
original selected incumbent can lie outside a narrow enhanced band; do not
silently include it or replace the original primary estimator with a branch
chosen by reference-coordinate error. Exact duplicate candidate coordinates
may be collapsed for set arithmetic; keep the raw archival records intact.

results/RECOVERED_POOL_DIAGNOSTICS.npz
  input_id,bands_db2,diameter_m[3,U],minimum_objective_db2,
  raw_candidate_count. Bands are .01,.001,.0001dB2 in that order.
results/RECOVERED_DIAGNOSTIC_DISTRIBUTION.csv gives all-block and per-block
  thresholds; ALL_FLAGGED_STATE_REGISTER.csv contains 208 stored contexts.
  Its columns full_pool_diameter_001_db2_m,0001_db2_m,00001_db2_m respectively
  denote .01,.001,.0001dB2 bands (the decimal point is omitted in names).
results/TARGETED_AUDIT_STATE_REGISTER.csv gives 398 unique audited inputs
  and all associated contexts in a JSON-valued CSV column.
results/BRANCH_GEOMETRY_DIAGNOSTICS.json/.csv describes three selected
  examples; it is not a representative-sample prevalence estimate.

Read-only verification of the delivered outputs (no optimizer called):
  python verify_recovery.py
  python verify_targeted_audits.py
The independent receipts validate COMPLETE status, full mapped coverage,
artifact hashes, local and absolute-coordinate residual calculations,
original prediction equality, and original-file preservation. Absolute UTM
rounding differences are explicitly separate from exact local-point checks.
report_recovery_diagnostics.py, report_targeted_audits.py, and
inspect_branch_geometry.py reproduce descriptive summaries without a solver.

For a fresh rerun, preserve the sibling layout in which paperb_execution_20261015
is adjacent to paperb_revision_20261016. Create a fresh numerical directory
containing these unmodified scripts, rather than overwriting this evidence.
After recovery preparation, prepare_targeted_audit.py base fixes the mandatory
and coverage schedule; after recovered candidates exist,
prepare_targeted_audit.py complete admits new flags within the cap.
run_targeted_audits.py prepare binds the final schedule before
run_targeted_audits.py run --workers 4 executes it. Original source,
inputs, and results are read-only.
