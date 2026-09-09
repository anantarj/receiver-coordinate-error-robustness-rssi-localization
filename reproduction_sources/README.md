# Additional original reproduction sources

These three existing scripts were recovered from the saved research records and copied without changes. SOURCE_INDEX.json records their identities. They were missing from the earlier reduced evidence package.

The coverage script operates only on reception sets, with a lexicographic receiver-ID tiebreak. The separate rank-stability script uses numeric ID tie order. These are the actual recorded implementations, not silently standardized replacements. Main topology figures retain the saved coverage log. The normalization script removes header quoting; its handling of file encodings/newlines is the preserved source behavior, not a newly certified byte-for-byte property for arbitrary CSVs.

From the evidence root, with NEW output prefixes outside it:

```bash
python reproduction_sources/paperb_coverage_audit_030926.py --data /path/lorawan.csv --map maps/recovered29.json --evaluator-dir code --sigfox-urban /path/sigfox_urban_norm.csv --sigfox-rural /path/sigfox_rural_norm.csv --out ../coverage_replay
python reproduction_sources/paperb_exposure_rank_stability_audit_040926.py --data /path/lorawan.csv --map maps/recovered29.json --evaluator-dir code --max-gws 10 --out ../rank_w10
python reproduction_sources/paperb_exposure_rank_stability_audit_040926.py --data /path/lorawan.csv --map maps/recovered29.json --evaluator-dir code --max-gws 5 --out ../rank_w5
```

The urban/rural Sigfox CSVs are external data from the cited source release. Header-normalized raw data and original normalization receipts were not present in this revision runtime; no new Sigfox computation or hash certification is asserted. Use the original source publisher checksums, preserve normalization receipts, and compare the emitted population counts and curves to results/base_logs/paperb_coverage_all.txt. Do not silently accept mismatches. The saved scientific outputs remain inspectable even without fetching these external inputs.

The scripts are research producers and may overwrite their named output prefixes. Always use a new directory. They are not invoked by the integrity checker. No companion manuscript is required to execute them.
