# RC8 reporting additions — existing experiments, explicit operators

`rotation_refit_frozen.csv` re-expresses all six retained pairs with **refit minus frozen** signs. `REPORTING_SOURCE_BINDING.json` identifies the original CSV and 16 scalar cases. The original frozen-arm per-message errors were not exported; consistency of scalars is not independent reproduction of those errors.

`radial_reference_radii.csv`, `radial_geometry_check.csv` and `bounded_check_sources.json` describe the existing frozen R29 geometry and its evaluation-transmitter centroid. The inward operator is unclipped; crossing (D > radius) is not the same as an increased final radius (D > 2 radius). A coincident receiver is unchanged. The centroid was rechecked against the fingerprinted CSV and stored row IDs without fitting or localizing.

`corrupted_count_labels.csv` maps the historic nominal percentage labels to actual counts. Method values in Supplement Tables S4–S7 are unchanged. Historical source tables/logs retain their original labels.

Run `python scripts/check_rc8_reporting.py` from the package root for scalar, source-identity, geometric and document-presence checks. Add `--csv /path/source.csv` to reconstruct the transmitter centroid from the separately obtained raw CSV. No check fits intercepts, runs localization, regenerates bootstraps or writes expected manifests. G4 and G6 remain FAIL.
