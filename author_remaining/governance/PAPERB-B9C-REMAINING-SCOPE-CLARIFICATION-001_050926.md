# Paper B B9C remaining-stage scope clarification

**Date:** 5 September 2026  
**Timing:** frozen before execution of exact-seven, G5, or G6 outputs in this stage.  
**Authority:** the original B9C protocol remains controlling; this document resolves only implementation ambiguities.

## Exact-seven completion

The exact `f=7` intermediate-load cells will be evaluated at 1 km and 10 km with eight canonical receiver-choice/direction draws for all available frozen coordinate rosters: recovered-29, official-32-minus-BS71, official-33 published, official-33 with BS71 substituted, recovered/official common-27, and recovered/official common-26-minus-BS71. The canonical target and perturbation seeds are retained:

- target selection: `Random(9100 + 31*7 + draw)`;
- displacement directions: `default_rng(7700 + 31*7 + draw)`.

These cells complete E1 but do not redefine G1, whose sparse/full endpoints are already adjudicated.

## G5 substrate and contrast scope

Because the original protocol did not name one substrate for G5, the registered contrasts will be evaluated independently on both:

1. recovered-29, the B9B primary substrate; and
2. official-32-minus-BS71, the principal anomaly-free official-coordinate sensitivity substrate.

At each `n in {3.5, 4.7, 6.0}`, receiver intercepts are recalibrated. Eight registered perturbation draws are used for one-receiver, all-receiver, top-six, top-seven, and isotropic controls.

The frozen G5 rotation contrast is the legacy unweighted-centroid rotation versus its eight-direction median-displacement-matched isotropic comparator. Its sign may legitimately differ by substrate after G4; G5 asks whether that substrate-specific direction remains stable across `n`. The operational-centroid/exact-magnitude rotation contrast is retained as a secondary explanatory sensitivity and cannot replace the frozen legacy contrast.

G5 is evaluated per contrast: at least three of four architectures must retain an unchanged sign across all three `n` values on each substrate. No `n` is selected as preferable.

## G6 estimand and dependence implementation

G6 is evaluated independently on recovered-29 and official-32-minus-BS71 at `n=4.7`, `max_gws=10`.

For top-six and top-seven, each message is evaluated under the same eight registered direction seeds. The message-level treatment outcome is the median error across the eight directions. The paired statistic is:

`median_i(median_r(error_top7[i,r])) - median_i(median_r(error_top6[i,r]))`.

Spatial cells are fixed on transmitter UTM coordinates at widths 500 m, 1 km, and 2 km. Occupied cells are sampled with replacement as complete clusters for 2,000 deterministic replicates per width. The number of occupied cells is preserved in each bootstrap draw; every message in a selected cell is retained together.

The exhaustion statistic uses the finite-corpus indicator that a message is newly exhausted at the top-six to top-seven transition. It is resampled with the same spatial cells.

The dataset contains timestamps but no route identifier. A secondary temporal-cluster analysis therefore uses fixed wall-clock bins of 5, 15, and 30 minutes, with the same cluster-bootstrap procedure. These secondary intervals do not replace the preregistered spatial-cell result.

## Non-retrospective rule

G4 remains failed under its frozen legacy transfer criterion. No G5 or G6 outcome can convert G4 to a pass. The post-failure rotation diagnosis may deepen interpretation only as explicitly labelled explanatory evidence.
