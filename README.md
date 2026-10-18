Calibration-Dependent Robustness to Receiver-Coordinate Errors in RSSI Localization
Reproducibility resources — version 1.2.0
Authors: Ananta Ranjan and Vijay Kumar Jha
Evidence DOI: https://doi.org/10.5281/zenodo.23255545
Source repository: https://github.com/anantarj/receiver-coordinate-error-robustness-rssi-localization

This public package contains computational methods, locked protocols, derived
inputs, retained predictions, candidate searches, numerical diagnostics and
machine-readable results. The current submission manuscript, scientific
supplement, their LaTeX sources, and submission-prose generators are excluded.
Publication of this evidence package still discloses its methods and findings.

FILES TO OBTAIN
1. PAPERB_ADDITIONAL_EVIDENCE_v1.2.0_PUBLIC.zip, supplied as four ordered parts. It contains the matched WCL/RSS-NLS
   studies and the subsequent numerical, calibration-quality, consequence,
   finite-mechanism and receiver-removal analyses.
2. PAPERB_REPRODUCIBILITY_v1.2.0.zip, the unchanged earlier twelve-part archive
   containing earlier simulations and controls. Its embedded v1.1.0 baseline
   includes historical document sources already distributed with that earlier
   release (DOI 10.5281/zenodo.23061691). These are not the current submission.
3. PAPERB_GITHUB_PUBLIC_v1.2.0.zip, a browsable source subset; it does not contain the large output arrays.
4. PUBLIC_RELEASE_MANIFEST_v1.2.0.json, PUBLIC_SHA256SUMS_v1.2.0.txt and
   verify_public_release.py for delivery checks and archive assembly.

REPRODUCIBILITY ROUTES
Run python3 verify_public_release.py in the download folder. Add --assemble
to assemble both ZIPs without altering their parts. Extract the additional ZIP
into a fresh working directory. Keep paperb_execution_20261015/ and
paperb_revision_20261016/ as siblings. Run python3 verify_bundle.py there.
Read the two README_REPRODUCE.txt files for saved-output checks and replay.
Use a disposable working copy for scripts that rewrite receipts or results.

For the current numerical recovery and audit registers, start with
paperb_revision_20261016/numerical/README_SCHEMA.txt. Consequence tables and
candidate-pool bounds are in consequences/results/. Calibration split/fit and
validation-selected update records are in calibration/. Receiver-removal
availability and error registers are in removal/. Finite mechanism experiments
are in theory/. Claim-to-artifact CSVs retain their original references; entries
pointing to withheld manuscript text are not public-download promises.

The public calibration verification adapter is
paperb_revision_20261016/removal/verify_completed_calibration_public.py.
It retains the parent scientific checks and explicitly excludes verification
of the two withheld PDFs. The public finite-diagnostic adapter is
paperb_revision_20261016/theory/run_finite_diagnostics_public.py --verify-only.
It verifies the original computational bindings while explicitly recording the
one withheld proof-text binding. Original programs and original locks remain
unchanged for provenance. Their document-dependent checks require the private
document set; use the named public adapters for this distribution.

PUBLIC_DOCUMENT_EXCLUSIONS.json records the omitted paths and original hashes.
PUBLIC_PACKAGING_AUDIT.json documents preserved scientific files and derived
adapters. Root and per-study FILE_MANIFEST/BUNDLE_MANIFEST files describe this
public package. Other historical manifests/receipts retain their original scope
and may refer to withheld documents. They are not fresh verification receipts.
Mathematical proofs are supplied to journal reviewers with the manuscript and
supplement. Repository integrity is not scientific validation or global-optimum
certification. No experiment has been rerun to create this public packaging.

INPUTS AND LIMITS
Third-party full raw measurements and gateway catalogue are not redistributed.
Acquire the original source at https://doi.org/10.5281/zenodo.3904158 and follow
the documented fingerprints. Derived observation/reference slices are supplied.
All measured-data experiments use one Antwerp campaign. Spatial folds are not
independent deployments; supplied coordinates are not independently surveyed
truth. Results are conditional on the stated estimators, calibration regimes,
selection rules, candidate pools, and reporting populations. Adverse results,
unresolved numerical cases, and all original output arrays remain included.

LICENSING
Author-created code: MIT. Author-created documentation and derived non-code
artifacts: CC BY 4.0. Third-party materials retain their original terms.
See LICENSE, LICENSES/ and THIRD_PARTY_NOTICES.md in the archives.

This GitHub tree is a source subset. Run full evidence checks from the downloaded additional-evidence archive. Existing public tags are preserved.
