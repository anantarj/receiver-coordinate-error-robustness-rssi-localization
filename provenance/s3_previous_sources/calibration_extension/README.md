# Paper B — paired-calibration implementation stage

**23 September 2026 | Author-review working packet, not a final journal upload or public release.**

This packet contains the completed 128-pair WCL extension, its exact protocol and driver, complete paired numerical outputs, source-derived diagnostics, a new figure, proposed manuscript passages/outline, and a tested local release-verifier repair. It does not replace the submitted RC8 files or the published v1.0.0 archive.

Start with `EXECUTION_REPORT.md`, then `manuscript_drafts/CALIBRATION_EXTENSION_RESULTS.md` and `manuscript_drafts/CONTRIBUTION_OUTLINE.md`. The new abstract is explicitly a draft. The full Sensors manuscript and Supplement have not yet been assembled or approved.

## Verify this packet

From this extracted directory:

```bash
python3 release_repair/verify_evidence.py --root . --manifest ARTIFACT_SHA256SUMS.txt
python3 verify_public_wcl_extension.py --root .
```

The first command checks artifact bytes/coverage and does not rewrite its manifest. The second checks all scheduled pairs, output arithmetic, weight/prediction identities, touched subsets and historical bridge equality. It does not independently refit intercepts. NumPy is required by the second command.

## Check against the external measurements

Obtain the exact original LoRaWAN v1.3 CSV from the already cited source release (DOI `10.5281/zenodo.3904158`). Expected CSV SHA-256:

`870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446`

Then:

```bash
python3 verify_public_wcl_extension.py --root . \
  --csv /absolute/path/to/lorawan_antwerp_2019_dataset.csv
```

This adds reconstruction of transmitter positions and RSSI slots, verifies error values and the weights implied by recorded intercepts, and still does not refit the intercepts. It needs NumPy, pandas and pyproj. The tested environment is recorded in `extension/ENVIRONMENT.json`.

Raw source measurements are not bundled. To avoid distributing direct source slices, the exported reference NPZs omit `raw_rssi` and `truth`; all other fields are retained. `EXPORT_TRANSFORMATIONS.json` gives the local-original and exported hashes. All pair NPZs are unchanged. Original local validation used the full references; this public-compatible route obtains omitted fields from the exact external CSV.

`verify_wcl_outputs.py` is retained as the source of the original local full-reference validation. It is NOT the entry point for the reduced references in this delivery copy. Use `verify_public_wcl_extension.py` here.

## Rerun the experiment from the pinned source kernels

This is optional author reproduction, not work required to obtain the results already delivered. The minimal `reproduction_inputs/` tree contains the unchanged required source, maps and population manifests. Do not run inside your existing project output folders.

```bash
python3 run_paired_wcl_extension.py \
  --source-root reproduction_inputs \
  --csv /absolute/path/to/lorawan_antwerp_2019_dataset.csv \
  --protocol-dir protocol --output ../paperb_bridge_rerun --phase bridge
```

Only after `BRIDGE_PASS`:

```bash
python3 run_paired_wcl_extension.py \
  --source-root reproduction_inputs \
  --csv /absolute/path/to/lorawan_antwerp_2019_dataset.csv \
  --protocol-dir protocol --output ../paperb_extension_rerun --phase extension \
  --bridge ../paperb_bridge_rerun/BRIDGE_STATUS.json
```

All output directories must be new. Rerun outputs include direct RSSI/transmitter slices for local validation; do not redistribute those unfiltered. The supplied delivery export already excludes them.

## Regenerate tables and the figure

```bash
python3 summarize_extension.py --root . --out ../paperb_tables_recomputed
python3 plot_paired_calibration.py --root . --out ../paperb_figure_recomputed
```

The second command also needs matplotlib. All 128 fields, including four contrary cases, are displayed. New table exports do not overwrite original reports.

## Status and boundaries

- 128/128 pairs complete; four original R29 bridge arrays reproduce exactly.
- No p-values or claim of 639,488 independent observations. That is only the number of repeated message-condition error values checked.
- No new physical deployment, new algorithm, whole B9C rerun or change to G4/G6.
- Native maps share the targeted receiver coordinates and baseline intercepts but differ in other receivers and query identities.
- Public verifier repair is tested locally; **not pushed** to GitHub or Zenodo.
- The full reference/retraction audit, target-template conversion, final full-document integration and new both-author approval remain outstanding.

Code is MIT and author-created documentation/derived artifacts are CC BY 4.0 under the existing project licensing split. Third-party source terms are preserved. See `LICENSE`, `LICENSES/` and `THIRD_PARTY_NOTICES.md`. Private manuscript drafts and audit records in this working packet are not automatically approved for public release.
