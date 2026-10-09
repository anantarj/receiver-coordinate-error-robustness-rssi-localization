# Paper B — expanded reproducibility resources (v1.2.0)

**Public software/evidence version:** `1.2.0`  
**Version DOI:** https://doi.org/10.5281/zenodo.23255545  
**GitHub:** https://github.com/anantarj/receiver-coordinate-error-robustness-rssi-localization  
**Exact versioned archive:** `PAPERB_REPRODUCIBILITY_v1.2.0.zip`

Associated working manuscript: **Calibration-Induced Receiver Suppression and Its Limits in Weighted-Centroid Localization**, by Ananta Ranjan and Vijay Kumar Jha. The exact final manuscript and Supplement documents may be separately revised; this release freezes the expanded computational evidence, not a journal publication decision.

## What this archive contains

- `baseline_v1.1.0/PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip` is the exact, unchanged previous evidence ZIP (SHA-256 `01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268`), available independently at https://doi.org/10.5281/zenodo.23061691. It preserves the older evidence including the original 128 matched pairs, original source tree and earlier document bindings. Its embedded historical publication-status text describes the old snapshot, not the current deposit.
- `expanded_evidence/historical_extensions/step1` through `step3` hold curated original-pair reliability and harm calculations, raw-input reconstruction, and deterministic boundary experiments. Their numerical data, methods and hashes are preserved without private author preparation records.
- `expanded_evidence/step4/` holds the finite/noisy generated datasets, real-data weighting/calibration/magnitude core, complete numerical arrays, locked registries and executable analysis/checking sources.
- `expanded_evidence/step5/` holds the six-calibration-stratum-receiver validation, full empirical error-exceedance analysis, complete scored arrays and curve tables, locked registries, executables and checks.
- `CLAIM_TO_ARTIFACT.csv` gives exact primary locators for the central study claims and necessary interpretation limits.
- `REPRODUCE.md` provides the executable verification routes and external-input instructions.
- `FILE_MANIFEST.json` enumerates exact bytes and SHA-256 values for every file in this archive except the manifest itself.

The repository's tracked source tree contains the reproducibility sources and compact indices; the **complete output arrays are distributed in the exact ZIP asset**, attached to the GitHub `v1.2.0` release and mirrored byte-for-byte on Zenodo.

## Scientific and interpretive scope

One public Antwerp LoRaWAN campaign underpins the measured-data comparisons. The two coordinate configurations from that campaign are *not independent deployments*. Synthetic known-geometry experiments investigate model conditions and do not substitute for another physical field trial. Receiver-specific intercept updates, normalized coordinate influence, weighting powers, and availability are evaluated under explicitly registered rules. A proposed receiver-removal target set is supplied; the work does not detect erroneous receivers automatically.

Refitting and frozen calibration are legitimate information regimes. The original receiver-removal operational failure rates enforce at least three selected receivers after removal and **do not refill slots**. Selected quantile differences, complete empirical exceedance curves and individual-message harms measure different properties. Small affected sets are not enlarged by repeated directions.

## Inputs, licensing and immutable versions

The **third-party raw CSV and gateway catalogue are not redistributed**. Reproduction requires the original public dataset (DOI https://doi.org/10.5281/zenodo.3904158) with input SHA-256 `870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446` for the specified CSV. Do not infer surveyed physical coordinate truth from the supplied reference positions.

Author-created software is MIT licensed; author-created documentation and derived non-code artifacts are CC BY 4.0. Third-party rights remain with their owners. See `LICENSE`, `LICENSES/README.md`, and `THIRD_PARTY_NOTICES.md`.

The earlier `v1.1.0` release and DOI remain unchanged. See `REPRODUCE.md` before executing resource-intensive producers. For disclosure, use the manuscript's approved statements rather than treating this archive as an author-approval or journal-submission record.

---

## Archived v1.1.0 README (historical context)

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
