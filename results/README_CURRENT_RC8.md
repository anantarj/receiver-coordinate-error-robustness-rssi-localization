# Current result and reporting entry point

Use `CLAIM_TO_ARTIFACT_RC8.csv`. Earlier versioned indexes and original numerical files are preserved as history, not competing current reporting instructions. `rc8/` contains only the approved scalar/geometry and display clarifications. Canonical code, map parents, populations, saved author outputs and original figure-data tables are unchanged. Current LaTeX captions and Supplement table numbering are bound in the RC8 build record.

Saved-output verification is `python scripts/check_rc5_reporting.py`; new reporting-specific checks are `python scripts/check_rc8_reporting.py`. Neither is a new localization execution. See the root README for full producer routes and their distinct scope.
