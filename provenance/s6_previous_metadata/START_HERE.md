# Start here — S5 integrated evidence

1. Read `README.md` for exact scope and version boundaries.
2. Run `python3 verify_evidence.py` from this directory.
3. Run `python3 scripts/run_release_checks.py --out ../paperb_release_check`. Choose a new output folder outside the package.

The combined command performs integrity, saved-result, coordinate and paired-array checks. It neither refits/interpolates results nor repairs its expected manifest at runtime. See `calibration_extension/README.md` for optional external-data reconstruction and experiment replay. New results are not claimed to be inside the preceding v1.0.0 DOI.

## S4 reporting closure

`results/s4/` adds numerical target-weight/intercept diagnostics, the exactly identified O33-substituted window control and executed spatial definitions. These are derived from retained records, not new perturbation runs. Run `python scripts/check_s4_reporting.py` for the read-only reconstruction check. The accompanying source/PDF versions are S5; S4 records remain the numerical reporting authority. Public v1.1.0 deposition and author approval remain separate; the baseline DOI is not the new experiment DOI.

## S5 narrative and declaration revision

The matched calibration intervention and numerical weight diagnostics now precede the four-pipeline load context. Transmitter-reference and aggregate-error wording are explicit; participation is an identity-traced local comparison over k=5–7, not isolated causal mediation. Numerical results, source kernels and figure data are unchanged. `results/CLAIM_TO_ARTIFACT_SENSORS_S5.csv` supplies current section and figure locations.

The confirmed Author Contributions and Jha email are inserted; the Access AI declaration, no-funding and no-COI statements are preserved. No separate pronoun field is supplied. Final ethics/consent and submission-status facts and both authors' approval of the exact rendered set remain to be confirmed outside the scientific supplement.

Run `python3 scripts/check_s5_documentation.py` for document bindings, protected S4-file identities, numerical-table preservation, declarations and active terminology. `scripts/run_release_checks.py` includes this check. No checker updates its expected manifest. This archive is `PAPERB_SENSORS_EVIDENCE_v1.1.0_S5_300926.zip`; it is not a newly published Zenodo record.
