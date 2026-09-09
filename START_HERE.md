# Start here

This file gives the shortest route for inspecting and reproducing the Paper B release.

## 1. Inspect the release before running anything

Start with:

- `README.md`
- `results/CLAIM_TO_ARTIFACT_RC8.csv`
- `data/EXTERNAL_INPUTS.json`
- `coordinate_provenance/README.md`
- `results/README_CURRENT_RC8.md`

## 2. Create the Python environment

Using Conda:

```bash
conda env create -f environment.yml
conda activate paperb-repro
```

If you prefer pip, create a clean virtual environment and install:

```bash
python -m pip install -r requirements.txt
```

The retained records include historical environment information. Exact historical bitwise environment identity is not claimed where the dependency freeze is unavailable.

## 3. Run read-only/saved-output checks

From the repository root:

```bash
python verify_evidence.py
python scripts/check_rc5_reporting.py
python scripts/check_rc8_reporting.py
python scripts/verify_coordinate_provenance.py --out ../paperb_input_check
```

Expected interpretation:

- successful checks establish consistency of the released artifacts with the retained records they test;
- they are not automatically a fresh rerun of every localization experiment;
- they do not establish physical truth of a receiver map;
- they do not reconstruct R29's incomplete historical selection process.

## 4. Obtain external source data

The raw Antwerp measurements are not redistributed in this repository. Obtain the LoRaWAN Antwerp v1.3 files and gateway catalogue from the public source cited in the manuscript.

Before using them, compare their fingerprints with:

```text
data/EXTERNAL_INPUTS.json
coordinate_provenance/EXTERNAL_INPUTS.json
```

The expected principal CSV SHA-256 is recorded there. Do not substitute a rewritten or reordered CSV and assume source-row identities remain equivalent.

## 5. Coordinate-input reconstruction

`coordinate_provenance/README.md` documents the two levels of checking:

1. saved-evidence/map-parent verification; and
2. a raw CSV–JSON identity rebuild when the fingerprint-matched external files are supplied.

The raw rebuild uses reception metadata and receiver presence/RSSI sequences before consulting catalogue coordinates. Transmitter coordinates and localization outcomes are not used to select the receiver identities in that reconstruction.

## 6. Locate results behind manuscript claims

Use:

```text
results/CLAIM_TO_ARTIFACT_RC8.csv
```

This is the current claim-to-artifact index for RC8. Useful locations include:

- `results/figure_data/`
- `results/rc5/`
- `results/rc8/`
- `author_remaining/`
- `historical_controls/`

The historical-control records are retained as antecedent evidence and are not reclassified as newly executed RC8 experiments.

## 7. Full replay scope

For fuller reproduction, inspect:

```text
scripts/prepare_replay_workspace.py
reproduction_sources/README.md
coordinate_provenance/README.md
```

`prepare_replay_workspace.py` constructs the historical path layout from pinned files plus separately supplied fingerprint-matched source inputs. Inspect the script before execution and write outputs outside the repository.

## 8. Known scientific boundaries

- R29 is a frozen historical reference with incomplete original selection provenance.
- G4 (legacy rotation transfer) remains failed.
- G6 (spatial-cell transfer) remains failed.
- Some structured spatial arms are deterministic constructions, whereas isotropic controls have repeated directions.
- Saved-output verification is not independent deployment replication.

These boundaries are part of the released scientific record, not omissions to be silently repaired during reproduction.
