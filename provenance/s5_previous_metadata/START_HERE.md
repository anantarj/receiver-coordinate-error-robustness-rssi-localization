# Start here — S4 integrated evidence

1. Read `README.md` for exact scope and version boundaries.
2. Run `python3 verify_evidence.py` from this directory.
3. Run `python3 scripts/run_release_checks.py --out ../paperb_release_check`. Choose a new output folder outside the package.

The combined command performs integrity, saved-result, coordinate and paired-array checks. It neither refits/interpolates results nor repairs its expected manifest at runtime. See `calibration_extension/README.md` for optional external-data reconstruction and experiment replay. New results are not claimed to be inside the preceding v1.0.0 DOI.

## S4 reporting closure

`results/s4/` adds numerical target-weight/intercept diagnostics, the exactly identified O33-substituted window control and executed spatial definitions. These are derived from retained records, not new perturbation runs. Run `python scripts/check_s4_reporting.py` for the read-only reconstruction check. The accompanying source/PDF versions are S4. Public v1.1.0 deposition and author approval remain separate; the baseline DOI is not the new experiment DOI.
