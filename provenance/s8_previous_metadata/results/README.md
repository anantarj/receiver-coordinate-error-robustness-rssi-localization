# Result indexes

Current integrated manuscript: `CLAIM_TO_ARTIFACT_SENSORS_S6.csv`. Baseline-specific detail: `CLAIM_TO_ARTIFACT_RC8.csv`. Older B10/RC8/S2 indexes are retained unchanged as historical records; they do not replace the current manuscript interpretation.

New pairs and diagnostics: `../calibration_extension/results/` and `../calibration_extension/extension/pairs/`. Unchanged original arrays/logs remain in their existing folders. No old numeric result was overwritten to create the new 32-field summaries.

## S6 bounded reporting revision

Current documents and archive are S6. Supplement S16.2 now points to main Figure 2; S14.2 correctly states one-decimal display from full-precision arrays. The actual pinned median fit has no imposed intercept bounds, clipping, regularization or shared intercept parameter; the claim is not generalized to constrained fits or alternative weighting. `results/s6/` records the implementation inspection and focused connection to existing references 10 and 11. No numerical outputs or figures changed. Run `python3 scripts/check_s6_documentation.py` for these additions; the combined release checker includes it. The same old DOI remains baseline-only.
