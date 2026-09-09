# Paper B — Stage B9C Preregistered Reference-Substrate and Robustness Safeguard Protocol

**Protocol date:** 5 September 2026  
**Scientific authority entering stage:** B9B  
**Status at freeze:** protocol and decision rules frozen before result adjudication  
**Purpose:** preempt the most credible IEEE Access “reject — updates required” objections without reopening the broad experiment programme or selecting favorable post-hoc outcomes.

## 1. Reviewer questions being addressed

B9C addresses five reviewer-facing questions:

1. Do the three Paper-B conclusions depend materially on using the correlation-audited recovered-29 substrate rather than the metadata-derived official-33 assignment?
2. Is any official-map result dominated by the known BS 71 catalogue anomaly?
3. Does the top-six-to-top-seven localization transition survive a pure coordinate-assignment comparison, a native official-map analysis, and compact changes of the propagation exponent?
4. Do key effects survive spatial/campaign dependence checks rather than relying only on iid-message orientation intervals?
5. Are kilometre-scale perturbations appropriately tied to registration, catalogue, label, frame, and self-localization failures rather than represented as ordinary GNSS noise?

## 2. Frozen scientific boundaries

B9C does not:

- change the B9B primary conclusions after seeing new outputs;
- add NLLS;
- tune an estimator on official-33;
- select a favorable receiver roster, direction, corruption magnitude, or propagation exponent;
- replace the B9B recovered-29 experiment;
- treat official-33 and recovered-29 native-roster comparisons as assignment-only effects;
- treat repeated directions or repeated evaluations of the same messages as independent observations.

The following remain fixed wherever technically applicable:

- dataset release: Antwerp LoRaWAN version 1.3;
- split and evaluation-message identities;
- duplicate-removal rule;
- four estimators: WCL, ABS, DIFF, and Min-Max;
- DIFF fewer-than-two-pair fallback;
- receiver ranking from clean-message selection frequency;
- corruption targets, seeds, and registered directions;
- receiver-specific-intercept refit policy;
- default path-loss exponent \(n=4.7\).

## 3. Coordinate substrates

### R29 — recovered-29

The existing B9B primary reference. It remains the main experiment because B9B was designed and frozen on this substrate.

### R27/O27 — common-roster assignment isolation

The 27 receiver identities common to recovered-29 and official-33 are evaluated on one common message roster. Only coordinates change. This is the principal assignment-only sensitivity test.

Results are also repeated after excluding BS 71 if it belongs to the common roster. This prevents the known catalogue anomaly from deciding the whole assignment comparison.

### O33 — native official-33

All official-33 mapped receivers are used under the same selection and calibration rules. Because the roster and eligible population can differ from R29, O33 is an operational sensitivity, not a pure coordinate-effect estimate.

### O33−71 and O33-R71

Two anomaly controls are retained:

- O33−71 excludes BS 71 before message eligibility and selection.
- O33-R71 retains the official roster but substitutes the independently documented repaired BS 71 coordinate. This arm is secondary and must always be labelled as an anomaly repair.

## 4. Prespecified experiment set

### B9C-E1 — sparse/intermediate/dense load

For each admissible substrate:

- displacement magnitudes: 1 km and 10 km;
- corrupted receiver counts: 1, 7, and all receivers in the substrate;
- eight registered receiver/direction draws where a subset is selected;
- all four estimators;
- fresh receiver-intercept refit, matching B9B.

Purpose: test whether the sparse-versus-dense regime and architecture dependence survive coordinate-substrate change.

### B9C-E2 — exposure-boundary sensitivity

At 5 km:

- top-\(k\) receiver sets for \(k=1,\ldots,10\), extended to 14 when the roster permits;
- standard `max_gws=10`;
- compact `max_gws=5` repeat for \(k=5,6,7,8\);
- registered directions retained from B9B;
- top, bottom, and random controls at \(k=6\) and \(k=7\).

Purpose: determine whether the location and direction of the \(k=6\rightarrow7\) transition survive assignment and native-roster changes.

### B9C-E3 — selection-set exhaustion

Recompute \(C(k)=P(G_q\subseteq T_k)\) and \(\Delta C(k)\) for:

- O33;
- O33−71;
- the common-roster assignment-isolation population.

No receiver coordinates enter the statistic after the eligible roster and selected sets are fixed. Native-roster results are not described as independent replications of R29.

### B9C-E4 — spatial-structure sensitivity

Two compact spatial contrasts are fixed:

1. rigid rotation at \(5^\circ\) versus eight matched-isotropic directions using the rotation arm's median receiver displacement;
2. 1-km coherent translation versus eight isotropic directions.

All four estimators are retained.

Purpose: test the qualitative claim that equal coordinate displacement magnitudes are not interchangeable and that affine/directional structure interacts with architecture.

### B9C-E5 — propagation-exponent sensitivity

Repeat only the following representative contrasts at \(n\in\{3.5,4.7,6.0\}\):

- one-receiver versus all-receiver corruption at 10 km;
- top-six versus top-seven at 5 km;
- \(5^\circ\) rotation versus matched-isotropic displacement.

Receiver intercepts are recalibrated at each \(n\). No value of \(n\) is selected as “best.”

### B9C-E6 — dependence-aware precision sensitivity

For key paired contrasts, resample complete spatial cells rather than individual messages:

- primary cell width: 1 km in projected coordinates;
- sensitivity widths: 500 m and 2 km;
- 2,000 deterministic bootstrap replicates per width;
- statistics: difference of message-level medians for top-seven versus top-six under each estimator, and \(\Delta C(7)\);
- all messages in a sampled cell are retained together;
- if timestamps and route identifiers permit, a route/time-block bootstrap is reported as a secondary check.

This analysis supplements, but does not overwrite, the finite-corpus and perturbation-design summaries in B9B.

## 5. Frozen decision gates

### G1 — load-regime transfer

At 10 km on O33−71:

- each one-receiver absolute median effect must be no greater than 10%;
- each full-roster effect must be positive and at least 100%;
- the full-roster effect must exceed the corresponding one-receiver effect for all four estimators.

Failure does not invalidate B9B. It requires the sparse/dense statement to be explicitly substrate-conditioned and the substrate interaction to be reported.

### G2 — exposure-boundary transfer

For O33−71 and the O27 assignment-only arm:

- all four \(k=6\rightarrow7\) degradation jumps must be positive;
- \(k=7\) must be the largest early increment through \(k=8\) for at least three of four architectures;
- no claim of a universal cliff magnitude is permitted.

Failure requires removal of substrate-general language and presentation of the recovered-29 transition as a deployment/substrate-specific result.

### G3 — BS 71 non-dominance

The sign and qualitative classification of G1 and G2 must agree between O33−71 and O33-R71. If O33-published differs only because of BS 71, the manuscript must say so explicitly.

### G4 — spatial-structure transfer

On O33−71:

- the WCL \(5^\circ\)-rotation minus matched-isotropic excess must remain positive;
- at least two of four architectures must show an absolute rotation-versus-isotropic difference of at least 10 percentage points, or the coherent-versus-isotropic contrast must meet that condition;
- no universal architecture ordering is inferred.

Failure narrows the spatial claim to recovered-29 and reports substrate dependence.

### G5 — exponent stability

Across \(n=3.5,4.7,6.0\), the direction of the sparse-versus-dense, top-six-versus-top-seven, and structured-versus-isotropic contrasts must remain unchanged for at least three of four architectures.

Failure requires explicit \(n\)-conditioning in the abstract, synthesis, and conclusion.

### G6 — dependence sensitivity

For the 1-km spatial-cell bootstrap:

- the 95% interval for the top-seven minus top-six median-error difference must exclude zero for WCL;
- at least three of four architectures must retain a positive point estimate at every cell width;
- the exhaustion increment must remain positive at all three cell widths.

Failure removes inferential language and retains only corpus-descriptive effect sizes.

## 6. Manuscript actions fixed before results

### If G1–G6 pass

Add:

- one compact main-text table or panel summarizing substrate, anomaly, exponent, and block-bootstrap sensitivity;
- one paragraph in Experimental Apparatus defining the substrate hierarchy;
- one subsection after the three principal result axes titled “Reference-substrate and dependence sensitivity”;
- full tables and diagnostics in Supplement S12;
- a claim-to-artifact extension and exact run manifest.

The abstract gains at most one bounded sentence; no new fourth contribution is created.

### If one or more gates fail

Report the failure. Do not suppress the arm or replace its threshold. Revise the relevant claim to the narrower level supported:

- recovered-29-specific;
- official-substrate-specific;
- BS-71-sensitive;
- \(n\)-conditioned;
- corpus-descriptive rather than dependence-robust.

A failed transfer can itself strengthen the paper's central thesis that coordinate-error risk depends on substrate and architecture, but it cannot be relabelled as successful robustness.

## 7. Stop rule

After B9C-E1 through E6 and the corresponding manuscript integration, no additional Paper-B experiment is authorized before submission unless:

- B9C identifies a reproducibility defect;
- a result contradicts a headline claim and needs a single diagnostic required to locate the defect;
- the final official-template cold read reveals a scientific inconsistency.

A second external localization deployment is reserved as a contingent B9D escalation, not an automatic expansion. It is justified only if B9C leaves the principal contribution dependent on recovered-29 in a way that cannot be adequately bounded.
