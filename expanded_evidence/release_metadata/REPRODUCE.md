# Reproduction and integrity routes — Paper B v1.2.0

Version-specific evidence DOI: https://doi.org/10.5281/zenodo.23255545  

## Required inputs

- This exact extracted v1.2.0 ZIP (see `FILE_MANIFEST.json`).
- Immutable baseline ZIP is included at `baseline_v1.1.0/PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip` (SHA-256 `01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268`).
- **Separately obtained** original public Antwerp dataset CSV, SHA-256 `870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446`. Source dataset DOI: `10.5281/zenodo.3904158`. Never substitute a similar unverified dataset.

Run with a Python environment compatible with the tested `Python 3.13.5`, `numpy 2.3.5`, `pandas 2.2.3`, `scipy 1.17.0`, `pyproj 3.7.2`. On another platform package-level numerical results may not be byte-identical even if statistically/numerically equivalent; preserve the original verified archived arrays. No script below changes the frozen original ZIP.

## No-experiment integrity check

From the release root:

```bash
python3 tools/paperb_release_manager.py verify --archive /absolute/path/to/PAPERB_REPRODUCIBILITY_v1.2.0.zip
```

This checks the frozen manifest, embedded baseline hash, metadata DOI and exact member list. The separately retained step-4 and step-5 test/verification tools can be run without changing the archived arrays.

## Prior analyses: historical original-pair, raw-input and deterministic boundary verification

Scientific inputs and results for steps 1–3 are under `expanded_evidence/historical_extensions/`; read `expanded_evidence/PRIOR_STEPS_README.md` for their scope and original-source member checksums. The third-party source observations are a separate acquisition. These curated science files deliberately exclude private administrative histories and do not claim to be a separate measured deployment.

## Step 4: new full synthetic and real-core computations

**First make a disposable copy** of `expanded_evidence/step4` into a fresh workspace and execute from that copied `step4/` directory. Do not regenerate directly inside the archived release folder or edit the locked registries.

```bash
python3 src/run_c2.py --registry protocol/C2_REGISTRY.json \
  --lock protocol/C2_LOCK.json --out results/c2
python3 src/run_real_core.py \
  --archive /absolute/path/to/PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip \
  --csv /absolute/path/to/verified_antwerp.csv \
  --registry protocol/REAL_CORE_REGISTRY.json \
  --lock protocol/REAL_CORE_LOCK.json --out results/real
python3 src/summarize_step4.py --root .
python3 src/verify_step4.py --root . --csv /absolute/path/to/verified_antwerp.csv
python3 -m unittest discover -s tests -v
```

For a full fresh producer run, remove *only the copied output folders* `results/c2` and `results/real` before executing the run commands; producers intentionally refuse to overwrite existing outputs. The other registry and code files must remain unchanged.

## Step 5: additional receiver tests and complete curves

From another disposable copy of `expanded_evidence/step5`, and again using the original baseline archive and input CSV:

```bash
python3 vendor/step4/run_real_core.py \
  --archive /absolute/path/to/PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip \
  --csv /absolute/path/to/verified_antwerp.csv \
  --registry vendor/step4/REAL_CORE_REGISTRY.json \
  --lock vendor/step4/REAL_CORE_LOCK.json --out results/core_restored
python3 src/run_d3.py \
  --archive /absolute/path/to/PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip \
  --csv /absolute/path/to/verified_antwerp.csv \
  --registry protocol/D3_REGISTRY.json --lock protocol/D3_LOCK.json --out results/d3
python3 src/analyze_exceedance.py --core results/core_restored --d3 results/d3 \
  --registry protocol/EXCEEDANCE_REGISTRY.json \
  --lock protocol/EXCEEDANCE_LOCK.json --out results/exceedance
python3 src/summarize_step5.py --root . --out results/synthesis
python3 src/verify_d3.py --root . \
  --archive /absolute/path/to/PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip --csv /absolute/path/to/verified_antwerp.csv
python3 src/verify_exceedance.py --root . --core results/core_restored
python3 -m unittest discover -s tests -v
```

For a fresh producer run, delete only **copied** `results/core_restored`, `results/d3` and `results/exceedance` first. Results are already present and checksum-verified in the frozen archive, so no rerun is necessary to inspect them. Complete field curves are regenerable from the retained errors/masks; 352 structurally selected draw-zero curves are explicitly stored.

## Interpretive guardrails

Preserve field/set/receiver identities and individual adverse outcomes. Across-field medians are descriptive, not confidence limits or independent deployments; within-field paired quantiles and per-message changes differ. The full and affected populations have different denominators. The manifest assures published file bytes, not physical positional truth, prior-art novelty, editorial acceptance or generalization beyond the tested conditions.
