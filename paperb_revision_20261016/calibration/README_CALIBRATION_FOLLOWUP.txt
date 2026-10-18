PAPER B — CALIBRATION-QUALITY FOLLOW-UP

This directory is additive to paperb_execution_20261015. Original observations,
fits, numerical outputs, code and manuscripts are not changed. It implements
Section 3 of PAPERB_REVISION_PLAN_20261016.txt, after prior outcomes were known.
The procedure is a diagnostic follow-up, not external preregistration.

Scientific scope
---------------
1. All 18 original input blocks: frozen and unrestricted-fit RSS residuals at
   the held-out recorded reference positions for all fields and zero baselines.
   Primary reception population: original selected receptions of fixed query
   cohorts. Companion: all valid roster receptions of the SAME query rows.
   Neither is described as a census of all messages in the held-out region.
2. Four original spatial folds: disjoint 250-m fit/validation cells within the
   original training regions, retaining original rosters and query cohorts.
   Baseline and refit intercepts use only fitting records. A support-only hash
   allocation succeeds at the first predeclared salt; every roster receiver
   has at least ten fitting AND validation receptions in the realized split.
3. A single common intercept-shrinkage coefficient is selected per field from
   {0,.25,.5,.75,1} by equal-receiver validation MAE for BS14 and BS69. These
   changed metadata identities are known in the intervention; no fault detector
   is introduced. Unchanged receiver losses are invariant in the coefficient.
4. Only frozen, unrestricted and validation-selected intercept policies are
   localized. The original WCL and original finite RSS-NLS solver are retained.
   Complete observed initial/endpoint/incumbent candidates are now archived.

No threshold of absolute acceptable calibration quality is asserted. Relative
RSS loss changes do not certify coordinate correctness or positioning quality.
Validation loss chooses a policy; query RSS assesses it separately on previously
examined query cohorts. Fit/validation cells are disjoint, but adjacent cells
and campaign observations need not be statistically independent.

Files
-----
protocol/CALIBRATION_PROTOCOL.json fixes residual/partition/selection operations
before their new outcomes. SPLIT_SUPPORT_COUNTS.csv and SPLIT_FEASIBILITY.json
record support-only allocation. Original block hashes and raw CSV are bound.

inputs/blocks/study2_<fold>_fitval_all.npz mirrors the original input interface:
  reference_intercepts_dbm                 72 values, fit-only baseline
  field_refit_intercepts_dbm               9 x 72, fit-only unrestricted
  field_selected_intercepts_dbm            9 x 72, selected shrinkage
  field_selected_lambda                   9, including zero field lambda0
  query arrays/roster/coordinates          exact original bytes
  cal_* arrays                            fitting records only
  validation_source_rows                  separate validation row identities
  original_calibration_population_*       original parent training population

Additional validation NPZs retain receiver-level validation RSS/reference
records and all three policy residuals. Original all-training A0 is never used
in the new extension. Endpoint-selected policies use exact endpoint bytes.

results/ORIGINAL_RECEIVER_RESIDUALS.csv contains signed bias, MAE, absolute
quantiles, RMSE, count and zero-map differences for every receiver/field/policy.
Group and spatial CSVs preserve their different populations and aggregations.
results/LAMBDA_SELECTION_GRID.csv retains the complete five-coefficient grid.
results/CALIBRATION_POLICY_SELECTION.csv records all 36 zero/positive field rows.

Query candidate schema
----------------------
results/extension_query_arrays/ stores merged field x policy x query arrays,
with policies [frozen,refit,selected]. Query chunks have paired files under
extension_query_shards/ and extension_candidate_shards/.

nlls_input_sha256 provides an unambiguous exact-input key, using the same binary
serialization as numerical/recover_candidates.py. nlls_input_index is LOCAL to
its checkpoint shard and must not be treated as globally unique after merging.
The matching checkpoint name contains original query-index start and stop.

Candidate arrays contain every finite prescribed initial point, recorded finite
endpoint/fallback and explicit selected incumbent, up to39 slots per input.
Candidate kind0=initial,1=endpoint/fallback,2=explicitincumbent. Local coordinates
are retained to avoid global-to-local rounding during objective recomputation.
Recorded and recomputed objectives, status, convergence and exception fields
are retained. A read-only observer captures unchanged _local_search output and
returns it unchanged; no query truth or WCL prediction enters RSS-NLS starts.

Bands .01,.001,.0001 dB^2 select found candidates relative to the pool minimum.
They are neither global-optimality guarantees nor statistical confidence sets.
Candidate envelopes may be conservative under unconstrained per-query choices.
Exactly identical policy inputs have zero comparative effect under a consistent
input-to-output rule; identical baseline/current input movement is zero.

Reproduction
------------
Use a disposable copy; never rewrite locked originals. Set OPENBLAS_NUM_THREADS,
OMP_NUM_THREADS and MKL_NUM_THREADS to 1. Python 3.12/NumPy/SciPy/pandas environment
versions are recorded in the protocols/parent runtime. From the extraction
parent containing both dated roots, first change into the calibration directory:

  cd paperb_revision_20261016/calibration

Run the following relative commands from that directory. To invoke them from
elsewhere, use their complete paths; the scripts locate their data from __file__.
Preserve the sibling paperb_execution_20261015 directory. Retain the supplied
protocol and execution locks; do not regenerate them for replay.

  python src/calibration_quality.py feasibility
  python src/calibration_quality.py immediate
  python src/calibration_quality.py extension
  python src/verify_calibration.py
  python src/analyze_calibration.py calibration

The protocol command was executed once before outcomes. Query execution uses a
separate locked protocol and verified immutable checkpoint receipts:

  python src/run_extension_queries.py pilot --workers 1
  python src/run_extension_queries.py run --workers 4
  python src/verify_extension_queries.py
  python src/analyze_calibration.py queries
  python src/build_calibration_fragments.py
  python src/plot_calibration_link.py

No localizer is executed by calibration_quality.py. New localization results are separately
labelled secondary analyses and do not overwrite any original result.

Completed output integrity and qualifications
--------------------------------------------
All 54,000 stored states are finite, with zero execution exceptions. They map to
26,542 checkpoint-distinct solves and 26,212 globally distinct numerical inputs.
Finite output does not imply universal convergence: 84 states (24 unique inputs)
contain at least one unconverged local run. Nine states (seven unique inputs)
have found-candidate diameter above 1 m in the 0.01-dB^2 band, including four
states (two inputs) above 1 km. All states and all candidate pools are retained.
Independent complete reconstruction in ../removal/ additionally verifies the
global input counts and diagnostic flags; see CALIBRATION_DIAGNOSTIC_COUNTS.json
and CALIBRATION_FINAL_INDEPENDENT_VERIFICATION.json in that directory.

All full/affected-cohort P50/P95 comparison signs remain invariant over the
examined candidate pools or numerically tied. This is not global optimality or
an exhaustive near-optimal-region guarantee. At 1 km, improved held-out target
RSS MAE occurs in four selected-policy fields, but RSS-NLS P50 worsens in three
of those four. At 5 km, both estimators improve P95 in all 16 fields. These are
fixed field/fold conditions from one campaign, not independent deployments.
