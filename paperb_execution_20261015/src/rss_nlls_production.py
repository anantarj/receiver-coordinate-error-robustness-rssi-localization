"""Fixed finite multistart calibrated RSS least squares for Paper B.

The production estimate is the lowest finite objective among every prescribed
local-search start and its finite endpoint. It is not labelled a global optimum.
No query reference position, WCL output, wall-clock budget, or outcome-dependent
search escalation enters this interface. `audit` is a separate calculation and
never changes the primary result. Coordinates must be supplied in metres.
"""
from __future__ import annotations

import heapq
import time
import numpy as np
from scipy.optimize import least_squares

ALGORITHM_ID = "RSS_NLLS_FIXED_3X3_PLUS_ANCHORS_200_V1"
LOCAL_MAX_NFEV = 200
LOCAL_TOLERANCE = 1e-11
COMPETITIVE_TOLERANCE_DB2 = 0.01
POSITION_CLUSTER_TOLERANCE_M = 0.001
AUDIT_MAX_NFEV = 1000


def _validate(anchors, rss, intercepts, n, d0):
    anchors, rss, intercepts = (np.asarray(a, dtype=np.float64)
                                for a in (anchors, rss, intercepts))
    if anchors.ndim != 2 or anchors.shape[1] != 2 or len(anchors) == 0:
        raise ValueError("anchors must have nonempty shape (receivers, 2)")
    if rss.shape != (len(anchors),) or intercepts.shape != rss.shape:
        raise ValueError("rss and intercepts must each have one value per receiver")
    if not all(np.isfinite(v).all() for v in (anchors, rss, intercepts)):
        raise ValueError("receiver coordinates, RSS and intercepts must be finite")
    if not np.isfinite(n) or not np.isfinite(d0) or n <= 0 or d0 <= 0:
        raise ValueError("n and d0 must be finite and positive")
    return anchors, rss, intercepts


def residual(x, anchors, rss, intercepts, n=4.7, d0=1.0):
    d = np.linalg.norm(np.asarray(x) - anchors, axis=1)
    return rss - intercepts + 10.0 * n * np.log10((d + d0) / d0)


def objective(x, anchors, rss, intercepts, n=4.7, d0=1.0):
    r = residual(x, anchors, rss, intercepts, n, d0)
    return float(r @ r)


def _jacobian(x, anchors, rss, intercepts, n, d0):
    delta = x - anchors
    d = np.linalg.norm(delta, axis=1)
    # The Euclidean norm is not differentiable at an exact receiver. Zero there
    # is a specified local-search convention, not a differentiability assertion.
    direction = np.divide(delta, d[:, None], out=np.zeros_like(delta),
                          where=d[:, None] > 0)
    return (10.0 * n / np.log(10.0)) * direction / (d + d0)[:, None]


def _geometry(anchors, grid_side):
    origin = anchors.mean(axis=0)  # Equal-weight centering; no RSS dependence.
    local_anchors = anchors - origin
    spans = np.ptp(local_anchors, axis=0)
    scale = max(float(np.max(spans)), 1.0)
    # Both dimensions use half the largest span, including collinear geometries.
    half_span = np.maximum(spans / 2.0, scale / 2.0)
    fractions = np.linspace(-1.0, 1.0, grid_side)
    starts = [np.array([sx, sy]) * half_span
              for sx in fractions for sy in fractions]
    starts.extend(a.copy() for a in local_anchors)
    return origin, local_anchors, scale, np.asarray(starts)


def _local_search(starts, scale, args, max_nfev):
    records = []
    best, upper, best_index, best_source = None, float("inf"), -1, "none"
    for index, x0 in enumerate(starts):
        initial_value = objective(x0, *args)
        # Strict objective ordering; exact ties retain the earliest candidate.
        # Within each start the initial point precedes its endpoint.
        if np.isfinite(initial_value) and initial_value < upper:
            best, upper, best_index, best_source = x0.copy(), initial_value, index, "start"
        point, value, success, status, nfev = x0.copy(), initial_value, False, -99, 0
        exception_type = ""
        try:
            fit = least_squares(residual, x0, jac=_jacobian, args=args,
                                method="trf", loss="linear", x_scale=scale,
                                ftol=LOCAL_TOLERANCE, xtol=LOCAL_TOLERANCE,
                                gtol=LOCAL_TOLERANCE, max_nfev=max_nfev)
            nfev, status = int(fit.nfev), int(fit.status)
            fit_value = objective(fit.x, *args)
            if np.isfinite(fit.x).all() and np.isfinite(fit_value):
                point, value = fit.x.copy(), fit_value
                success = bool(fit.success)
                if value < upper:
                    best, upper, best_index, best_source = point.copy(), value, index, "endpoint"
            else:
                status, exception_type = -98, "nonfinite_endpoint"
        except (ArithmeticError, ValueError, RuntimeError) as exc:
            exception_type = type(exc).__name__
        records.append({"point": point, "objective": value, "success": success,
                        "status": status, "nfev": nfev, "exception": exception_type})
    return best, upper, best_index, best_source, records


def _competitive(records, upper, origin):
    points = [r["point"] for r in records
              if np.isfinite(r["objective"]) and
              r["objective"] <= upper + COMPETITIVE_TOLERANCE_DB2]
    unique = []
    for point in points:
        if all(np.linalg.norm(point - p) > POSITION_CLUSTER_TOLERANCE_M for p in unique):
            unique.append(point)
    if len(points) > 1:
        a = np.asarray(points)
        diameter = float(np.max(np.linalg.norm(a[:, None] - a[None, :], axis=2)))
    else:
        diameter = 0.0
    return [(p + origin).tolist() for p in unique], diameter


def solve(anchors, rss, intercepts, n=4.7, d0=1.0):
    """Run all fixed starts. Invalid inputs raise ValueError before optimization.

    Finite initial points survive failed local runs. `finite_output` and local
    convergence diagnostics must be retained separately by scientific callers.
    """
    clock = time.monotonic()
    anchors, rss, intercepts = _validate(anchors, rss, intercepts, n, d0)
    origin, a, scale, starts = _geometry(anchors, 3)
    best, upper, best_index, best_source, records = _local_search(
        starts, scale, (a, rss, intercepts, n, d0), LOCAL_MAX_NFEV)
    finite = best is not None and np.isfinite(upper)
    converged = sum(r["success"] for r in records)
    failed = sum(bool(r["exception"]) for r in records)
    points, diameter = _competitive(records, upper, origin) if finite else ([], float("nan"))
    if not finite:
        status = "no_finite_output"
    elif converged == len(records):
        status = "finite_all_local_runs_converged"
    elif converged:
        status = "finite_some_local_runs_unconverged"
    else:
        status = "finite_no_local_run_converged"
    return {
        "algorithm_id": ALGORITHM_ID,
        "position_m": (best + origin).tolist() if finite else [float("nan"), float("nan")],
        "objective_db2": upper,
        "status": status,
        "finite_output": bool(finite),
        "local_runs": len(records),
        "local_runs_converged": converged,
        "local_runs_failed": failed,
        "local_runs_budget_exhausted": sum(r["status"] == 0 for r in records),
        "best_start_index": best_index,
        "best_candidate_source": best_source,
        "nfev_total": sum(r["nfev"] for r in records),
        "competitive_local_solution_count": len(points),
        "competitive_local_positions_m": points,
        "competitive_diameter_m": diameter,
        "competitive_tolerance_db2": COMPETITIVE_TOLERANCE_DB2,
        "position_cluster_tolerance_m": POSITION_CLUSTER_TOLERANCE_M,
        "local_position_m": [(r["point"] + origin).tolist() for r in records],
        "local_objective_db2": [r["objective"] for r in records],
        "local_converged": [r["success"] for r in records],
        "local_status": [r["status"] for r in records],
        "local_nfev": [r["nfev"] for r in records],
        "local_exception": [r["exception"] for r in records],
        "search_origin_m": origin.tolist(),
        "search_scale_m": scale,
        "exact_global_optimum_claimed": False,
        "position_uniqueness_certified": False,
        "elapsed_seconds": time.monotonic() - clock,
    }


def _down(value):
    # Conservative numerical guard, not a directed-rounding interval guarantee.
    return max(0.0, float(value) - 1e-11 * (1.0 + abs(float(value))))


def rectangle_lower_bound(lo, hi, anchors, rss, intercepts, n=4.7, d0=1.0):
    """Sum receiver-wise minimum squared residuals over distance intervals."""
    nearest = np.maximum(np.maximum(lo - anchors, anchors - hi), 0.0)
    farthest = np.maximum(np.abs(lo - anchors), np.abs(hi - anchors))
    dmin = np.maximum(0.0, np.nextafter(np.linalg.norm(nearest, axis=1), -np.inf))
    dmax = np.nextafter(np.linalg.norm(farthest, axis=1), np.inf)
    rlo = rss - intercepts + 10.0 * n * np.log10((dmin + d0) / d0)
    rhi = rss - intercepts + 10.0 * n * np.log10((dmax + d0) / d0)
    guard = 1e-12 * (1.0 + np.maximum(np.abs(rlo), np.abs(rhi)))
    rlo, rhi = rlo - guard, rhi + guard
    absolute_min = np.maximum(np.maximum(rlo, -rhi), 0.0)
    return _down(absolute_min @ absolute_min)


def exterior_lower_bound(radius, anchors, rss, intercepts, n=4.7, d0=1.0):
    """Lower bound for all x outside the radius about the chosen origin."""
    anchor_radius = np.nextafter(np.linalg.norm(anchors, axis=1), np.inf)
    distance_lower = np.maximum(0.0, np.nextafter(radius - anchor_radius, -np.inf))
    rlo = rss - intercepts + 10.0 * n * np.log10((distance_lower + d0) / d0)
    rlo -= 1e-12 * (1.0 + np.abs(rlo))
    positive_min = np.maximum(rlo, 0.0)
    return _down(positive_min @ positive_min)


def certified_radius(anchors, rss, intercepts, incumbent, n=4.7, d0=1.0):
    """Find a ball excluding an improving exterior, subject to numerical guards."""
    radius = max(1.0, float(np.max(np.linalg.norm(anchors, axis=1))))
    for doubling in range(80):
        lower = exterior_lower_bound(radius, anchors, rss, intercepts, n, d0)
        if lower > incumbent + 1e-10 * (1.0 + incumbent):
            return radius, lower, doubling
        radius *= 2.0
    raise ArithmeticError("Could not bound exterior; numerical objective gap unavailable")


def audit(anchors, rss, intercepts, primary_result, n=4.7, d0=1.0,
          max_splits=30000, objective_tolerance_db2=0.01):
    """Independent stronger starts, then a deterministic numerical bound audit.

    Five-by-five geometric grid plus receiver starts; 1000 local evaluations per
    start. Split the rectangle with smallest lower bound along its longest side;
    ties follow insertion order and x-axis first. The incumbent is evaluated at
    child centres; it is not fed back into the production result. No wall-clock
    limits. A positive unresolved gap is reported, never silently certified.
    """
    clock = time.monotonic()
    anchors, rss, intercepts = _validate(anchors, rss, intercepts, n, d0)
    if (not isinstance(max_splits, (int, np.integer)) or max_splits < 0 or
        not np.isfinite(objective_tolerance_db2) or objective_tolerance_db2 <= 0):
        raise ValueError("nonnegative integer max_splits and positive finite tolerance required")
    origin, a, scale, starts = _geometry(anchors, 5)
    args = (a, rss, intercepts, n, d0)
    best, upper, _, _, records = _local_search(starts, scale, args, AUDIT_MAX_NFEV)
    strong_upper = upper
    primary_point = np.asarray(primary_result["position_m"], dtype=float) - origin
    primary_value = objective(primary_point, *args)
    if primary_point.shape != (2,) or not np.isfinite(primary_point).all() or not np.isfinite(primary_value):
        raise ValueError("Audit requires a finite primary estimate")
    if primary_value < upper:
        best, upper = primary_point.copy(), primary_value
    radius, exterior_bound, doublings = certified_radius(a, rss, intercepts, upper, n, d0)
    lo, hi = np.full(2, -radius), np.full(2, radius)
    heap = [(rectangle_lower_bound(lo, hi, *args), 0, lo, hi)]
    ticket, splits = 1, 0
    while heap:
        lower = min(upper, heap[0][0])
        if upper - lower <= objective_tolerance_db2 or splits >= max_splits:
            break
        bound, _, lo, hi = heapq.heappop(heap)
        if bound > upper:
            continue
        axis = int(np.argmax(hi - lo))
        middle = (lo[axis] + hi[axis]) / 2.0
        if not lo[axis] < middle < hi[axis]:
            # Keep unsplittable box: machine precision is not a proof of a gap.
            heapq.heappush(heap, (bound, ticket, lo, hi))
            break
        hi_left, lo_right = hi.copy(), lo.copy()
        hi_left[axis], lo_right[axis] = middle, middle
        for child_lo, child_hi in ((lo, hi_left), (lo_right, hi)):
            point = (child_lo + child_hi) / 2.0
            value = objective(point, *args)
            if np.isfinite(value) and value < upper:
                upper, best = value, point.copy()
            lb = rectangle_lower_bound(child_lo, child_hi, *args)
            if lb <= upper:
                heapq.heappush(heap, (lb, ticket, child_lo, child_hi))
                ticket += 1
        splits += 1
    lower = min(upper, heap[0][0]) if heap else upper
    gap = max(0.0, upper - lower)
    points, diameter = _competitive(records, upper, origin)
    return {
        "audit_id": "RSS_NLLS_5X5_PLUS_ANCHORS_1000_AND_RECTANGLE_BOUNDS_V1",
        "primary_position_m": list(primary_result["position_m"]),
        "primary_objective_recomputed_db2": primary_value,
        "strong_local_objective_db2": strong_upper,
        "audit_position_m": (best + origin).tolist(),
        "audit_objective_db2": upper,
        "objective_improvement_db2": max(0.0, primary_value - upper),
        "position_shift_m": float(np.linalg.norm(best - primary_point)),
        "global_lower_bound_db2": lower,
        "objective_gap_db2": gap,
        "objective_tolerance_db2": objective_tolerance_db2,
        "objective_gap_met_numerically": bool(gap <= objective_tolerance_db2),
        "status": "numerical_gap_met" if gap <= objective_tolerance_db2 else "uncertified",
        "splits": splits,
        "max_splits": max_splits,
        "outer_radius_m": radius,
        "outer_lower_bound_db2": exterior_bound,
        "outer_doublings": doublings,
        "local_runs": len(records),
        "local_runs_converged": sum(r["success"] for r in records),
        "competitive_local_solution_count": len(points),
        "competitive_local_positions_m": points,
        "competitive_diameter_m": diameter,
        "primary_result_changed": False,
        "exact_global_optimum_claimed": False,
        "position_uniqueness_certified": False,
        "elapsed_seconds": time.monotonic() - clock,
        "certificate_scope": "Numerically guarded objective bound; not directed-rounding proof, positional uniqueness, or localization accuracy",
    }
