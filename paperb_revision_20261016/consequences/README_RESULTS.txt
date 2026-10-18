PAPER B — CONSEQUENCE AND FOUND-CANDIDATE SENSITIVITY ANALYSIS

This directory is additive. It does not modify any original input, production
solver, primary prediction, or original manuscript. The descriptive protocol was
written and hashed before these follow-up outcomes were calculated.

Original source dependency:
  ../../paperb_execution_20261015/
Recovered candidate dependency:
  ../numerical/
These relative scopes are resolved from this directory. Retain this layout, or
adjust the source-root constant explicitly and record that change when porting.

Commands from any working directory:
  python src/original_consequences.py
  python tests/test_envelopes.py
  python src/candidate_consequences.py
  python src/summarize_pool_diagnostics.py
  python src/plot_transfer.py
  python src/paper_fragments.py

After the separately scheduled targeted enhanced audit completes:
  python src/candidate_consequences.py --enhanced-directory ../numerical/targeted_audits
  python src/summarize_pool_diagnostics.py --enhanced
The relative enhanced-directory command argument is interpreted from the shell's
working directory; use its absolute path when running elsewhere.

results/original/ contains every original-output field, both directions of the
method-choice transfer diagnostic, all zero/null/adverse contrasts, both reporting
cohorts, reference-uncertainty sign-certificate boundaries, exact error-threshold
intervals, and full interval-width summaries. Its 192 originally reported ranking
rows reconstruct exactly from the frozen arrays.

results/candidates/ contains complete primary-pool envelopes at objective bands
0.01, 0.001 and 0.0001 dB squared. Ranking, within-estimator calibration effects,
and prediction-movement effects have different classification files. Invariance
of one must not be substituted for another. Explicit sensitivity assignments and
two reference-independent deterministic alternatives are retained. Candidate
references score sensitivity only; they never select a production branch.

results/candidates_enhanced/ is a separate overlay, when created. It combines all
primary pools with the completed targeted audit archives and must be described
with that targeted coverage; it is not exhaustive enhanced search of all inputs.

results/presentation/ contains the four-panel vector figure and its exact source
CSV, main and supplement fragments, and complete full-cohort tables for all 24
primary-map positive fields and all 32 all-fit spatial fields. Zero fields remain
in the figure and the complete machine-readable results. The ten-reception and
R29 cases, plus affected cohorts, remain in the full CSVs.

Interpretation safeguards:
  * Choice transfer is selected and evaluated on the same cohort, not test regret.
  * Candidate envelopes concern found solutions, not complete near-global sets.
  * A straddling envelope alone does not prove an attainable branch reversal.
  * Exact repeated numerical inputs share one candidate under implementable rules.
  * Reference uncertainty keeps predictions and calibration fixed; |margin|/2 is
    loss of a sufficient sign guarantee, not an achieved reversal or GNSS accuracy.
  * Threshold widths are lengths on the tolerance axis, not application risks.
  * Maps, directions, folds and calibration repetitions are descriptive conditions,
    not independent network deployments.
