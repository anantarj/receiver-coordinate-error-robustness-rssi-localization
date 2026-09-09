# Paper B B9C — Rotation transfer cause diagnostic

Date: 5 September 2026
Status: post-failure diagnostic frozen before execution of new diagnostic arms
Authority: B9C G4 remains FAIL regardless of diagnostic outcome

## Question
Why did the positive recovered-29 5-degree rotation-minus-matched-isotropic WCL gap fail to transfer to official-32-minus-BS71?

## Existing facts before this diagnostic
- Recovered-29 legacy result: +5-degree rotation, median displacement 429 m, WCL +49.8%; four-draw constant-429-m isotropic WCL +22.7%; gap +27.1 pp.
- Official-32-minus-BS71 result: +5-degree rotation, median displacement 328 m, WCL +11.0%; four-draw constant-328-m isotropic WCL +15.6%; gap -4.6 pp.
- Completion to eight constant-magnitude isotropic directions retained a negative official WCL gap (-3.93 pp).
- The legacy comparator matches median displacement only. It does not match the per-receiver displacement distribution or RMSE.

## Fixed diagnostic arms
Substrates:
1. recovered-29 native population;
2. official-32-minus-BS71 native population;
3. recovered common-27;
4. official common-27.

The common-27 pair uses an identical ordered evaluation population and identical receiver identities; only coordinate assignments differ.

For each substrate:
- reference;
- +5-degree rigid rotation about that map's receiver centroid;
- -5-degree rigid rotation about that map's receiver centroid;
- eight legacy isotropic maps in which every receiver moves by the rotation's median displacement; seeds 4750 + 13r, r=0,...,7;
- eight exact-magnitude-matched isotropic maps preserving each receiver's rotation displacement magnitude but independently randomizing its direction; seeds 5750 + 13r, r=0,...,7.

All arms retain n=4.7, max_gws=10, canonical split/evaluation population, fresh per-map receiver-intercept refitting, and the canonical WCL/ABS/DIFF/Min-Max implementations.

## Diagnostic interpretations fixed before execution
D1. Four-versus-eight replication: recovered-29 remains a genuine finite-design observation if its positive legacy gap survives eight directions.
D2. Magnitude-distribution mismatch: if rotation's excess materially contracts or reverses against the exact-magnitude-matched comparator, the legacy median-only comparator did not isolate direction structure.
D3. Rotation-sign interaction: a material +5 versus -5 asymmetry indicates interaction with pre-existing frame orientation; 'rotation' cannot be treated as sign-free.
D4. Assignment-only interaction: a different gap sign/classification on recovered-common-27 versus official-common-27 identifies coordinate assignment, rather than roster/population alone, as load-bearing.
D5. Outlier leverage: geometry diagnostics will report median/RMS/max rotation displacement and per-anchor influence checks. Large recovered-map displacement-tail leverage is evidence against attributing the entire legacy gap to bearing change alone.

No diagnostic can retroactively turn G4 into PASS. Results will be used only to explain the failure and determine correct manuscript wording.
