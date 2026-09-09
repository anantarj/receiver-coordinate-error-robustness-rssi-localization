# Receiver-coordinate error robustness in RSSI localization

Reproducibility package for:

**Not All Receiver-Coordinate Errors Are Equal: Corruption Load, Exposure Topology, and Spatial Structure in RSSI Localization**  
Ananta Ranjan and Vijay Kumar Jha

This repository contains the author-created code, frozen coordinate configurations, ordered evaluation populations, perturbation definitions, retained outputs, figure data, and verification utilities used for the IEEE Access manuscript.

## Start here

For the shortest verification route, see **[START_HERE.md](START_HERE.md)**.

The source measurements are **not redistributed**. Obtain the public Antwerp LoRaWAN v1.3 data and gateway catalogue from the cited source release, then verify them against `data/EXTERNAL_INPUTS.json` / `coordinate_provenance/EXTERNAL_INPUTS.json`.

## Scientific scope

The study evaluates four implemented RSSI-localization pipelines under controlled receiver-coordinate perturbations:

- intercept-corrected weighted centroid localization (WCL),
- absolute-residual lattice localization (ABS),
- differential-residual lattice localization (DIFF), and
- Min-Max.

The principal experimental dimensions are corruption load and magnitude, receiver-participation topology and recalibration, and spatial error structure. The package preserves negative results and design limitations. In particular, the pre-specified legacy rotation-transfer criterion (G4) and spatial-cell transfer criterion (G6) remain **failed**.

## Repository contents

- `code/` — canonical evaluator and experiment harness.
- `maps/` — eight frozen coordinate constructions used by the study.
- `data/` — external-data fingerprints and acquisition notes; no raw third-party measurements.
- `coordinate_provenance/` — used-receiver crosswalk, map-parent records, source manifests, and coordinate-input checks.
- `results/` — retained outputs, current claim-to-artifact index, figure data, population manifests, reporting tables, and bounded RC8 checks.
- `author_remaining/` — retained author-run outputs for the later safeguard/diagnostic stages.
- `historical_controls/` — exact design records and saved summaries for antecedent controls retained for provenance.
- `figures/` — publication figure PDFs and figure manifests.
- `scripts/` — verification, reporting, figure, and replay-preparation utilities.
- `reproduction_sources/` — supporting audit and normalization sources.
- `governance/` — frozen B9C protocol and gate matrix used to interpret the reported safeguards.

## Verification

From the repository root, after inspecting the scripts:

```bash
python verify_evidence.py
python scripts/check_rc5_reporting.py
python scripts/check_rc8_reporting.py
python scripts/verify_coordinate_provenance.py --out ../paperb_input_check
```

These commands are deliberately scoped:

- `verify_evidence.py` checks released bytes and package integrity.
- `check_rc5_reporting.py` rederives retained method medians and checks the matched-exposure reporting reconstruction.
- `check_rc8_reporting.py` checks the six retained rotation refit/frozen pairs and the RC8 radial-operator reporting.
- `verify_coordinate_provenance.py` checks saved identities, catalogue projection, and frozen map-parent relations. It does **not** by itself rerun the raw CSV–JSON identity join.

See `START_HERE.md` for external-input and fuller replay guidance.

## Reference-coordinate limits

The primary R29 assignment is a frozen historical correlation-selected map with incomplete original selection provenance. It is not represented as independently surveyed truth. Reproduction of experiments conditional on the frozen map is distinct from reconstructing its missing historical selection process.

The catalogue-derived configurations provide a separate input path. BS71 is treated as a survey-relative extreme and sensitivity case, not as a proven physical catalogue error. `maps/official27_common.json` is a mixed-reference construction: 26 catalogue-derived coordinates plus the R29 coordinate for BS71, held fixed in both common-27 arms.

## Data availability

The underlying Antwerp measurements and gateway catalogue are third-party public data and are not redistributed here. Their exact expected filenames and fingerprints are recorded in `data/EXTERNAL_INPUTS.json` and `coordinate_provenance/EXTERNAL_INPUTS.json`.

Author-created derived data needed to inspect the manuscript's reported experiments are included in this repository.

## Version

This repository is being prepared for **v1.0.0**, aligned to manuscript revision **RC8 (9 September 2026)**.

**Zenodo DOI:** to be inserted after DOI reservation and before the v1.0.0 release is frozen.

## Licensing

- Author-created **code**: MIT License (`LICENSE`).
- Author-created **documentation and derived non-code artifacts**: CC BY 4.0 (`LICENSES/CC-BY-4.0.txt`).
- Third-party data and source materials retain their original terms. See `THIRD_PARTY_NOTICES.md`.

The top-level MIT license does not relicense third-party material or non-code artifacts covered separately by CC BY 4.0.

## Citation

Citation metadata are provided in `CITATION.cff`. After the Zenodo DOI is reserved, the DOI will be added to both this README and `CITATION.cff` before the public v1.0.0 release.

## Funding

No funding was received for this work.
