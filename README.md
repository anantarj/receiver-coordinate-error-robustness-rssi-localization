# Receiver-coordinate error robustness in RSSI localization

## Version and associated article

**Version 1.1.0 — Sensors S8, 30 September 2026.** Prepared release snapshot; remote publication and final author approval are not asserted by the local package.

Associated manuscript: **Recalibration Can Mask Measured Sensitivity to Receiver-Coordinate Errors in RSSI Localization**.

Authors: Ananta Ranjan and Vijay Kumar Jha. This revises the earlier article titled *Not All Receiver-Coordinate Errors Are Equal: Corruption Load, Exposure Topology, and Spatial Structure in RSSI Localization*.

Reserved version DOI: https://doi.org/10.5281/zenodo.23061691

Preceding v1.0.0 baseline DOI: https://doi.org/10.5281/zenodo.22680802 . It does **not** contain the 32-field paired-calibration extension. Preserve that record and tag unchanged.

Repository: https://github.com/anantarj/receiver-coordinate-error-robustness-rssi-localization

Exact version-matched asset: `PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip`.

## Current verification route

From this extracted directory, use Python 3.10 or later with the compatible dependencies in `requirements.txt`:

```bash
python3 verify_evidence.py
python3 scripts/run_release_checks.py --out ../paperb_release_check_S8
```

Choose a new output folder outside the package. These commands do not rewrite expected hashes, run the localization experiment, refit intercepts, bootstrap results, or reconstruct the raw CSV–JSON join. The combined route checks package integrity, retained baseline arrays, saved coordinate evidence, all 128 matched pairs, reporting tables and current S8 documents/metadata.

To include the separately delivered PDF and LaTeX-ZIP hashes in the document check, place those four assets in one directory and run:

```bash
python3 scripts/check_s8_release_metadata.py --pdf-dir /path/to/S8_assets
```

`verify_evidence.py` is standard-library only. Other current checks require the scientific Python dependencies. Inspect the scripts before running them.

## Historical checker boundary

`check_s5_documentation.py`, `check_s6_documentation.py` and `check_s7_release_metadata.py` are preserved historical sources, not current standalone S8 verification entry points. Their earlier-version metadata pins must not be applied to a later release root. Shared pure document-parsing helpers remain imported from the unchanged S5 module. The S8 checker independently verifies the current source bindings, complete preservation list, declarations, numerical tables and exact S7-to-S8 source delta. The historical S5/S6 failures found while checking S7 are recorded in `results/s8/PACKAGING_CORRECTION.json`; they are not reported as passed.

## Scientific scope

The original four-pipeline corruption-load, participation and spatial experiments are retained. The WCL-only paired extension uses R29/O32-minus-BS71, top one/two, 5 km, and 32 specified fields per cell: 128 matched pairs, not 128 independent deployments. Four official-map top-one fields are harmful under refitting and remain included. The original two-field observations and the new 32-field summaries are distinct evidence sets.

R29 is a frozen historical assignment with incomplete selection provenance, not independently surveyed truth. Catalogue controls do not establish physical accuracy. G4 and G6 remain failed. The common-27 official-named map retains the recovered BS71 coordinate in both arms. The observed suppression is specific to the unconstrained receiver-wise median fits and the stated exponential WCL weighting; it is not established for bounded/regularized calibration, shared intercepts or another weighting law.

## Contents and current bindings

`code/`, `maps/`, `author_remaining/`, `coordinate_provenance/`, `historical_controls/`, `reproduction_sources/`, `figures/` and the existing numerical records retain their scientific contents. `calibration_extension/` contains the executed producer, protocol, complete saved arrays and diagnostics. External raw measurements and the source catalogue are not redistributed; obtain and fingerprint the cited public inputs for full experimental replay.

`document_sources/` contains current main and Supplement source trees. `DOCUMENT_BINDING.json` binds these to the separately delivered PDFs and LaTeX ZIPs. `results/CLAIM_TO_ARTIFACT_SENSORS_S8.csv` is the current index. Previous indexes remain historical. `provenance/s8_previous_metadata/` preserves every superseded S7 file byte-for-byte. No S7 archive is overwritten.

S8 repairs active version/index labels and obsolete advertised checker commands. The manuscript and Supplement change only the release-asset name (and index name where present). No experiment, numerical result, figure, scientific claim or author declaration changes.

## Licensing, funding and publication

Author-created code: MIT. Author-created documentation and derived non-code artifacts: CC BY 4.0. Third-party terms remain unchanged; see `THIRD_PARTY_NOTICES.md` and `LICENSES/`.

No funding was received for this work. DOI reservation is not publication. `ZENODO_NEXT_STEP.md` describes the existing-record release route. Final author approval and applicable journal-administration facts remain separate from local verification.
