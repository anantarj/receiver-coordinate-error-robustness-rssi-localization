# Result indexes

Current integrated manuscript: `CLAIM_TO_ARTIFACT_SENSORS_S8.csv`. Baseline-specific detail: `CLAIM_TO_ARTIFACT_RC8.csv`. All prior indexes, including S6 and S7, are historical and remain unchanged.

New paired arrays and diagnostics: `../calibration_extension/results/` and `../calibration_extension/extension/pairs/`. Original arrays/logs remain in their existing locations. `s4/` remains the numerical reporting authority; `s6/` preserves the implementation and focused-literature records; `s7/` preserves the original DOI reservation/binding record. `s8/` records only the packaging correction, exact source delta and S7 preservation contract.

The current combined route is `python3 scripts/run_release_checks.py --out /new/external/output` from the repository root. Its current documentation stage is `scripts/check_s8_release_metadata.py`; earlier document-checker entry points are historical, not advertised current commands.
