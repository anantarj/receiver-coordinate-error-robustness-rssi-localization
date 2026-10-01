# Start here — S8 integrated evidence

Version 1.1.0, reserved DOI `10.5281/zenodo.23061691`. The preceding DOI `10.5281/zenodo.22680802` is v1.0.0 baseline-only.

Use `PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip` with the matching S8 PDFs and source ZIPs. The S7 set is preserved but is superseded as the current upload candidate.

1. Read `README.md` and install its compatible Python dependencies.
2. Run `python3 verify_evidence.py` from this directory.
3. Run `python3 scripts/run_release_checks.py --out ../paperb_release_check_S8` with a new external output directory.
4. Optionally run `python3 scripts/check_s8_release_metadata.py --pdf-dir /path/to/S8_assets` to verify the delivered PDFs and LaTeX ZIPs.

The historical S5/S6/S7 document checkers are not current standalone entry points. Their previous-version pins remain unchanged as historical evidence. Use the S8 checker above, not an older-stage checker against the current root.

Current index: `results/CLAIM_TO_ARTIFACT_SENSORS_S8.csv`. Numerical authority remains the retained baseline, calibration-extension and S4 reporting records; S8 runs no new experiment.

DOI reservation, local validation, all-author approval, GitHub publication, Zenodo publication and journal submission are distinct states. No remote action or final approval is inferred from this snapshot.
