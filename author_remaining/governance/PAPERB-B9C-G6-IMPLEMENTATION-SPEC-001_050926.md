# B9C G6 implementation specification

**Frozen before execution.**

- Substrates: recovered-29 and official-32-minus-BS71.
- Estimator setting: `n=4.7`, `max_gws=10`.
- Top-six/top-seven maps: eight registered direction seeds `8800+k+101*d`, `d=0,...,7`.
- Per-message treatment outcome: median error across the eight direction realizations.
- Paired statistic: median(top-seven per-message outcome) minus median(top-six per-message outcome).
- Spatial cluster labels: `floor(x / w), floor(y / w)` in the fixed projected UTM coordinate system, with `w in {500,1000,2000}` m.
- Temporal cluster labels: floor of UTC timestamp since Unix epoch into `{5,15,30}` minute bins. This is secondary because no route identifier is present.
- Cluster bootstrap: sample the observed number of occupied clusters uniformly with replacement; concatenate all messages from each selected cluster, retaining duplicate clusters when selected repeatedly.
- Replicates: 2,000 per substrate and cluster width.
- Random seeds: spatial `960000 + substrate_index*10000 + width`; temporal `970000 + substrate_index*10000 + minutes`.
- Interval: percentile 2.5th and 97.5th quantiles of the bootstrap statistic.
- Exhaustion statistic: percentage of messages newly exhausted at the top-six to top-seven transition, resampled under the same clusters.
- No bootstrap outcome changes the finite-corpus point estimate or the registered G6 rule.
