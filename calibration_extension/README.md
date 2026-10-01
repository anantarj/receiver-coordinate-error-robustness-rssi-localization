# Paired-calibration extension — complete stored evidence

128 matched pairs, with 32 fields in each R29/O32-minus-BS71 and top-one/top-two cell. The four adverse official-map top-one fields are retained. The dated `EXECUTION_REPORT.md` records the S1 computation and its boundaries; its future-work statements are historical, not current instructions. No new experiment is executed by the verification commands below.

## Verify

From this directory:

```bash
python3 release_repair/verify_evidence.py --root . --manifest ARTIFACT_SHA256SUMS.txt
python3 verify_public_wcl_extension.py --root .
```

The local manifest now covers the actually distributed files. Original S1 draft manuscripts were deliberately excluded from the integrated release; the prior manifest/README are retained under the package-root `provenance/s3_previous_sources/`. No numerical outputs were removed or changed.

The second command verifies all planned fields, paired scalar arithmetic, prediction/weight identities, affected-message summaries and bridge equality; it does not independently refit intercepts. NumPy is required.

## Optional external-data reconstruction

```bash
python3 verify_public_wcl_extension.py --root . --csv /absolute/path/to/lorawan_antwerp_2019_dataset.csv
```

This additionally reconstructs transmitter positions and raw RSSI slots from the external fingerprinted CSV and checks error values and weights. Requirements: NumPy, pandas, pyproj. Raw measurements are not distributed. Exported reference NPZs omit raw RSSI/transmitter truth; `EXPORT_TRANSFORMATIONS.json` records the change. The original full-reference checker is historical; the public-compatible checker is the active route.

## Optional full replay

Read `protocol/` and the versioned driver before execution. Run outside an existing results directory; outputs must be new:

```bash
python3 run_paired_wcl_extension.py --source-root reproduction_inputs --csv /absolute/path/to/lorawan_antwerp_2019_dataset.csv --protocol-dir protocol --output ../paperb_bridge_rerun --phase bridge
```

After a successful historical bridge:

```bash
python3 run_paired_wcl_extension.py --source-root reproduction_inputs --csv /absolute/path/to/lorawan_antwerp_2019_dataset.csv --protocol-dir protocol --output ../paperb_extension_rerun --phase extension --bridge ../paperb_bridge_rerun/BRIDGE_STATUS.json
```

A replay produces local direct observation slices for checking. Do not redistribute those unfiltered. The stored public-compatible arrays are already sanitized. Neither replay nor public posting occurred during S3.

## Summary and figure reconstruction

```bash
python3 summarize_extension.py --root . --out ../paperb_tables_recomputed
python3 plot_paired_calibration.py --root . --out ../paperb_figure_recomputed
```

Use new output directories. The figure additionally requires matplotlib. No field is selected by its outcome. G4/G6 remain failed; two native configurations are not independent deployments.
