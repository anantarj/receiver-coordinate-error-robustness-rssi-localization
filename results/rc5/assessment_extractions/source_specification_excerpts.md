# Exact source excerpts supporting the targeted review checks

## code/baseline_001_e123_pairfallback_040926.py
SHA-256: `6e8881f3a83b70c49ee2b1f3892b9a2cf65e5491717c336b3e1cbace01943b2f`

Lines 511–566:
```text
511: def lattice(ev, g, r, n, obj, agg="median", tau=None, topk=25, stages=None):
512:     """DEFECT FIXED 18 Aug: --tau was DEAD. Of 39 lattice() call sites, 2 passed
513:     tau=; args.tau was referenced once, in BLOCK 13's discard-rate line. So
514:     `--tau 5` reported a 5 dB discard rate while every localization still ran at
515:     the hardcoded 3.0 -- a sweep would have shown a moving discard rate and a
516:     flat error curve, which is C7's published claim, produced by a dead flag
517:     rather than by the data. Resolving None against the module TAU makes one
518:     edit reach every call site. At the default the numbers are unchanged."""
519:     if tau is None:
520:         tau = TAU
521:     A = np.median if agg == "median" else np.mean
522:     k = g.shape[0]
523:     c = ev.wcl_estimate(g[:min(topk, k)], r[:min(topk, k)])
524:     io, jo = np.triu_indices(k, 1)
525:     z = r[io] - r[jo]
526:     keep = np.abs(z) >= tau
527:     # PAPER-B CONTRACT REPAIR 4 Sep 2026: the method specification drops
528:     # the admission threshold when fewer than two pairs survive. Without
529:     # this fallback DIFF can return the first lattice point for a degenerate
530:     # surface. ABS is unchanged.
531:     if obj != "abs" and int(keep.sum()) < 2:
532:         keep = np.ones_like(keep, dtype=bool)
533:     sa = sd = None
534:     for span, sp in (stages or ((6000.0, 600.0), (1500.0, 150.0))):
535:         Pn = ev.triangular_lattice_points(center=c, span_m=span, spacing_m=sp)
536:         lg = np.log10(np.linalg.norm(Pn[:, None, :] - g[None, :, :], axis=2) + 1.0)
537:         Ra = np.abs(r[None, :] - (-10.0 * n * lg))
538:         Rd = (np.abs(z[None, keep] - (-10.0 * n * (lg[:, io[keep]] - lg[:, jo[keep]])))
539:               if keep.any() else None)
540:         if obj == "abs":
541:             S = A(Ra, axis=1)
542:         elif obj == "diff":
543:             if Rd is None:
544:                 c = Pn[0]; continue
545:             S = A(Rd, axis=1)
546:         else:
547:             if Rd is None:
548:                 S = A(Ra, axis=1)
549:             else:
550:                 if sa is None:
551:                     i0 = int(np.argmin(np.linalg.norm(Pn - c, axis=1)))
552:                     f = lambda v: max(1.4826 * float(np.median(np.abs(v - np.median(v)))), 1e-6)
553:                     sa, sd = f(Ra[i0]), f(Rd[i0])
554:                 S = A(np.hstack([Ra / sa, Rd / sd]), axis=1)
555:         c = Pn[int(np.argmin(S))]
556:     return c
557: 
558: 
559: def fit_a0(cal, coords, n):
560:     by = {}
561:     for mm in cal:
562:         for rx in mm.receptions:
563:             if rx.gid in coords:
564:                 d = float(np.linalg.norm(coords[rx.gid] - np.array([mm.x, mm.y]))) + 1.0
565:                 by.setdefault(rx.gid, []).append(rx.rssi + 10 * n * math.log10(d))
566:     return {g: float(np.median(v)) for g, v in by.items() if len(v) >= 10}
```

Lines 583–585:
```text
583: def mkey(m):
584:     return (round(float(m.x), 3), round(float(m.y), 3),
585:             tuple(sorted((rx.gid, round(float(rx.rssi), 3)) for rx in m.receptions)))
```

Lines 2430–2478:
```text
2430:         coh_theta_at = 0.0   # E3b, set per angle
2431:         tx_centroid = np.array([np.mean([m_.x for m_ in EV]), np.mean([m_.y for m_ in EV])])  # E3
2432:         def build(base, targets, disp, seed, mode="iso"):
2433:             """New dict. mode iso = random direction, magnitude disp."""
2434:             rg = np.random.default_rng(seed); out = {}
2435:             for g, v in base.items():
2436:                 if g in targets:
2437:                     if mode == "iso":
2438:                         th = rg.uniform(0, 2*np.pi)
2439:                         out[g] = v + disp*np.array([np.cos(th), np.sin(th)])
2440:                     elif mode == "coherent":      # E3: one shared direction for all
2441:                         th = coh_theta
2442:                         out[g] = v + disp*np.array([np.cos(th), np.sin(th)])
2443:                     elif mode == "inward":        # E3: toward the transmitter centroid
2444:                         d = tx_centroid - np.asarray(v, float); nrm = float(np.linalg.norm(d))
2445:                         out[g] = v + (disp*d/nrm if nrm > 0 else 0.0)
2446:                     elif mode == "outward":       # E3b: away from the transmitter centroid
2447:                         d = np.asarray(v, float) - tx_centroid; nrm = float(np.linalg.norm(d))
2448:                         out[g] = v + (disp*d/nrm if nrm > 0 else 0.0)
2449:                     elif mode == "coherent_at":   # E3b: shared direction at a given angle
2450:                         out[g] = v + disp*np.array([np.cos(coh_theta_at), np.sin(coh_theta_at)])
2451:                     else:
2452:                         out[g] = v + rg.normal(0, disp/np.sqrt(2), 2)
2453:                 else:
2454:                     out[g] = np.array(v, float)
2455:             return out
2456: 
2457:         def score(mp, want=("wcl", "abs")):
2458:             a0m = fit_a0(cal, mp, n); ew, ea = [], []
2459:             for mm in EV:
2460:                 rx = [r for r in mm.receptions if r.gid in mp and r.gid in a0m]
2461:                 if len(rx) < 3: continue
2462:                 rx = sorted(rx, key=lambda r: -r.rssi)[:args.max_gws]
2463:                 g_ = np.vstack([mp[r.gid] for r in rx])
2464:                 raw = np.array([r.rssi for r in rx], float)
2465:                 rv = raw - np.array([a0m[r.gid] for r in rx], float)
2466:                 t = np.array([mm.x, mm.y], float)
2467:                 if "wcl" in want: ew.append(float(np.linalg.norm(wcl(ev, g_, rv) - t)))
2468:                 if "abs" in want:
2469:                     ea.append(float(np.linalg.norm(lattice(ev, g_, rv, n, "abs", "mean") - t)))
2470:             return (float(np.median(ew)) if ew else float("nan"),
2471:                     float(np.median(ea)) if ea else float("nan"), len(ew) or len(ea))
2472:         # GAP FILLED 19 Aug. The differential objective was absent from this block.
2473:         # Added as an ADDITIVE companion rather than by widening the scorer above,
2474:         # whose return arity is consumed by many call sites. No existing caller
2475:         # changes, so every figure this block already published is untouched.
2476:         def score_diff(mp):
2477:             a0m = fit_a0(cal, mp, n); out = []
2478:             for mm in EV:
```

Lines 2680–2722:
```text
2680:         # ---------- VARIANT 6 (E2c, Paper B, 3 Sep 2026): MATCHED-EXPOSURE SUBSETS.
2681:         # Random anchor subsets stratified by exposure share S: same S, different anchors.
2682:         # Pre-registered: if damage at equal S varies across compositions by more than the
2683:         # floor, exposure share is NOT the sufficient statistic (composition/geometry carries it).
2684:         if args.matched_s:
2685:             selc6 = {}
2686:             for mm in EV:
2687:                 rx = [r for r in mm.receptions if r.gid in PHYS]
2688:                 if len(rx) < 3: continue
2689:                 for r in sorted(rx, key=lambda r: -r.rssi)[:args.max_gws]:
2690:                     selc6[r.gid] = selc6.get(r.gid, 0) + 1
2691:             tot6 = float(sum(selc6.get(g, 0) for g in G))
2692:             P(f"\n  (6) MATCHED-EXPOSURE SUBSETS [E2c]. Random subsets binned by exposure share S "
2693:               f"(+/-0.025), displaced {args.corrupt_disp} m, up to 8 subsets per bin, four estimators.")
2694:             P(f"      {'S-bin':>6}{'n':>3}{'k range':>9}{'WCL med':>9}{'WCL range':>13}{'ABS med':>9}{'DIFF med':>10}{'MinMax med':>12}")
2695:             rg6 = random.Random(6606)
2696:             for Sb in (0.10, 0.20, 0.30, 0.40, 0.50):
2697:                 found, tries = [], 0
2698:                 while len(found) < 8 and tries < 4000:
2699:                     tries += 1
2700:                     k = rg6.randint(2, 14); tg = set(rg6.sample(G, k))
2701:                     S = sum(selc6.get(g, 0) for g in tg) / tot6
2702:                     if abs(S - Sb) <= 0.025: found.append((k, tg))
2703:                 if not found:
2704:                     P(f"      {Sb:>6.2f}  no subset found in bin"); continue
2705:                 A6, B6, D6, M6 = [], [], [], []
2706:                 for idx, (k, tg) in enumerate(found):
2707:                     bad = build(PHYS, tg, args.corrupt_disp, 6700 + idx)
2708:                     a, b, _ = score(bad); A6.append(100*(a-w0)/w0); B6.append(100*(b-a0r)/a0r)
2709:                     D6.append(100*(score_diff(bad)-d0_21)/d0_21); M6.append(100*(score_mm(bad)-m0_21)/m0_21)
2710:                 ks = [k for k, _ in found]
2711:                 P(f"      {Sb:>6.2f}{len(found):>3}{min(ks):>4}-{max(ks):<4}{np.median(A6):>8.1f}%"
2712:                   f"{min(A6):>6.1f}-{max(A6):<6.1f}{np.median(B6):>8.1f}%{np.median(D6):>9.1f}%{np.median(M6):>11.1f}%")
2713:             P(f"      -> KILL CONDITION (pre-registered): within-bin WCL range < floor at every S => S is sufficient.")
2714: 
2715:         # ---------- E4 (4 Sep 2026): NLLS ROBUSTNESS ARM. Additive; --nlls-arm 1.
2716:         _C_e4 = np.vstack(list(PHYS.values()))
2717:         bb_e4 = (_C_e4[:, 0].min() - 3000, _C_e4[:, 0].max() + 3000,
2718:                  _C_e4[:, 1].min() - 3000, _C_e4[:, 1].max() + 3000)
2719:         def score_nlls(mp, a0_override=None):
2720:             a0m = a0_override if a0_override is not None else fit_a0(cal, mp, n)
2721:             out = []
2722:             for mm in EV:
```

## code/deltamesh_antwerp_eval_v10_fixed_080826.py
SHA-256: `b14b35b5748e447971e5b22da7c39ededc8277aa04e5690eeff672bf1311cac5`

Lines 1168–1200:
```text
1168: def triangular_lattice_points(center: np.ndarray, span_m: float, spacing_m: float) -> np.ndarray:
1169:     """
1170:     Generate a triangular lattice in a square window of side span_m centered at 'center'.
1171:     """
1172:     # bounding box
1173:     half = span_m / 2.0
1174:     x_min = center[0] - half
1175:     x_max = center[0] + half
1176:     y_min = center[1] - half
1177:     y_max = center[1] + half
1178: 
1179:     # triangular lattice basis:
1180:     # points = i * (s,0) + j*(s/2, s*sqrt(3)/2)
1181:     s = spacing_m
1182:     dy = s * math.sqrt(3.0) / 2.0
1183: 
1184:     xs = []
1185:     ys = []
1186:     j = 0
1187:     y = y_min
1188:     while y <= y_max:
1189:         # offset every other row
1190:         offset = 0.0 if (j % 2 == 0) else s / 2.0
1191:         x = x_min + offset
1192:         while x <= x_max:
1193:             xs.append(x)
1194:             ys.append(y)
1195:             x += s
1196:         y += dy
1197:         j += 1
1198: 
1199:     return np.column_stack([np.array(xs, dtype=float), np.array(ys, dtype=float)])
1200: 
```

## scripts/build_figures.py
SHA-256: `1e3f123074d8bc0cd3e3ed5e312a601e1c4db835e0d81a40b70fba1195128303`

Lines 36–48:
```text
36: def main():
37:     FIG.mkdir(exist_ok=True);PANEL.mkdir(exist_ok=True)
38:     load=pd.read_csv(DATA/'paperb_load_surface.csv');parts=[]
39:     for i,m in enumerate(METHODS):
40:         fig,ax=chart(f'({chr(97+i)}) {m}','Corrupted receiver count','Displacement magnitude (m)')
41:         d=load[load.method==m].pivot(index='D_m',columns='f',values='effect_pct').sort_index()
42:         ax.set_position([.19,.19,.57,.65]);ax.grid(False);im=ax.imshow(d.values,origin='lower',aspect='auto',vmin=-2,vmax=846)
43:         ax.set_xticks(range(len(d.columns)),[str(x) for x in d.columns]);ax.set_yticks(range(len(d.index)),[f'{x:,}' for x in d.index])
44:         cax=fig.add_axes([.79,.19,.035,.65]);cb=fig.colorbar(im,cax=cax);cb.set_label('Median error change (%)',fontsize=8);cb.ax.tick_params(labelsize=7)
45:         parts.append(save_panel(fig,'Fig1_'+m.replace('-','')))
46:     assemble('Fig1_Corruption_Load_Surface.pdf',parts,2,['results/figure_data/paperb_load_surface.csv'],'R29; 8 draws except 500 m: 32 draws. All five expansion magnitudes; no antecedent 5-km cross-section.')
47:     e=pd.read_csv(DATA/'paperb_exposure_5km_w10.csv');parts=[]
48:     for i,m in enumerate(METHODS):
```
