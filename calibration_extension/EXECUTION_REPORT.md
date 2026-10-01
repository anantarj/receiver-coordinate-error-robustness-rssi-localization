# Paper B — implementation stage S1 completed

**23 September 2026 | Target: Sensors | Local computation and author-review drafts**

## Decision and completed work

The original source inputs were recovered from the supplied/library artifacts; no new upload is needed. The original paired calibration bridge passed. The approved bounded extension was executed in full: **128 matched pairs, 256 scoring conditions**. A new source-grounded argument outline, 184-word abstract draft, detailed methods/results passage, LaTeX integration fragment, complete figure and focused closest-work comparison are prepared. The public-manifest verification defect has a tested local repair.

The principal new result is **calibration-dependent sensitivity, not uniform protection**. All 32 two-target fields benefit from refitting on each native configuration. Four of 32 one-target fields on O32−71 instead worsen with refitting. These are retained in the table, figure, data and proposed abstract.

The submitted RC8 manuscript/Supplement/LaTeX archives are unchanged. No revised complete manuscript PDF, public release, DOI, GitHub push or journal submission is claimed in this stage.

## 1. Exact execution and controls

The protocol/driver were locally frozen before bridge/extended outcomes (freeze SHA-256 `dbee07600d6b0036361306dbcd25dbb64efb98da975d68014b56d525b1c204e9`). The unchanged canonical loader and WCL/calibration functions reconstruct the 16,612-record calibration set and the native 2,498-record evaluation sets. Baselines reproduce 597.6726773741443 m on R29 and 593.7425223089783 m on O32−71. The original top-one/two, two-field results reproduce 3.5/29.3% and 1.5/117.0% (refit/frozen). All four original bridge array records match the corresponding extended cases exactly.

Empty-target and zero-displacement controls pass exactly. Target identities, unchanged raw RSSI, ordered evaluation identities, selected receivers, reference-map immutability and sufficient calibration support are asserted. Non-target intercepts are unchanged; all output values are finite and complete. Untouched message predictions remain exactly equal to reference in every arm. The first bridge attempt timed out before exporting any pairs and is recorded; the subsequent complete bridge passed before the extension was executed.

The completed extension uses the same fields as the approved input register: 32 per native-map/target-count cell, 5 km, n=4.7 and maximum receiver window ten. All outcomes were retained. The full run, including input loading, took approximately 127 seconds in this environment. These are assistant-runtime computations, not an author-machine rerun or physical replication.

## 2. Results

The signed paired benefit is median(error_frozen) minus median(error_refit) within each field. Arm percentages below are medians across fields relative to the appropriate unperturbed reference. They are not pooled-message percentages. The paired benefit is summarized separately and is not inferred by subtracting the two arm medians.

| Configuration | Refit change | Frozen change | Median paired benefit | Paired full range | Helpful/harmful fields |
|---|---:|---:|---:|---:|---:|
| R29, top one | +3.51% | +35.71% | 192.92 m | 5.83–226.89 m | 32/0 |
| R29, top two | +1.53% | +99.83% | 587.87 m | 327.07–736.86 m | 32/0 |
| O32−71, top one | +3.33% | +31.75% | 169.03 m | −25.25–248.24 m | 28/4 |
| O32−71, top two | −1.76% | +50.23% | 307.93 m | 123.24–448.39 m | 32/0 |

The four adverse official top-one fields have draw indices 4, 5, 9 and 14. Their adverse effects persist in the fixed touched-message subset. No field has been hidden or replaced. The full range and IQR, every individual result and the sign convention are available in `results/`.

The old R29 frozen top-two figure, 117.0%, remains correct for the original two fields. The expanded 32-field median is 99.83%. This is an extension with a different aggregation population, not an unexplained correction to the old result.

## 3. Explanation and limitations

Two-target corruption touches 1,845/2,498 R29 messages and 1,817/2,498 O32−71 messages. The small refit whole-population effect is therefore not explained solely by an untouched majority. The corresponding touched-subset paired median benefits are 740.37 and 463.71 m. These are differences of subset medians, not a claim that every touched message improves.

The normalized target weight mass falls sharply when the intercepts are refitted. For example, the two-target R29 diagnostic changes from about 0.21890 to 0.00015850. This follows the exact normalized reweighting identity for fixed raw RSSI. The identity was checked against saved predictions and is included as explanatory algebra, not a novelty claim or error-magnitude decomposition.

The four adverse cases matter: calibration-induced downweighting is not universally beneficial. The two reference configurations share the same BS14/BS69 coordinates, baseline intercepts and calibration population. Other geometry, roster composition and evaluation identities differ. They are not independent deployments and their difference does not isolate the cause of the adverse fields. The study remains conditional on its chosen configurations, calibration opportunity, targets and finite fields.

G4 and G6 remain failed. The new sparse comparison neither independently manipulates support exhaustion nor eliminates R29's historical provenance limitation. It adds realization-level evidence to one intervention, not general validation of the whole research programme.

## 4. Contribution and manuscript work prepared

`manuscript_drafts/` contains a proposed title/outline, a 184-word abstract, a detailed integration-ready results account, LaTeX fragment and focused comparison against five primary works. The proposed argument retains the full four-pipeline load study and foregrounds calibration-state effects, identity-traced participation and reference/pivot-sensitive interpretation.

The literature comparison distinguishes our finite-pipeline experiment from previous uncertainty-aware estimators, weighting methods, geometric bounds/decompositions and energy/error-constrained sensor selection. It does not certify first-ever novelty. Access levels are recorded; several primary records were accessible only as abstracts. The full bibliography/retraction audit remains due.

The new LaTeX results fragment compiles in a standalone check with no overfull box or undefined reference. This is not the final Sensors class build. The new all-field figure was rendered and visually checked. The original ten manuscript figure PDFs remain unchanged.

## 5. Verification results

- 128 scheduled pairs accounted for, with 32 in each of four cells.
- All four historical bridge arrays equal their extended-run counterparts.
- A separate full-reference checker reconstructed weights, predictions, errors, primary and touched summaries, and the normalized reweighting identity for 639,488 repeated condition-message values.
- Maximum prediction reconstruction discrepancy was below 5e−9 m; maximum normalized-weight discrepancy was about 4.44e−16.
- The exported-data checker passed without raw measurements. With the external fingerprinted CSV it also reconstructed all 639,488 error values and weight vectors. This does not independently refit intercepts.
- Seven exported summary/diagnostic tables regenerate from complete retained records within numerical tolerance.
- All 957 original public-starter manifest entries remain unchanged. The original main, Supplement, both source archives and public starter archive match the input hashes.
- 15 release-verifier/builder tests passed, including manifest discovery, ./ normalization, changed/missing/unlisted files, unsafe paths, duplicate aliases, ambiguous manifests, symlink escape and manifest-not-rewritten-on-failure behavior.

These checks distinguish package integrity, numerical reconstruction and original experimental execution. They do not establish independent physical replication or predict acceptance.

## 6. Release repair and export boundaries

The new local read-only verifier recognizes the actual public manifest and normalizes its leading ./ paths. A separate guarded build script allows only explicitly authorized manifest changes/additions. The repaired verifier reads the unchanged starter successfully (957/957). No public tag was moved and no existing Zenodo file was replaced.

This delivery contains derived outputs and source code, not the raw Antwerp CSV. Four reference NPZ delivery copies explicitly omit raw RSSI/transmitter-truth arrays; original local files and all pair arrays remain untouched. `EXPORT_TRANSFORMATIONS.json` records both identities. The public-compatible checker obtains those fields from the external CSV when supplied. The original local checker is included for provenance but is not the no-data entry point for the reduced export.

The next integrated release must fix README/CITATION/release status and intentional metadata hashes together. It must use a new version in the existing archive family rather than imply these new outcomes are in v1.0.0 / DOI 10.5281/zenodo.22680802.

## 7. Next bounded stage

Assemble the complete Sensors manuscript and Supplement from the revised hierarchy and the completed results; retain all required qualifications and map/source credit; complete references and template checks; prepare and verify the new actual release; then obtain both authors' approval of the complete rendered set. The exact AI, funding and conflict declarations and the correct author pronouns remain frozen unless an explicit author decision changes them.

No further expansion of directions, maps, solvers or datasets is indicated by these results. The next stage is integration and submission preparation, not another experiment search. The current drafts and packet are not themselves the final journal upload set.
