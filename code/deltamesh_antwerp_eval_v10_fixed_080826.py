#!/usr/bin/env python3
"""
DeltaMesh (Pairwise RSSI-Difference Triangular Lattice Search) — Antwerp evaluation script (improved gateway handling)

Why this exists:
- The Antwerp LoRaWAN dataset variant commonly used in papers does NOT always ship with gateway GPS coordinates.
- Pure geometry-based methods (trilateration, DeltaMesh) need anchor coordinates, so we must either:
  (a) load true gateway coordinates from a mapping file, OR
  (b) estimate them from training messages (using known transmitter GPS in the dataset).

This script supports two gateway estimators:
1) "centroid"  (baseline): weighted centroid of top-K strongest receptions per gateway (fast but can be biased).
2) "rssfit"    (recommended): fit each gateway (x,y) by minimizing a robust RSSI log-distance residual
                              (also yields a per-gateway intercept A0_hat that can be used for bias correction).

Key option:
- --bias-correct : subtract per-gateway A0_hat from RSSI before DeltaMesh scoring (reduces gateway-specific offsets).

Notes:
- This is an OUT-OF-REGIME validation for DeltaMesh if the deployment is sparse and gateways do not surround the device.
- WCL is included as a geometry-agnostic baseline and can outperform geometry-based methods when anchors are uncertain.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from pyproj import Transformer

# Optional: SciPy for least squares trilateration
try:
    from scipy.optimize import least_squares  # type: ignore
except Exception:
    least_squares = None

# [STAGE1-FIX D3] linear_sum_assignment was referenced at line 515 but never
# imported. [STAGE1-FIX D2] _HAVE_SCIPY was referenced at line 513 but never
# defined. Both made the Hungarian snapping branch unreachable/fatal.
try:
    from scipy.optimize import linear_sum_assignment  # type: ignore
    _HAVE_SCIPY = True
except Exception:
    linear_sum_assignment = None
    _HAVE_SCIPY = False


# ----------------------------
# Data structures
# ----------------------------
@dataclass
class Rx:
    gid: str
    rssi: float  # dBm


@dataclass
class Message:
    x: float
    y: float
    receptions: List[Rx]


# ----------------------------
# Coordinate conversion
# ----------------------------
def utm_epsg_from_lon(lon: float) -> int:
    """Return EPSG code for UTM zone in northern hemisphere (dataset is Antwerp)."""
    zone = int((lon + 180.0) / 6.0) + 1
    return 32600 + zone


def make_transformer(lat0: float, lon0: float) -> Transformer:
    epsg = utm_epsg_from_lon(lon0)
    return Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

def compute_xy_bbox(msgs: Sequence[Message], pad_m: float = 0.0) -> Tuple[float, float, float, float]:
    """Bounding box in XY for a set of messages.

    Returns: (xmin, xmax, ymin, ymax) in meters.
    """
    if not msgs:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [m.x for m in msgs]
    ys = [m.y for m in msgs]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    return (xmin - pad_m, xmax + pad_m, ymin - pad_m, ymax + pad_m)


def filter_gw_xy_by_bbox(
    gw_xy: Dict[str, Tuple[float, float]],
    bbox: Tuple[float, float, float, float],
    margin_m: float = 0.0,
) -> Dict[str, Tuple[float, float]]:
    """Filter gateway XY dict to those within bbox (+ optional margin).

    bbox: (xmin, xmax, ymin, ymax) in meters.
    margin_m: expand bbox by this margin (meters).
    """
    xmin, xmax, ymin, ymax = bbox
    xmin -= float(margin_m)
    xmax += float(margin_m)
    ymin -= float(margin_m)
    ymax += float(margin_m)
    out: Dict[str, Tuple[float, float]] = {}
    for k, (x, y) in gw_xy.items():
        if (xmin <= x <= xmax) and (ymin <= y <= ymax):
            out[k] = (x, y)
    return out

# ----------------------------
# Dataset loading
# ----------------------------
def load_antwerp_csv(
    path: str,
    min_gws: int,
    *,
    rssi_floor: float = -150.0,
    rssi_ceil: float = -20.0,
    max_hdop: Optional[float] = None,
    sample_rows_for_col_check: int = 5000,
) -> List[Message]:
    """
    Load Antwerp-style LoRaWAN dataset into the internal "messages" representation.

    The Antwerp CSVs floating around in the wild appear in (at least) two common *wide* formats:

    (A) "BS columns" format (common in the Aernouts/Antwerp dump):
        - latitude / longitude columns (e.g., 'latitude','longitude' or 'lat','lon')
        - one RSSI column per gateway/base-station:
            'BS 1', 'BS 2', ... (values are RSSI in dBm, NaN when not heard)

    (B) "rssi columns" format:
        - latitude / longitude columns
        - per-gateway RSSI columns containing the token 'rssi', e.g.
            'gw_12_rssi', 'gateway_5_rssi', 'RSSI_34', ...

    This loader auto-detects both formats. If your file is in long format
    (one row per reception with 'gateway_id' and 'rssi'), you must pivot it
    first or extend this loader.
    """
    # Robust read: try comma first, then semicolon.
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.read_csv(path, sep=";")

    # ----------------------------
    # Lat / Lon column detection
    # ----------------------------
    lat_col = None
    lon_col = None
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in ("lat", "latitude", "gps_lat", "gpslat"):
            lat_col = c
        if cl in ("lon", "lng", "longitude", "gps_lon", "gpslng", "gpslon"):
            lon_col = c
    if lat_col is None or lon_col is None:
        raise ValueError(
            "Could not find latitude/longitude columns. "
            "Expected something like lat/lon or latitude/longitude. "
            f"Columns seen: {list(df.columns)[:40]}{'...' if len(df.columns)>40 else ''}"
        )

    lat0 = float(df.iloc[0][lat_col])
    lon0 = float(df.iloc[0][lon_col])
    tfm = make_transformer(lat0, lon0)

    # ----------------------------
    # RSSI column detection
    # ----------------------------
    cols = [str(c) for c in df.columns]

    # Candidate set 1: Antwerp-style wide format columns like "BS 12".
    bs_cols: List[str] = []
    bs_re = re.compile(r"(?i)^\s*bs[\s_\-]*\d+\s*$")
    for c in cols:
        if c in (str(lat_col), str(lon_col)):
            continue
        if bs_re.match(c):
            bs_cols.append(c)

    # Candidate set 2: generic columns containing "rssi".
    rssi_cols: List[str] = []
    for c in cols:
        if c in (str(lat_col), str(lon_col)):
            continue
        if "rssi" in c.lower():
            rssi_cols.append(c)

    if not bs_cols and not rssi_cols:
        raise ValueError(
            "Could not find any gateway RSSI columns. "
            "This script supports wide-format columns either like 'BS 1'/'BS 2'/... "
            "or columns containing 'rssi' (e.g., gw_12_rssi). "
            f"Columns seen: {list(df.columns)[:60]}{'...' if len(df.columns)>60 else ''}"
        )

    # NOTE: Some datasets use "BS <id>" columns as *flags* (0/1) or other
    # metadata rather than RSSI. Conversely, some use "rssi_*" as the actual
    # RSSI values. We choose the column family whose values look like RSSI.
    def _score_candidate_cols(candidate_cols: List[str]) -> float:
        if not candidate_cols:
            return -1.0
        sample = df[candidate_cols].head(sample_rows_for_col_check).copy()
        sample = sample.apply(pd.to_numeric, errors="coerce")
        vals = sample.to_numpy(dtype=float, copy=False)
        mask = np.isfinite(vals)
        if mask.sum() == 0:
            return -1.0
        inrange = (vals >= rssi_floor) & (vals <= rssi_ceil) & mask
        return float(inrange.sum() / mask.sum())

    score_bs = _score_candidate_cols(bs_cols)
    score_rssi = _score_candidate_cols(rssi_cols)

    # Prefer the higher-score family; tie-break to rssi_cols (more explicit).
    if score_rssi >= score_bs:
        use_bs = False
        rssi_like_cols = rssi_cols
    else:
        use_bs = True
        rssi_like_cols = bs_cols

    print(
        f"RSSI column family selection: use_bs={use_bs} "
        f"(score_bs={score_bs:.3f}, score_rssi={score_rssi:.3f}) | "
        f"n_cols={len(rssi_like_cols)} | rssi_range=[{rssi_floor},{rssi_ceil}]"
    )

    # Lightweight sanity check on the chosen family.
    try:
        _samp = df[rssi_like_cols].head(sample_rows_for_col_check).apply(pd.to_numeric, errors="coerce")
        _vals = _samp.to_numpy(dtype=float, copy=False)
        _mask = np.isfinite(_vals) & (_vals >= rssi_floor) & (_vals <= rssi_ceil)
        if _mask.sum() > 0:
            _v = _vals[_mask]
            q = np.quantile(_v, [0.01, 0.5, 0.99])
            print(
                "RSSI sample stats (filtered): "
                f"count={_v.size} | min={_v.min():.1f} | p01={q[0]:.1f} | "
                f"median={q[1]:.1f} | p99={q[2]:.1f} | max={_v.max():.1f}"
            )
        else:
            print("RSSI sample stats: no values within the specified rssi_range. ")
    except Exception as e:
        print(f"RSSI sample stats skipped due to error: {e}")

    # ----------------------------
    # Row -> Message conversion
    # ----------------------------
    messages: List[Message] = []
    for _, row in df.iterrows():
        # Optional GPS quality filtering (Antwerp provides HDOP).
        if max_hdop is not None and "HDOP" in df.columns:
            try:
                hdop_val = float(row["HDOP"])
            except Exception:
                hdop_val = float("nan")
            if np.isfinite(hdop_val) and hdop_val > max_hdop:
                continue

        lat = float(row[lat_col])
        lon = float(row[lon_col])
        x, y = tfm.transform(lon, lat)

        rxs: List[Rx] = []
        for c in rssi_like_cols:
            val = row[c]
            if pd.isna(val):
                continue
            try:
                rssi = float(val)
            except Exception:
                continue

            # Filter out common sentinel encodings for "no reception".
            # Typical LoRa RSSI is roughly [-137, -30] dBm; we use configurable
            # bounds and drop anything outside.
            if not np.isfinite(rssi):
                continue
            if rssi < rssi_floor or rssi > rssi_ceil:
                continue

            if use_bs:
                # 'BS 12' -> gid '12'
                m = re.search(r"(\d+)", str(c))
                gid = m.group(1) if m else str(c).strip()
            else:
                # gateway id extraction: strip common prefixes/suffixes from column name
                gid = str(c)
                gid = gid.replace("rssi", "").replace("RSSI", "")
                gid = gid.replace("__", "_").strip("_").strip()

            rxs.append(Rx(gid=str(gid), rssi=rssi))

        if len(rxs) >= min_gws:
            # sort strongest first (less negative)
            rxs.sort(key=lambda r: r.rssi, reverse=True)
            messages.append(Message(x=x, y=y, receptions=rxs))

    return messages



def utm_epsg_from_latlon(lat: float, lon: float) -> int:
    """Return EPSG code for the UTM zone containing (lat, lon)."""
    zone = int((lon + 180.0) // 6.0) + 1
    if lat >= 0:
        return 32600 + zone  # WGS84 / UTM Northern Hemisphere
    return 32700 + zone       # WGS84 / UTM Southern Hemisphere

def latlon_to_utm(lat: float, lon: float, epsg: Optional[int] = None) -> Tuple[float, float]:
    """Convert (lat, lon) in degrees to (x, y) in meters (UTM)."""
    if epsg is None:
        epsg = utm_epsg_from_latlon(lat, lon)
    tfm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = tfm.transform(lon, lat)
    return float(x), float(y)

def _extract_lat_lon(obj) -> Optional[Tuple[float, float]]:
    """Try to extract (lat, lon) from a variety of JSON structures."""

    if obj is None:
        return None

    if isinstance(obj, dict):
        # Direct (lat, lon) keys.
        lat_val = None
        lon_val = None
        for k in ("latitude", "lat", "Latitude", "Lat"):
            if k in obj:
                lat_val = obj[k]
                break
        for k in ("longitude", "lon", "long", "Longitude", "Lon", "Lng", "lng"):
            if k in obj:
                lon_val = obj[k]
                break

        if lat_val is not None and lon_val is not None:
            try:
                lat = float(lat_val)
                lon = float(lon_val)
                if np.isfinite(lat) and np.isfinite(lon):
                    return lat, lon
            except Exception:
                pass

        # Nested coordinate structures.
        for ck in ("coords", "coordinate", "coordinates", "location", "pos", "position"):
            if ck in obj:
                ll = _extract_lat_lon(obj[ck])
                if ll is not None:
                    return ll
        return None

    if isinstance(obj, (list, tuple)) and len(obj) >= 2:
        try:
            a = float(obj[0])
            b = float(obj[1])
        except Exception:
            return None
        if not (np.isfinite(a) and np.isfinite(b)):
            return None

        # Heuristic: decide which component is latitude.
        if -90.0 <= a <= 90.0 and -180.0 <= b <= 180.0:
            return a, b
        if -90.0 <= b <= 90.0 and -180.0 <= a <= 180.0:
            return b, a
        return None

    return None


def load_gateway_locations(json_path: str) -> Dict[str, Tuple[float, float]]:
    """Load a gateway-location JSON file.

    Supported formats:
      1) dict: {"<gw_id>": {"lat": .., "lon": ..}} (keys may also be latitude/longitude)
      2) dict: {"<gw_id>": [lat, lon]} or {"<gw_id>": (lat, lon)}
      3) list of dicts: [{"id": "...", "lat": .., "lon": ..}, ...]

    Returns:
      mapping: dict {gateway_id -> (x_m, y_m)} in a projected (approx-meters) coordinate system.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    mapping: Dict[str, Tuple[float, float]] = {}

    def _extract_latlon(d: dict):
        lat = d.get("lat", d.get("latitude"))
        lon = d.get("lon", d.get("longitude"))
        return lat, lon

    def _extract_xy(d: dict):
        x = d.get("x")
        y = d.get("y")
        return x, y

    # if isinstance(data, dict):
    #     for gid, v in data.items():
    #         lat = lon = None
    #         x = y = None

    #         if isinstance(v, dict):
    #             x, y = _extract_xy(v)
    #             if x is not None and y is not None:
    #                 mapping[str(gid)] = (float(x), float(y))
    #                 continue
    #             lat, lon = _extract_latlon(v)

    #         elif isinstance(v, (list, tuple)) and len(v) >= 2:
    #             lat, lon = v[0], v[1]

    #         if lat is None or lon is None:
    #             continue

    #         try:
    #             x, y = latlon_to_xy_utm(float(lat), float(lon))
    #         except Exception:
    #             continue
    #         mapping[str(gid)] = (x, y)

    #     return mapping

    if isinstance(data, dict):
        # Could be a mapping id -> (x,y), id -> (lat,lon), or id -> dict
        for gid, v in data.items():
            lat = lon = None
            x = y = None

            if isinstance(v, dict):
                x, y = _extract_xy(v)
                if x is not None and y is not None:
                    mapping[str(gid)] = (float(x), float(y))
                    continue
                lat, lon = _extract_latlon(v)

            elif isinstance(v, (list, tuple)) and len(v) >= 2:
                lat, lon = v[0], v[1]

            if lat is None or lon is None:
                continue

            try:
                x, y = latlon_to_utm(float(lat), float(lon))  # [STAGE1-FIX D1]
            except Exception:
                continue
            mapping[str(gid)] = (x, y)

        return mapping    

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            gid = item.get("id") or item.get("gateway") or item.get("gw_id")
            if gid is None:
                continue
            lat, lon = _extract_latlon(item)
            if lat is None or lon is None:
                continue
            try:
                x, y = latlon_to_utm(float(lat), float(lon))  # [STAGE1-FIX D1]
            except Exception:
                continue
            mapping[str(gid)] = (x, y)
        return mapping

    return mapping


def greedy_snap_estimated_to_known(
    est_xy: Dict[str, Tuple[float, float]],
    known_xy: Dict[str, Tuple[float, float]],
    method: str = "hungarian",
    max_dist_m: float = float("inf"),   # [STAGE1-FIX D4] was passed at call site but absent here
) -> Tuple[Dict[str, Tuple[str, float]], Dict[str, Tuple[float, float]]]:
    """Snap estimated gateway positions to a set of known gateway positions.

    Args:
      est_xy: {label -> (x,y)} estimated positions (e.g., BS 1..BS72)
      known_xy: {gateway_id -> (x,y)} known positions
      method: 'hungarian' (global assignment) or 'greedy' (local nearest-neighbour)

    Returns:
      mapping: {label -> (gateway_id, distance_m)}
      snapped_xy: {label -> (x,y)} snapped positions (in known coord frame)
    """
    if not est_xy or not known_xy:
        return {}, dict(est_xy)

    method = (method or "").strip().lower()
    if method not in {"hungarian", "greedy"}:
        method = "greedy"

    labels = list(est_xy.keys())
    gids = list(known_xy.keys())

    # Build cost matrix (Euclidean distance)
    import numpy as _np

    E = _np.array([est_xy[k] for k in labels], dtype=float)
    K = _np.array([known_xy[k] for k in gids], dtype=float)

    # cost[i,j] = ||E_i - K_j||
    diff = E[:, None, :] - K[None, :, :]
    cost = _np.sqrt(_np.sum(diff * diff, axis=2))

    mapping: Dict[str, Tuple[str, float]] = {}
    snapped_xy: Dict[str, Tuple[float, float]] = {}

    if method == "hungarian" and _HAVE_SCIPY:
        # Rectangular assignment: one unique known gateway per estimated label.
        row_ind, col_ind = linear_sum_assignment(cost)
        used = set()
        for r, c in zip(row_ind, col_ind):
            lab = labels[int(r)]
            gid = gids[int(c)]
            d = float(cost[int(r), int(c)])
            if d > max_dist_m:          # [STAGE1-FIX D4] reject implausible assignments
                snapped_xy[lab] = est_xy[lab]
                continue
            mapping[lab] = (gid, d)
            snapped_xy[lab] = tuple(map(float, known_xy[gid]))
            used.add(gid)

        # Any labels not assigned (shouldn't happen when n_known >= n_est), keep estimate.
        for lab in labels:
            if lab not in snapped_xy:
                snapped_xy[lab] = est_xy[lab]

        return mapping, snapped_xy

    # Fallback greedy (nearest unused)
    unused = set(gids)
    for i, lab in enumerate(labels):
        # pick nearest unused known
        best_gid = None
        best_d = float("inf")
        for j, gid in enumerate(gids):
            if gid not in unused:
                continue
            d = float(cost[i, j])
            if d < best_d:
                best_d = d
                best_gid = gid
        if best_gid is None or best_d > max_dist_m:   # [STAGE1-FIX D4]
            snapped_xy[lab] = est_xy[lab]
            continue
        unused.remove(best_gid)
        mapping[lab] = (best_gid, best_d)
        snapped_xy[lab] = tuple(map(float, known_xy[best_gid]))

    return mapping, snapped_xy
# ---------------------------------------------------------------------------
# Gateway subset selection & optional robust trimming
# ---------------------------------------------------------------------------

def _cross(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Monotonic chain convex hull. Returns hull vertices in CCW order."""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def _poly_area(poly: List[Tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def _hull_area(points: List[Tuple[float, float]]) -> float:
    return _poly_area(_convex_hull(points))


def _pairwise_max_distance(points: List[Tuple[float, float]]) -> float:
    """Max pairwise distance (meters) for small point sets."""
    if len(points) < 2:
        return 0.0
    best = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        for j in range(i + 1, len(points)):
            x2, y2 = points[j]
            d = math.hypot(x2 - x1, y2 - y1)
            if d > best:
                best = d
    return best


def select_gateways_by_geometry(
    receptions: List[Reception],
    gw_xy: Dict[str, Tuple[float, float]],
    k: int,
    seed: int = 0,
) -> List[Reception]:
    """
    Geometry-aware gateway selection: greedily expand convex-hull area of selected gateways.
    Uses ONLY gateway coordinates (and deterministic tie-breaking); does not use device ground truth.

    Returns up to k receptions (may be <k if coordinates are missing).
    """
    # Keep only receptions with known gateway coordinates
    cand = [rx for rx in receptions if rx.gid in gw_xy]
    if k <= 0 or not cand:
        return []
    if len(cand) <= k:
        return cand

    # Deterministic ordering with RSSI tie-break (higher RSSI first), then gid
    cand = sorted(cand, key=lambda r: (-r.rssi, r.gid))

    rng = random.Random(seed)

    # Start with the strongest gateway (stable), then pick farthest for geometric spread
    selected: List[Reception] = [cand[0]]
    remaining = cand[1:]

    def xy_of(rx: Reception) -> Tuple[float, float]:
        p = gw_xy[rx.gid]
        return (float(p[0]), float(p[1]))

    while len(selected) < k and remaining:
        if len(selected) == 1:
            # pick farthest from first
            x0, y0 = xy_of(selected[0])
            best_i, best_d = 0, -1.0
            for i, rx in enumerate(remaining):
                x, y = xy_of(rx)
                d = math.hypot(x - x0, y - y0)
                if d > best_d:
                    best_d, best_i = d, i
            selected.append(remaining.pop(best_i))
            continue

        sel_pts = [xy_of(rx) for rx in selected]
        base_area = _hull_area(sel_pts)
        best_score = -1.0
        best_idxs: List[int] = []

        for i, rx in enumerate(remaining):
            pts = sel_pts + [xy_of(rx)]
            area = _hull_area(pts)
            # score: primary = hull area; secondary = max pairwise dist
            score = area
            if score > best_score + 1e-9:
                best_score = score
                best_idxs = [i]
            elif abs(score - best_score) <= 1e-9:
                best_idxs.append(i)

        if not best_idxs:
            break

        # tie-break by max pairwise distance increase, then RSSI
        if len(best_idxs) > 1:
            best_i = best_idxs[0]
            best_tiebreak = -1.0
            current_maxd = _pairwise_max_distance(sel_pts)
            for i in best_idxs:
                rx = remaining[i]
                pts = sel_pts + [xy_of(rx)]
                maxd = _pairwise_max_distance(pts)
                tiebreak = maxd - current_maxd
                if tiebreak > best_tiebreak + 1e-9:
                    best_tiebreak = tiebreak
                    best_i = i
                elif abs(tiebreak - best_tiebreak) <= 1e-9:
                    # choose higher RSSI
                    if remaining[i].rssi > remaining[best_i].rssi:
                        best_i = i
            selected.append(remaining.pop(best_i))
        else:
            selected.append(remaining.pop(best_idxs[0]))

    return selected


def select_gateways_subset(
    receptions_sorted_by_rssi: List[Reception],
    gw_xy: Dict[str, Tuple[float, float]],
    k: int,
    mode: str = "rssi",
    hybrid_pool_factor: float = 2.0,
    seed: int = 0,
) -> List[Reception]:
    """
    Select up to k gateways from receptions.

    mode:
      - 'rssi'     : take top-k by RSSI (current behavior)
      - 'geometry' : greedily maximize convex-hull area of chosen gateways
      - 'hybrid'   : run geometry selection on a pool of top (pool_factor*k) by RSSI
    """
    if k <= 0:
        return []

    mode = (mode or "rssi").lower().strip()
    cand = [rx for rx in receptions_sorted_by_rssi if rx.gid in gw_xy]
    if not cand:
        return []

    if mode == "rssi":
        return cand[:k]

    pool_k = max(k, int(math.ceil(hybrid_pool_factor * k)))
    pool = cand[:pool_k]

    if mode == "geometry":
        return select_gateways_by_geometry(cand, gw_xy, k=k, seed=seed)

    if mode == "hybrid":
        # Geometry selection on RSSI-filtered pool; tie-breaking already favors higher RSSI.
        return select_gateways_by_geometry(pool, gw_xy, k=k, seed=seed)

    raise ValueError(f"Unknown gw-select mode: {mode!r}")


def _wcl_xy_quick(receptions: List[Reception], gw_xy: Dict[str, Tuple[float, float]]) -> Tuple[float, float]:
    """Lightweight WCL position (used only for residual trimming pre-processing)."""
    pts = []
    ws = []
    for rx in receptions:
        if rx.gid not in gw_xy:
            continue
        x, y = gw_xy[rx.gid]
        # convert RSSI to positive weight; clamp for stability
        w = math.exp(max(-140.0, min(-30.0, rx.rssi)) / 10.0)
        pts.append((x, y))
        ws.append(w)
    if not pts:
        return (0.0, 0.0)
    wsum = sum(ws) if sum(ws) > 0 else 1.0
    x = sum(p[0] * w for p, w in zip(pts, ws)) / wsum
    y = sum(p[1] * w for p, w in zip(pts, ws)) / wsum
    return (x, y)


def _robust_z_scores(values: np.ndarray) -> np.ndarray:
    """Robust z-scores based on MAD."""
    if values.size == 0:
        return values
    med = np.median(values)
    mad = np.median(np.abs(values - med))
    sigma = 1.4826 * mad
    if sigma < 1e-9:
        return np.zeros_like(values)
    return (values - med) / sigma


def trim_gateways_by_residual(
    selected: List[Reception],
    pool: List[Reception],
    gw_xy: Dict[str, Tuple[float, float]],
    assumed_n: float,
    z_thresh: float = 2.5,
    max_drop: int = 2,
    min_keep: int = 3,
) -> Tuple[List[Reception], int]:
    """
    Residual-based gateway trimming with a max-drop cap.

    This is a PRE-PROCESSING step that removes extreme outlier gateways (RSSI inconsistent with a
    provisional estimate) and returns a trimmed candidate pool (caller re-selects k gateways).

    Returns (pool_trimmed, n_dropped). If trimming cannot be applied safely, returns (pool, 0).
    """
    if max_drop <= 0 or len(pool) <= len(selected) or len(selected) < max(min_keep, 3):
        return pool, 0

    # Provisional location from WCL (no path-loss calibration required)
    x0, y0 = _wcl_xy_quick(selected, gw_xy)

    # Fit per-message A0 via median to avoid bias to any single gateway
    pts = []
    rssi = []
    for rx in selected:
        if rx.gid in gw_xy:
            gx, gy = gw_xy[rx.gid]
            d = max(1.0, math.hypot(gx - x0, gy - y0))
            pts.append(d)
            rssi.append(rx.rssi)
    if len(pts) < max(min_keep, 3):
        return pool, 0

    pts = np.asarray(pts, dtype=float)
    rssi = np.asarray(rssi, dtype=float)

    a0_hat = np.median(rssi + 10.0 * assumed_n * np.log10(pts))
    rssi_pred = a0_hat - 10.0 * assumed_n * np.log10(pts)
    resid = np.abs(rssi - rssi_pred)

    z = _robust_z_scores(resid)
    # Candidate outliers: z > threshold
    idxs = np.where(z > z_thresh)[0]
    if idxs.size == 0:
        return pool, 0

    # Drop worst offenders, capped
    worst = sorted(idxs.tolist(), key=lambda i: z[i], reverse=True)[: max_drop]
    drop_gids = {selected[i].gid for i in worst}

    # Ensure we keep at least min_keep
    if len(selected) - len(drop_gids) < min_keep:
        # reduce drop set to satisfy min_keep
        allowed = max(0, len(selected) - min_keep)
        if allowed <= 0:
            return pool, 0
        drop_gids = set(list(drop_gids)[:allowed])

    if not drop_gids:
        return pool, 0

    # Build trimmed pool and return it to caller (caller will re-select using its gw-select policy)
    pool_trimmed = [rx for rx in pool if rx.gid not in drop_gids]
    if len(pool_trimmed) < len(selected):
        # Can't refill fully; abort trimming
        return pool, 0
    return pool_trimmed, len(drop_gids)

def estimate_gateway_positions_centroid(
    train_messages: Sequence[Message],
    seed: int = 0,
    topk_per_gw: int = 25,
) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
    """
    Baseline estimator:
      - For each gateway, collect (rssi, tx_x, tx_y) from training messages.
      - Take top-K strongest by RSSI and compute weighted centroid with weights 10^(rssi/10).

    Returns:
      gw_xy: gid -> [x,y]
      gw_a0: gid -> NaN (not estimated)
    """
    by_gw: Dict[str, List[Tuple[float, float, float]]] = {}
    for m in train_messages:
        for rx in m.receptions:
            by_gw.setdefault(rx.gid, []).append((rx.rssi, m.x, m.y))

    gw_xy: Dict[str, np.ndarray] = {}
    gw_a0: Dict[str, float] = {}
    for gid, recs in by_gw.items():
        recs.sort(key=lambda t: t[0], reverse=True)
        recs = recs[: topk_per_gw]
        rssi = np.array([t[0] for t in recs], dtype=float)
        xs = np.array([t[1] for t in recs], dtype=float)
        ys = np.array([t[2] for t in recs], dtype=float)

        w = np.power(10.0, rssi / 10.0)
        if np.sum(w) <= 0:
            xy = np.array([float(np.mean(xs)), float(np.mean(ys))])
        else:
            xy = np.array([float(np.sum(w * xs) / np.sum(w)), float(np.sum(w * ys) / np.sum(w))])
        gw_xy[gid] = xy
        gw_a0[gid] = float("nan")
    return gw_xy, gw_a0


def estimate_gateway_a0_from_known_positions(
    train_messages: Sequence[Message],
    gw_xy: Dict[str, np.ndarray],
    assumed_n: float,
) -> Dict[str, float]:
    """Estimate per-gateway A0 given known gateway coordinates.

    Model: rssi = A0 - 10 n log10(d).  =>  A0 = rssi + 10 n log10(d).

    We use a robust median over links for each gateway.
    """

    gw_a0: Dict[str, List[float]] = {gid: [] for gid in gw_xy.keys()}
    for m in train_messages:
        for rx in m.receptions:
            if rx.gid not in gw_xy:
                continue
            gxy = gw_xy[rx.gid]
            d = float(np.hypot(m.x - gxy[0], m.y - gxy[1]))
            d = max(d, 1.0)  # avoid log10(0)
            a0 = float(rx.rssi + 10.0 * assumed_n * math.log10(d))
            if np.isfinite(a0):
                gw_a0[rx.gid].append(a0)

    out: Dict[str, float] = {}
    for gid, vals in gw_a0.items():
        if len(vals) >= 10:
            out[gid] = float(np.median(np.array(vals, dtype=float)))
    return out


def _robust_gateway_loss_and_a0(
    gx: float,
    gy: float,
    tx_xy: np.ndarray,   # shape (N,2)
    rssi: np.ndarray,    # shape (N,)
    n: float,
    eps_m: float = 1.0,
) -> Tuple[float, float]:
    """
    For a candidate gateway position (gx,gy), compute:
      A0_hat = median( rssi + 10*n*log10(d) )
      residuals = rssi - (A0_hat - 10*n*log10(d))
    Return (loss, A0_hat) where loss = median(|residuals|).
    """
    dx = tx_xy[:, 0] - gx
    dy = tx_xy[:, 1] - gy
    d = np.sqrt(dx * dx + dy * dy) + eps_m
    a0_hat = float(np.median(rssi + 10.0 * n * np.log10(d)))
    resid = rssi - (a0_hat - 10.0 * n * np.log10(d))
    loss = float(np.median(np.abs(resid)))
    return loss, a0_hat


def estimate_gateway_positions_rssfit(
    train_messages: Sequence[Message],
    assumed_n: float,
    max_points_per_gw: int = 2000,
    strong_quantile: float = 0.75,
    init_topk_centroid: int = 50,
    step_schedule_m: Sequence[float] = (2000, 1000, 500, 250, 125, 60),
    max_iter_per_step: int = 40,
    seed: int = 0,
) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
    """
    Recommended estimator:
      - For each gateway, gather many (tx_x,tx_y,rssi) from training messages.
      - Optionally keep only the top 'strong_quantile' RSSI (stronger receptions) to reduce NLOS.
      - Fit (gx,gy) using a derivative-free pattern search minimizing median absolute RSSI residual.
      - A0_hat is computed in closed-form (median) for each candidate position.

    Returns:
      gw_xy: gid -> [x,y]
      gw_a0: gid -> A0_hat (per-gateway intercept at reference distance 1m under assumed_n)
    """
    rng = random.Random(seed)

    by_gw: Dict[str, List[Tuple[float, float, float]]] = {}
    for m in train_messages:
        for rx in m.receptions:
            by_gw.setdefault(rx.gid, []).append((rx.rssi, m.x, m.y))

    gw_xy: Dict[str, np.ndarray] = {}
    gw_a0: Dict[str, float] = {}

    for gid, recs in by_gw.items():
        # subsample to keep runtime bounded
        if len(recs) > max_points_per_gw:
            recs = rng.sample(recs, k=max_points_per_gw)

        rssi = np.array([t[0] for t in recs], dtype=float)
        tx_xy = np.array([[t[1], t[2]] for t in recs], dtype=float)

        # keep only stronger receptions if asked
        if 0.0 < strong_quantile < 1.0:
            thr = float(np.quantile(rssi, strong_quantile))
            mask = rssi >= thr
            if np.sum(mask) >= 50:
                rssi = rssi[mask]
                tx_xy = tx_xy[mask]

        # init: weighted centroid over top-K strongest
        order = np.argsort(-rssi)
        k = min(init_topk_centroid, len(rssi))
        idx = order[:k]
        rssi_k = rssi[idx]
        tx_k = tx_xy[idx]
        w = np.power(10.0, rssi_k / 10.0)
        if float(np.sum(w)) <= 0:
            cur = np.array([float(np.mean(tx_k[:, 0])), float(np.mean(tx_k[:, 1]))], dtype=float)
        else:
            cur = np.array(
                [
                    float(np.sum(w * tx_k[:, 0]) / np.sum(w)),
                    float(np.sum(w * tx_k[:, 1]) / np.sum(w)),
                ],
                dtype=float,
            )

        # clamp box based on tx support (plus margin)
        min_xy = np.min(tx_xy, axis=0) - 2000.0
        max_xy = np.max(tx_xy, axis=0) + 2000.0

        def clamp(p: np.ndarray) -> np.ndarray:
            return np.array(
                [float(min(max(p[0], min_xy[0]), max_xy[0])), float(min(max(p[1], min_xy[1]), max_xy[1]))],
                dtype=float,
            )

        cur = clamp(cur)
        best_loss, best_a0 = _robust_gateway_loss_and_a0(cur[0], cur[1], tx_xy, rssi, assumed_n)

        # pattern search
        dirs = [(1,0), (-1,0), (0,1), (0,-1), (1,1), (1,-1), (-1,1), (-1,-1)]
        for step in step_schedule_m:
            improved = True
            it = 0
            while improved and it < max_iter_per_step:
                improved = False
                it += 1
                for dx, dy in dirs:
                    cand = clamp(cur + np.array([dx * step, dy * step], dtype=float))
                    loss, a0_hat = _robust_gateway_loss_and_a0(cand[0], cand[1], tx_xy, rssi, assumed_n)
                    if loss < best_loss:
                        best_loss = loss
                        best_a0 = a0_hat
                        cur = cand
                        improved = True

        gw_xy[gid] = cur.copy()
        gw_a0[gid] = float(best_a0)

    return gw_xy, gw_a0


def fit_global_n(
    train_messages: Sequence[Message],
    gw_xy: Dict[str, np.ndarray],
    n_grid: Sequence[float] = tuple(np.linspace(1.8, 4.0, 23)),
    max_pairs: int = 200_000,
    seed: int = 0,
) -> float:
    """
    Optional: coarse grid search for global path-loss exponent n that minimizes a robust absolute residual
    over training links, after optimizing out per-gateway A0 via median.

    This is not "the truth" — it's just an empirical n that best matches a log-distance model on this dataset
    given the provided gateway coordinates.
    """
    rng = random.Random(seed)

    # Build training link list: (gid, tx_x, tx_y, rssi)
    links: List[Tuple[str, float, float, float]] = []
    for m in train_messages:
        for rx in m.receptions:
            if rx.gid in gw_xy:
                links.append((rx.gid, m.x, m.y, rx.rssi))
    if not links:
        return 2.7

    if len(links) > max_pairs:
        links = rng.sample(links, k=max_pairs)

    # group by gateway
    by_gw: Dict[str, List[Tuple[float, float, float]]] = {}
    for gid, x, y, rssi in links:
        by_gw.setdefault(gid, []).append((x, y, rssi))

    best_n = None
    best_loss = float("inf")

    for n in n_grid:
        # estimate per-gateway A0 via median
        a0_map: Dict[str, float] = {}
        for gid, pts in by_gw.items():
            g = gw_xy[gid]
            xs = np.array([p[0] for p in pts], dtype=float)
            ys = np.array([p[1] for p in pts], dtype=float)
            r = np.array([p[2] for p in pts], dtype=float)
            d = np.sqrt((xs - g[0]) ** 2 + (ys - g[1]) ** 2) + 1.0
            a0_map[gid] = float(np.median(r + 10.0 * n * np.log10(d)))

        # compute residuals across all links
        resids: List[float] = []
        for gid, x, y, rssi in links:
            g = gw_xy[gid]
            d = math.hypot(x - g[0], y - g[1]) + 1.0
            pred = a0_map[gid] - 10.0 * n * math.log10(d)
            resids.append(rssi - pred)

        loss = float(np.median(np.abs(np.array(resids, dtype=float))))
        if loss < best_loss:
            best_loss = loss
            best_n = n

    return float(best_n if best_n is not None else 2.7)


# ----------------------------
# Baselines
# ----------------------------
def wcl_estimate(gw_xy: np.ndarray, rssi: np.ndarray) -> np.ndarray:
    """
    Weighted centroid with RSSI-based weights.
    """
    # shift to positive weights: w ~ 10^(rssi/10)
    w = np.power(10.0, rssi / 10.0)
    s = float(np.sum(w))
    if s <= 0:
        return np.mean(gw_xy, axis=0)
    return np.array([float(np.sum(w * gw_xy[:, 0]) / s), float(np.sum(w * gw_xy[:, 1]) / s)], dtype=float)


def trilateration_fixed_A0(gw_xy: np.ndarray, rssi: np.ndarray, n: float, A0: float) -> np.ndarray:
    """
    Convert RSSI to distance using fixed A0, then solve via least squares.
    """
    if least_squares is None:
        return wcl_estimate(gw_xy, rssi)

    # d = 10^((A0 - rssi)/(10n))
    d = np.power(10.0, (A0 - rssi) / (10.0 * n))

    def fun(p: np.ndarray) -> np.ndarray:
        return np.sqrt((gw_xy[:, 0] - p[0]) ** 2 + (gw_xy[:, 1] - p[1]) ** 2) - d

    x0 = wcl_estimate(gw_xy, rssi)
    res = least_squares(fun, x0=x0, method="lm")
    return res.x


def trilateration_joint_A0(gw_xy: np.ndarray, rssi: np.ndarray, n: float) -> np.ndarray:
    """
    Jointly estimate p and a common A0 for a single message.
    """
    if least_squares is None:
        return wcl_estimate(gw_xy, rssi)

    def fun(z: np.ndarray) -> np.ndarray:
        p = z[:2]
        A0 = z[2]
        d = np.sqrt((gw_xy[:, 0] - p[0]) ** 2 + (gw_xy[:, 1] - p[1]) ** 2) + 1.0
        pred_rssi = A0 - 10.0 * n * np.log10(d)
        return pred_rssi - rssi

    x0 = wcl_estimate(gw_xy, rssi)
    z0 = np.array([x0[0], x0[1], float(np.median(rssi) + 10.0 * n * math.log10(1000.0))], dtype=float)
    res = least_squares(fun, x0=z0, method="lm")
    return res.x[:2]


# ----------------------------
# DeltaMesh
# ----------------------------
def triangular_lattice_points(center: np.ndarray, span_m: float, spacing_m: float) -> np.ndarray:
    """
    Generate a triangular lattice in a square window of side span_m centered at 'center'.
    """
    # bounding box
    half = span_m / 2.0
    x_min = center[0] - half
    x_max = center[0] + half
    y_min = center[1] - half
    y_max = center[1] + half

    # triangular lattice basis:
    # points = i * (s,0) + j*(s/2, s*sqrt(3)/2)
    s = spacing_m
    dy = s * math.sqrt(3.0) / 2.0

    xs = []
    ys = []
    j = 0
    y = y_min
    while y <= y_max:
        # offset every other row
        offset = 0.0 if (j % 2 == 0) else s / 2.0
        x = x_min + offset
        while x <= x_max:
            xs.append(x)
            ys.append(y)
            x += s
        y += dy
        j += 1

    return np.column_stack([np.array(xs, dtype=float), np.array(ys, dtype=float)])


def deltamesh_pairwise_cost(
    p: np.ndarray,
    gw_xy: np.ndarray,
    rssi: np.ndarray,
    n: float,
    min_pair_delta_db: float = 2.0,
    eps_m: float = 1.0,
) -> float:
    """
    Robust cost on pairwise RSSI differences:
      Δ_obs(i,j) = rssi_i - rssi_j
      Δ_pred(i,j) = -10*n*log10(d_i/d_j)

    cost = median_{i<j, |Δ_obs|>=threshold} |Δ_obs - Δ_pred|
    """
    k = gw_xy.shape[0]
    if k < 3:
        return float("inf")

    dx = gw_xy[:, 0] - p[0]
    dy = gw_xy[:, 1] - p[1]
    d = np.sqrt(dx * dx + dy * dy) + eps_m

    resids = []
    for i in range(k):
        for j in range(i + 1, k):
            delta_obs = float(rssi[i] - rssi[j])
            if abs(delta_obs) < min_pair_delta_db:
                continue
            delta_pred = -10.0 * n * math.log10(float(d[i] / d[j]))
            resids.append(abs(delta_obs - delta_pred))

    if not resids:
        return float("inf")
    return float(np.median(np.array(resids, dtype=float)))


def deltamesh_localize(
    gw_xy: np.ndarray,
    rssi: np.ndarray,
    n: float,
    coarse_spacing_m: float = 600.0,
    fine_spacing_m: float = 150.0,
    coarse_span_m: float = 6000.0,
    fine_span_m: float = 1500.0,
    min_pair_delta_db: float = 2.0,
    topk_centroid: int = 25,
) -> np.ndarray:
    """
    Two-stage triangular lattice search:
      1) center on WCL(topK) and search coarse lattice over coarse_span
      2) refine around best coarse point on fine lattice over fine_span
    """
    k = gw_xy.shape[0]
    kk = min(topk_centroid, k)
    center = wcl_estimate(gw_xy[:kk], rssi[:kk])

    coarse_pts = triangular_lattice_points(center=center, span_m=coarse_span_m, spacing_m=coarse_spacing_m)
    costs = np.array(
        [deltamesh_pairwise_cost(p, gw_xy, rssi, n, min_pair_delta_db=min_pair_delta_db) for p in coarse_pts],
        dtype=float,
    )
    best_idx = int(np.argmin(costs))
    best = coarse_pts[best_idx]

    fine_pts = triangular_lattice_points(center=best, span_m=fine_span_m, spacing_m=fine_spacing_m)
    costs2 = np.array(
        [deltamesh_pairwise_cost(p, gw_xy, rssi, n, min_pair_delta_db=min_pair_delta_db) for p in fine_pts],
        dtype=float,
    )
    best2 = fine_pts[int(np.argmin(costs2))]
    return best2


def pso_refine(
    init: np.ndarray,
    gw_xy: np.ndarray,
    rssi: np.ndarray,
    n: float,
    box_m: float = 250.0,
    particles: int = 30,
    iters: int = 25,
    min_pair_delta_db: float = 2.0,
    seed: int = 0,
) -> np.ndarray:
    """
    Lightweight PSO in a local box around init, minimizing the DeltaMesh pairwise cost.
    """
    rng = np.random.default_rng(seed)
    # bounds
    lo = init - box_m
    hi = init + box_m

    # init swarm
    X = rng.uniform(lo, hi, size=(particles, 2))
    V = np.zeros_like(X)
    pbest = X.copy()
    pbest_cost = np.array([deltamesh_pairwise_cost(x, gw_xy, rssi, n, min_pair_delta_db=min_pair_delta_db) for x in X])
    gbest = pbest[int(np.argmin(pbest_cost))].copy()
    gbest_cost = float(np.min(pbest_cost))

    # PSO hyperparams
    w = 0.72
    c1 = 1.49
    c2 = 1.49

    for _ in range(iters):
        r1 = rng.random(size=(particles, 2))
        r2 = rng.random(size=(particles, 2))
        V = w * V + c1 * r1 * (pbest - X) + c2 * r2 * (gbest - X)
        X = X + V
        X = np.clip(X, lo, hi)

        costs = np.array([deltamesh_pairwise_cost(x, gw_xy, rssi, n, min_pair_delta_db=min_pair_delta_db) for x in X])
        improved = costs < pbest_cost
        pbest[improved] = X[improved]
        pbest_cost[improved] = costs[improved]
        idx = int(np.argmin(pbest_cost))
        if float(pbest_cost[idx]) < gbest_cost:
            gbest_cost = float(pbest_cost[idx])
            gbest = pbest[idx].copy()

    return gbest


# ----------------------------
# Robust NLLS (Huber-loss multilateration) — additional baseline for revision
# ----------------------------
def _halton_seq(n: int, base: int, offset: int = 0) -> List[float]:
    """1-D Halton sequence in [0,1] with given base, starting at index offset+1."""
    seq = []
    for i in range(offset, offset + n):
        f, r = 1.0, 0.0
        idx = i + 1
        while idx > 0:
            f /= base
            r += f * (idx % base)
            idx //= base
        seq.append(r)
    return seq


def robust_nlls_localize(
    gw_mat: np.ndarray,
    rssi_corrected: np.ndarray,
    n: float,
    wcl_init: np.ndarray,
    bbox: Tuple[float, float, float, float],
    huber_c: float = 1.345,
    n_starts: int = 5,
    max_iter: int = 200,
    grad_tol: float = 1e-6,
    halton_seed: int = 42,
    boundary_margin: float = 100.0,
) -> Tuple[np.ndarray, bool, int]:
    """
    Robust NLLS localization using Huber-loss on bias-corrected absolute RSSI.

    Identical gateway selection, calibration, and bias correction as DeltaMesh.
    Only the search procedure differs (continuous Huber regression vs discrete mesh).

    Parameters
    ----------
    gw_mat          : (k,2) array of selected gateway positions
    rssi_corrected  : (k,)  bias-corrected RSSI (same dm_rssi used by DeltaMesh)
    n               : path-loss exponent (same swept value)
    wcl_init        : (2,)  WCL initializer (matched to DeltaMesh's coarse init)
    bbox            : (xmin, xmax, ymin, ymax) search bounds in meters
    huber_c         : Huber loss threshold (standard 1.345)
    n_starts        : 1 WCL init + (n_starts-1) Halton restarts
    max_iter        : max L-BFGS-B iterations per start
    grad_tol        : gradient convergence tolerance
    halton_seed     : seed for reproducible Halton perturbations
    boundary_margin : margin (m) from bbox edge to flag as diverged

    Returns
    -------
    x_hat      : (2,) estimated position (clipped to bbox)
    converged  : True if not near bbox boundary
    n_diverged : number of starts that hit the boundary
    """
    from scipy.optimize import minimize as _minimize  # already imported via least_squares

    G = gw_mat.astype(float)
    R = rssi_corrected.astype(float)
    xmin, xmax, ymin, ymax = bbox

    def objective(x: np.ndarray) -> float:
        d = np.sqrt((G[:, 0] - x[0]) ** 2 + (G[:, 1] - x[1]) ** 2) + 1.0
        pred = -10.0 * n * np.log10(d)
        res = R - pred
        abs_r = np.abs(res)
        loss = np.where(abs_r <= huber_c,
                        0.5 * res ** 2,
                        huber_c * (abs_r - 0.5 * huber_c))
        return float(np.sum(loss))

    # Build starts: WCL + Halton quasi-random within bbox
    starts = [np.clip(wcl_init.copy(), [xmin, ymin], [xmax, ymax])]
    rng_off = (halton_seed * 97 + 13) % 1000  # reproducible offset
    hx = _halton_seq(n_starts - 1, base=2, offset=rng_off)
    hy = _halton_seq(n_starts - 1, base=3, offset=rng_off)
    for hxi, hyi in zip(hx, hy):
        starts.append(np.array([xmin + hxi * (xmax - xmin),
                                 ymin + hyi * (ymax - ymin)], dtype=float))

    bounds_lbfgs = [(xmin, xmax), (ymin, ymax)]
    best_x: np.ndarray = starts[0].copy()
    best_loss = float("inf")
    n_diverged = 0

    for x0 in starts:
        try:
            res = _minimize(
                objective, x0, method="L-BFGS-B",
                bounds=bounds_lbfgs,
                options={"maxiter": max_iter, "gtol": grad_tol, "ftol": 1e-15},
            )
            x_cand = np.asarray(res.x, dtype=float)
            loss_cand = float(res.fun)
        except Exception:
            n_diverged += 1
            continue

        # check boundary divergence
        near_bnd = (
            x_cand[0] < xmin + boundary_margin or x_cand[0] > xmax - boundary_margin or
            x_cand[1] < ymin + boundary_margin or x_cand[1] > ymax - boundary_margin
        )
        if near_bnd:
            n_diverged += 1

        if loss_cand < best_loss:
            best_loss = loss_cand
            best_x = x_cand

    # clip to bbox
    best_x = np.clip(best_x, [xmin, ymin], [xmax, ymax])
    converged = not (
        best_x[0] < xmin + boundary_margin or best_x[0] > xmax - boundary_margin or
        best_x[1] < ymin + boundary_margin or best_x[1] > ymax - boundary_margin
    )
    return best_x, converged, n_diverged


# ----------------------------
# Metrics
# ----------------------------
def bootstrap_ci(values: np.ndarray, stat_fn, n_boot: int = 500, alpha: float = 0.05, seed: int = 0) -> Tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"))
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        stats.append(float(stat_fn(values[idx])))
    stats = np.array(stats, dtype=float)
    lo = float(np.quantile(stats, alpha / 2))
    hi = float(np.quantile(stats, 1 - alpha / 2))
    return lo, hi


# ----------------------------
# Evaluation
# ----------------------------
def eval_on_messages(
    messages_eval: Sequence[Message],
    gw_xy: Dict[str, np.ndarray],
    gw_a0: Dict[str, float],
    assumed_n: float,
    min_gws: int,
    max_gws: int,
    gw_select: str = "rssi",
    hybrid_pool_factor: float = 2.0,
    trim_gws: bool = False,
    trim_z: float = 2.5,
    trim_max_drop: int = 2,
    trilat_mode: str = "joint",
    trilat_A0: float = -40.0,
    drift_db: float = 0.0,
    min_pair_delta_db: float = 0.0,
    use_pso: bool = False,
    pso_box_m: float = 300.0,
    pso_particles: int = 20,
    pso_iters: int = 60,
    bias_correct: bool = False,
    use_robust_nlls: bool = False,
    nlls_huber_c: float = 1.345,
    nlls_n_starts: int = 5,
    seed: int = 0,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    rng = random.Random(seed)

    # gateway-trimming diagnostics (only used when trim_gws=True)
    _trim_triggers = 0
    _trim_dropped_total = 0

    # Robust NLLS diagnostics
    _nlls_diverged_total = 0

    # Precompute bounding box for NLLS from all gateway coordinates
    if use_robust_nlls and gw_xy:
        _all_coords = np.array(list(gw_xy.values()), dtype=float)
        _nlls_bbox = (
            float(_all_coords[:, 0].min()) - 2000.0,
            float(_all_coords[:, 0].max()) + 2000.0,
            float(_all_coords[:, 1].min()) - 2000.0,
            float(_all_coords[:, 1].max()) + 2000.0,
        )
    else:
        _nlls_bbox = (0.0, 1.0, 0.0, 1.0)

    rows = []
    t_wcl = []
    t_trilat = []
    t_dm = []
    t_pso = []
    t_nlls = []

    for m in messages_eval:
        # gateway subset selection (method-agnostic pre-processing)
        cand = [rx for rx in m.receptions if rx.gid in gw_xy]
        if len(cand) < max(min_gws, 3):
            continue

        pool_k = max_gws
        if trim_gws or (gw_select or "rssi").lower() != "rssi":
            pool_k = max(max_gws, int(math.ceil(hybrid_pool_factor * max_gws)))
        pool = cand[:pool_k]
        if len(pool) < max(min_gws, 3):
            continue

        used = select_gateways_subset(
            receptions_sorted_by_rssi=pool,
            gw_xy=gw_xy,
            k=max_gws,
            mode=gw_select,
            hybrid_pool_factor=hybrid_pool_factor,
            seed=seed,
        )
        if len(used) < max(min_gws, 3):
            continue

        # Optional: residual-based trimming with capped removal (drops extreme outliers, refills from pool)
        if trim_gws:
            trimmed_pool, n_dropped = trim_gateways_by_residual(
                selected=used,
                pool=pool,
                gw_xy=gw_xy,
                assumed_n=assumed_n,
                z_thresh=trim_z,
                max_drop=trim_max_drop,
                min_keep=max(min_gws, 3),
            )
            if n_dropped > 0:
                _trim_triggers += 1
                _trim_dropped_total += n_dropped
                used2 = select_gateways_subset(
                    receptions_sorted_by_rssi=trimmed_pool,
                    gw_xy=gw_xy,
                    k=max_gws,
                    mode=gw_select,
                    hybrid_pool_factor=hybrid_pool_factor,
                    seed=seed,
                )
                if len(used2) >= max(min_gws, 3):
                    used = used2

        # materialize arrays for estimators
        coords = []
        rssi = []
        a0s = []
        for rx in used:
            coords.append(gw_xy[rx.gid])
            rssi.append(float(rx.rssi))
            a0s.append(float(gw_a0.get(rx.gid, float("nan"))))


        gw_mat = np.vstack(coords)
        rssi_vec = np.array(rssi, dtype=float)
        a0_vec = np.array(a0s, dtype=float)

        # apply per-message drift (same drift for all gateways of that message)
        if drift_db != 0.0:
            rssi_vec = rssi_vec + rng.gauss(0.0, drift_db)

        # WCL baseline
        t0 = time.perf_counter()
        wcl_xy = wcl_estimate(gw_mat, rssi_vec)
        t_wcl.append((time.perf_counter() - t0) * 1000.0)

        # Trilateration baseline
        t0 = time.perf_counter()
        if trilat_mode == "joint":
            tril_xy = trilateration_joint_A0(gw_mat, rssi_vec, assumed_n)
        else:
            tril_xy = trilateration_fixed_A0(gw_mat, rssi_vec, assumed_n, trilat_A0)
        t_trilat.append((time.perf_counter() - t0) * 1000.0)

        # DeltaMesh RSSI vector: optionally bias-correct if we have per-gateway A0 estimates
        dm_rssi = rssi_vec.copy()
        if bias_correct and np.all(np.isfinite(a0_vec)):
            dm_rssi = dm_rssi - a0_vec

        # DeltaMesh
        t0 = time.perf_counter()
        dm_xy = deltamesh_localize(
            gw_mat,
            dm_rssi,
            assumed_n,
            min_pair_delta_db=min_pair_delta_db,
        )
        t_dm.append((time.perf_counter() - t0) * 1000.0)

        # Optional PSO
        dm_pso_xy = None
        if use_pso:
            t0 = time.perf_counter()
            dm_pso_xy = pso_refine(
                dm_xy,
                gw_mat,
                dm_rssi,
                assumed_n,
                box_m=pso_box_m,
                particles=pso_particles,
                iters=pso_iters,
                min_pair_delta_db=min_pair_delta_db,
                seed=seed,
            )
            t_pso.append((time.perf_counter() - t0) * 1000.0)

        # Robust NLLS baseline (optional, enabled by --use-robust-nlls)
        nlls_xy = None
        nlls_converged = False
        nlls_n_div = 0
        if use_robust_nlls:
            t0 = time.perf_counter()
            nlls_xy, nlls_converged, nlls_n_div = robust_nlls_localize(
                gw_mat=gw_mat,
                rssi_corrected=dm_rssi,  # same bias-corrected RSSI as DeltaMesh
                n=assumed_n,
                wcl_init=wcl_xy,         # WCL initializer matched to DeltaMesh
                bbox=_nlls_bbox,
                huber_c=nlls_huber_c,
                n_starts=nlls_n_starts,
                max_iter=200,
                grad_tol=1e-6,
                halton_seed=seed,
            )
            t_nlls.append((time.perf_counter() - t0) * 1000.0)
            _nlls_diverged_total += nlls_n_div

        # Errors
        true_xy = np.array([m.x, m.y], dtype=float)
        err_wcl = float(np.linalg.norm(wcl_xy - true_xy))
        err_tril = float(np.linalg.norm(tril_xy - true_xy))
        err_dm = float(np.linalg.norm(dm_xy - true_xy))
        err_dm_pso = float(np.linalg.norm(dm_pso_xy - true_xy)) if dm_pso_xy is not None else float("nan")
        err_nlls = float(np.linalg.norm(nlls_xy - true_xy)) if nlls_xy is not None else float("nan")

        rows.append(
            {
                "err_wcl": err_wcl,
                "err_trilat": err_tril,
                "err_deltamesh": err_dm,
                "err_deltamesh_pso": err_dm_pso,
                "err_nlls": err_nlls,
                "nlls_converged": int(nlls_converged) if nlls_xy is not None else -1,
                "nlls_n_diverged_starts": nlls_n_div if nlls_xy is not None else -1,
                "k_gws": int(len(gw_mat)),
            }
        )

    df = pd.DataFrame(rows)

    summary: Dict[str, Dict[str, float]] = {}
    for key in ["err_wcl", "err_trilat", "err_deltamesh", "err_deltamesh_pso", "err_nlls"]:
        vals = df[key].dropna().to_numpy(dtype=float)
        if len(vals) == 0:
            summary[key] = {"median": float("nan"), "p90": float("nan")}
            continue
        # For NLLS, filter out -1 sentinels (method not run)
        vals = vals[vals >= 0]
        if len(vals) == 0:
            summary[key] = {"median": float("nan"), "p90": float("nan")}
            continue
        med = float(np.median(vals))
        p90 = float(np.quantile(vals, 0.9))
        med_ci = bootstrap_ci(vals, np.median, seed=seed)
        p90_ci = bootstrap_ci(vals, lambda v: np.quantile(v, 0.9), seed=seed + 1)
        summary[key] = {
            "median": med,
            "median_ci_lo": med_ci[0],
            "median_ci_hi": med_ci[1],
            "p90": p90,
            "p90_ci_lo": p90_ci[0],
            "p90_ci_hi": p90_ci[1],
        }

    # NLLS-specific diagnostics
    nlls_diag: Dict[str, float] = {}
    if use_robust_nlls and "err_nlls" in df.columns:
        valid = df["nlls_converged"].to_numpy()
        valid_mask = valid >= 0
        if valid_mask.sum() > 0:
            n_converged = int((valid[valid_mask] == 1).sum())
            n_total = int(valid_mask.sum())
            nlls_diag["convergence_rate_pct"] = 100.0 * n_converged / n_total
            nlls_diag["divergence_rate_pct"] = 100.0 * (1 - n_converged / n_total)
            total_starts = n_total * nlls_n_starts
            nlls_diag["start_divergence_rate_pct"] = (
                100.0 * _nlls_diverged_total / total_starts if total_starts > 0 else float("nan")
            )

    runtime = {
        "wcl_ms_median": float(np.median(np.array(t_wcl))) if t_wcl else float("nan"),
        "trilat_ms_median": float(np.median(np.array(t_trilat))) if t_trilat else float("nan"),
        "deltamesh_ms_median": float(np.median(np.array(t_dm))) if t_dm else float("nan"),
        "pso_ms_median": float(np.median(np.array(t_pso))) if t_pso else float("nan"),
        "nlls_ms_median": float(np.median(np.array(t_nlls))) if t_nlls else float("nan"),
    }
    return df, {"metrics": summary, "runtime": runtime,
                "meta": {"trim_triggers": int(_trim_triggers),
                         "trim_dropped_total": int(_trim_dropped_total),
                         "nlls_diagnostics": nlls_diag}}


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Path to Antwerp CSV")
    ap.add_argument("--samples", type=int, default=5000, help="Number of eval messages to sample")
    ap.add_argument("--train-frac", type=float, default=0.2, help="Fraction of messages used to estimate gateway params")
    ap.add_argument(
    "--fixed-eval-pool",
    action="store_true",
    help="Fix the evaluation pool at 70% of messages and draw nested calibration subsets only from the first 30%.",
)
    ap.add_argument("--min-gws", type=int, default=3)
    ap.add_argument("--max-gws", type=int, default=10)
    ap.add_argument(
        "--gw-select",
        type=str,
        default="rssi",
        choices=["rssi", "geometry", "hybrid"],
        help="Per-message gateway subset selection: rssi=strongest, geometry=hull-spread, hybrid=geometry on strong pool",
    )
    ap.add_argument(
        "--hybrid-pool-factor",
        type=float,
        default=2.0,
        help="For geometry/hybrid, candidate pool size = ceil(factor * max_gws) taken by RSSI rank",
    )
    ap.add_argument(
        "--trim-gws",
        action="store_true",
        help="Optional residual-based trimming of extreme outlier gateways (capped) before running all estimators",
    )
    ap.add_argument("--trim-z", type=float, default=2.5, help="Robust z-score threshold for gateway trimming")
    ap.add_argument("--trim-max-drop", type=int, default=2, help="Max gateways dropped per message when trimming is enabled")

    # Many LoRaWAN CSV exports encode "no reception" as a sentinel numeric
    # value (e.g., -200, 0, 255) instead of NaN. We treat values outside this
    # plausible RSSI window as missing.
    ap.add_argument("--rssi-floor", type=float, default=-150.0, help="Drop RSSI < floor as missing")
    ap.add_argument("--rssi-ceil", type=float, default=-20.0, help="Drop RSSI > ceil as missing")
    ap.add_argument(
        "--gateway-locs",
        "--gateway_locs",
        dest="gateway_locs",
        type=str,
        default="",
        help=(
            "Optional JSON file with known gateway coordinates (e.g., Zenodo 'lorawan_antwerp_gateway_locations.json.txt'). "
            "If provided, the evaluator will attempt to use these coordinates. "
            "Note: if your RSSI table uses BS1..BSK columns (not hex gateway IDs), you must also pass --auto-map-bs "
            "to align BS labels to known gateways."
        ),
    )
    ap.add_argument(
        "--auto-map-bs",
        action="store_true",
        help=(
            "If the dataset uses BS1..BSK gateway labels but --gateway-locs provides hex gateway IDs, attempt to align "
            "BS labels to the nearest known gateways using the train split (snap estimated BS positions to known ones). "
            "This is a dataset-alignment step, not part of the localization method."
        ),
    )
    ap.add_argument(
        "--auto-map-max-dist",
        type=float,
        default=5000.0,
        help="Maximum snapping distance in meters when auto-mapping BS labels to known gateway locations (default: 5000).",
    )
    ap.add_argument(
        "--auto-map-margin-km",
        type=float,
        default=30.0,
        help="Margin (km) added to the train transmitter bounding box when filtering candidate gateways for auto-mapping (default: 30).",
    )
    ap.add_argument(
        "--max-hdop",
        type=float,
        default=None,
        help="Optional GPS-quality filter: drop rows with HDOP > this value (requires an HDOP column)",
    )

    ap.add_argument("--assumed-n", type=float, default=2.7, help="Assumed path-loss exponent for geometry-based methods")

    ap.add_argument("--gw-estimator", choices=["centroid", "rssfit"], default="rssfit")
    ap.add_argument("--fit-n", action="store_true", help="Fit a global n on training data (coarse grid)")

    ap.add_argument("--bias-correct", action="store_true", help="Subtract per-gateway A0_hat before DeltaMesh scoring (rssfit only)")

    ap.add_argument("--trilat-mode", choices=["fixed", "joint"], default="fixed")
    ap.add_argument("--trilat-A0", type=float, default=-40.0)

    ap.add_argument("--drift-db", type=float, default=0.0, help="Per-message common RSSI drift sigma (dB)")

    ap.add_argument("--min-pair-delta-db", type=float, default=2.0)

    ap.add_argument("--use-pso", action="store_true")
    ap.add_argument("--pso-box-m", type=float, default=250.0)
    ap.add_argument("--pso-particles", type=int, default=30)
    ap.add_argument("--pso-iters", type=int, default=25)

    ap.add_argument("--use-robust-nlls", action="store_true",
                    help="Enable Robust NLLS (Huber-loss multilateration) as an additional baseline.")
    ap.add_argument("--nlls-huber-c", type=float, default=1.345,
                    help="Huber loss threshold for Robust NLLS (default: 1.345, standard value).")
    ap.add_argument("--nlls-n-starts", type=int, default=5,
                    help="Number of optimizer restarts for Robust NLLS (1 WCL + n-1 Halton, default: 5).")

    ap.add_argument("--out-csv", type=str, default="", help="Write per-message errors CSV")

    ap.add_argument(
    "--save-resolved-gw-locs",
    type=str,
    default="",
    help="Optional JSON path to save the final resolved gateway coordinates keyed by dataset labels (e.g., BS1, BS2).",
    )
    ap.add_argument("--seed", type=int, default=0)

    ap.add_argument("--snap-method", default="hungarian", choices=["hungarian", "greedy"],
                    help="When --auto-map-bs is set, how to snap estimated BS positions to known gateways: global Hungarian assignment or greedy nearest-neighbour.")
    args = ap.parse_args()

    print(f"Loading dataset: {args.data} ...")
    t0 = time.perf_counter()
    messages = load_antwerp_csv(
        args.data,
        min_gws=args.min_gws,
        rssi_floor=args.rssi_floor,
        rssi_ceil=args.rssi_ceil,
        max_hdop=args.max_hdop,
    )
    print(f"Loaded {len(messages)} messages with >= {args.min_gws} receptions in {time.perf_counter()-t0:.2f}s")

    if not messages:
        raise SystemExit("No messages loaded — check format/min-gws/columns.")

    # rng = random.Random(args.seed)
    # rng.shuffle(messages)
    # n_train = int(len(messages) * args.train_frac)
    # train = messages[:n_train]
    # eval_pool = messages[n_train:]
    # print(f"Gateway estimation split: train={len(train)} eval={len(eval_pool)}")

    #New Block Patch 3B
    rng = random.Random(args.seed)
    rng.shuffle(messages)

    if args.fixed_eval_pool:
        calib_reservoir_frac = 0.30
        n_calib_res = int(len(messages) * calib_reservoir_frac)
        calib_reservoir = messages[:n_calib_res]
        eval_pool = messages[n_calib_res:]

        effective_train_frac = min(float(args.train_frac), calib_reservoir_frac)
        n_train = int(len(messages) * effective_train_frac)
        n_train = min(n_train, n_calib_res)
        train = calib_reservoir[:n_train]

        print(
            f"Gateway estimation split: calib_reservoir={len(calib_reservoir)} "
            f"train={len(train)} eval={len(eval_pool)} "
            f"(requested_train_frac={args.train_frac:.2f}, effective_train_frac={effective_train_frac:.2f})"
        )
    else:
        n_train = int(len(messages) * args.train_frac)
        train = messages[:n_train]
        eval_pool = messages[n_train:]
        print(f"Gateway estimation split: train={len(train)} eval={len(eval_pool)}")

    # Gateway estimation
    assumed_n = float(args.assumed_n)

    # ------------------------------------------------------------------
        # Gateway coordinates
    gw_xy: Dict[str, Tuple[float, float]] = {}
    gw_a0: Dict[str, float] = {}

    used = sorted({rx.gid for m in messages for rx in m.receptions})

    gw_xy_all: Dict[str, Tuple[float, float]] = {}
    if args.gateway_locs:
        try:
            gw_xy_all = load_gateway_locations(args.gateway_locs)
            matched = [gid for gid in used if gid in gw_xy_all]
            gw_xy = {gid: gw_xy_all[gid] for gid in matched}
            print(f"Loaded {len(gw_xy_all)} gateway locs; matched {len(gw_xy)}/{len(used)} gateway labels in data.")
        except Exception as e:
            print(f"Warning: failed to load gateway locations from {args.gateway_locs} ({e}). Falling back to estimation.")
            gw_xy_all = {}

    # If we got 0 direct matches but we do have gateway locations, the data likely uses BS1..BSK labels.
    # With --auto-map-bs enabled, estimate BS positions from the train split and snap them to the nearest known gateways.
    est_xy_cache: Dict[str, Tuple[float, float]] = {}
    if args.gateway_locs and gw_xy_all and len(gw_xy) == 0 and args.auto_map_bs:
        if all(re.match(r"^(BS)?\d+$", gid) for gid in used):
            if args.gw_estimator == "rssfit":
                est_xy_cache, _ = estimate_gateway_positions_rssfit(train, assumed_n=args.assumed_n, seed=args.seed)
            else:
                est_xy_cache, _ = estimate_gateway_positions_centroid(train, seed=args.seed)

            bbox = compute_xy_bbox(train)
            cand = filter_gw_xy_by_bbox(
                gw_xy_all, bbox=bbox, margin_m=float(args.auto_map_margin_km) * 1000.0
            )
            mapping, snapped_xy = greedy_snap_estimated_to_known(
                est_xy_cache, cand, method=args.snap_method, max_dist_m=float(args.auto_map_max_dist)
            )

            if mapping:
                gw_xy = dict(est_xy_cache)
                gw_xy.update(snapped_xy)
                print(
                    f"Auto-mapped {len(mapping)}/{len(est_xy_cache)} BS labels to known gateways "
                    f"(candidates={len(cand)}, max_dist={args.auto_map_max_dist:.0f} m)."
                )
            else:
                print(
                    "Warning: --auto-map-bs enabled but no BS labels could be snapped to known gateway locations; "
                    "falling back to pure estimation."
                )

    # If we still don't have any gateway coordinates, estimate them from the train split.
    if len(gw_xy) == 0:
        if args.gw_estimator == "centroid":
            gw_xy, gw_a0 = estimate_gateway_positions_centroid(train, seed=args.seed)
        else:
            gw_xy, gw_a0 = estimate_gateway_positions_rssfit(train, assumed_n=args.assumed_n, seed=args.seed)

    # If we have only partial gateway coordinates (e.g., some matched + some missing), fill missing ones by estimation.
    if len(gw_xy) > 0 and len(gw_xy) < len(used):
        if not est_xy_cache:
            if args.gw_estimator == "rssfit":
                est_xy_cache, _ = estimate_gateway_positions_rssfit(train, assumed_n=args.assumed_n, seed=args.seed)
            else:
                est_xy_cache, _ = estimate_gateway_positions_centroid(train, seed=args.seed)
        for gid in used:
            if gid not in gw_xy and gid in est_xy_cache:
                gw_xy[gid] = est_xy_cache[gid]
        if len(gw_xy) < len(used):
            print(f"Note: gateway coords available for {len(gw_xy)}/{len(used)} labels after fill; others will be ignored.")

    if args.save_resolved_gw_locs:
        out = {gid: {"x": float(x), "y": float(y)} for gid, (x, y) in sorted(gw_xy.items())}
        with open(args.save_resolved_gw_locs, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"Saved resolved gateway coordinates for {len(out)} labels to {args.save_resolved_gw_locs}")
        
    # If bias correction enabled, estimate per-gateway A0_hat using the final gw_xy (even if gw positions were snapped).
    if args.bias_correct:
        gw_a0 = estimate_gateway_a0_from_known_positions(train, gw_xy, assumed_n=args.assumed_n)

    # Optional: fit a single global n (useful with either known or estimated gateways)
    if args.fit_n:
        print("Fitting global n (coarse grid) ...")
        assumed_n = fit_global_n(train, gw_xy, seed=args.seed)
        print(f"Fitted n = {assumed_n:.3f}")

    # sample eval messages
    if len(eval_pool) > args.samples:
        eval_msgs = rng.sample(eval_pool, k=args.samples)
    else:
        eval_msgs = eval_pool

    df, summary = eval_on_messages(
        eval_msgs,
        gw_xy,
        gw_a0,
        assumed_n=assumed_n,
        min_gws=args.min_gws,
        gw_select=args.gw_select,
        hybrid_pool_factor=args.hybrid_pool_factor,
        trim_gws=args.trim_gws,
        trim_z=args.trim_z,
        trim_max_drop=args.trim_max_drop,
        max_gws=args.max_gws,
        trilat_mode=args.trilat_mode,
        trilat_A0=args.trilat_A0,
        drift_db=args.drift_db,
        min_pair_delta_db=args.min_pair_delta_db,
        use_pso=args.use_pso,
        pso_box_m=args.pso_box_m,
        pso_particles=args.pso_particles,
        pso_iters=args.pso_iters,
        bias_correct=(args.bias_correct and len(gw_a0) > 0),
        use_robust_nlls=args.use_robust_nlls,
        nlls_huber_c=args.nlls_huber_c,
        nlls_n_starts=args.nlls_n_starts,
        seed=args.seed,
    )

    n_used = len(df)
    print("\n" + "=" * 70)
    print(f"RESULT SUMMARY (N={n_used})")
    print("=" * 70)

    def fmt_metric(name: str, key: str) -> str:
        m = summary["metrics"][key]
        return (
            f"{name:>12}: median= {m['median']:.1f} m (CI {m['median_ci_lo']:.1f}–{m['median_ci_hi']:.1f})"
            f" | P90= {m['p90']:.1f} m (CI {m['p90_ci_lo']:.1f}–{m['p90_ci_hi']:.1f})"
        )

    print(fmt_metric("WCL", "err_wcl"))
    print(fmt_metric("Trilat", "err_trilat"))
    print(fmt_metric("DeltaMesh", "err_deltamesh"))
    if args.use_pso:
        print(fmt_metric("Delta+PSO", "err_deltamesh_pso"))
    else:
        print(f"{'Delta+PSO':>12}: n/a")
    if args.use_robust_nlls:
        print(fmt_metric("RobustNLLS", "err_nlls"))
        nlls_diag = summary.get("meta", {}).get("nlls_diagnostics", {})
        if nlls_diag:
            conv_rate = nlls_diag.get("convergence_rate_pct", float("nan"))
            div_rate = nlls_diag.get("divergence_rate_pct", float("nan"))
            print(f"{'RobustNLLS':>12}: convergence_rate={conv_rate:.1f}% divergence_rate={div_rate:.1f}%")
    else:
        print(f"{'RobustNLLS':>12}: n/a (use --use-robust-nlls to enable)")

    rt = summary["runtime"]
    print("\n" + "-" * 70)
    print(
        f"WCL runtime:      median= {rt['wcl_ms_median']:.3f} ms\n"
        f"Trilat runtime:   median= {rt['trilat_ms_median']:.3f} ms\n"
        f"DeltaMesh runtime:median= {rt['deltamesh_ms_median']:.3f} ms\n"
        f"PSO runtime:      median= {rt['pso_ms_median']:.3f} ms\n"
        f"RobustNLLS runtime:median= {rt['nlls_ms_median']:.3f} ms"
    )

    if args.out_csv:
        df.to_csv(args.out_csv, index=False)
        print(f"\nWrote per-message results to: {args.out_csv}")

    print("\nNotes:")
    if args.gw_estimator == "centroid":
        print(" - You used centroid gateway estimation. This can create 'coverage-centroid' anchors that are not physically consistent.")
    else:
        print(" - You used rssfit gateway estimation (more physically consistent under the assumed log-distance model).")
    if args.bias_correct:
        print(" - Bias correction enabled: per-gateway A0_hat subtracted before DeltaMesh scoring.")
    if args.max_gws > 6:
        print(" - max-gws > 6 can hurt difference-based methods on real data due to noisy far anchors; consider trying --max-gws 5 or 6.")
    print("=" * 70)


if __name__ == "__main__":
    main()