# Post-failure diagnostic addendum: matched control for operational-center rotation

Frozen after the center decomposition showed that recovered-29's legacy +5-degree rotation combines a +12.36% operational-center rotation response with a +37.57% coherent-translation response in WCL. This arm determines whether a residual bearing/rotation-structure penalty remains after the center-induced translation is removed.

For recovered-29 and official-32-minus-BS71:
- form +5-degree rotation about the reference corrected-WCL operational centroid;
- preserve each receiver's exact displacement magnitude from that rotation and independently randomize directions over eight fixed seeds, 7750 + 13r for r=0,...,7;
- retain the same messages, n=4.7, max_gws=10, fresh per-map A0 refitting, and all four estimators.

The comparison is diagnostic only and cannot alter G4. A positive residual gap supports a substrate-specific bearing-structure component; a near-zero or negative gap indicates that the legacy recovered result was dominated by the center-induced translation component.
