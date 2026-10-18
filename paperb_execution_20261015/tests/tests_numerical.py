"""Synthetic production-algorithm checks; no Antwerp calibration contrasts."""
from pathlib import Path
import copy
import hashlib
import inspect
import json
import platform
import sys
import time
from unittest.mock import patch

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import rss_nlls_production as solver


def rss_at(x, anchors, intercepts, n=4.7, d0=1.0):
    return intercepts - 10 * n * np.log10((np.linalg.norm(x - anchors, axis=1) + d0) / d0)


def main():
    clock = time.monotonic()
    checks = []
    anchors = np.array([[-800, -600], [900, -400], [750, 850], [-650, 900], [150, -950], [100, 600]], float)
    intercepts = np.array([-30, -32, -29, -31, -33, -28], float)
    truth = np.array([120., -80.])
    rss = rss_at(truth, anchors, intercepts)
    exact = solver.solve(anchors, rss, intercepts)
    assert exact["finite_output"]
    assert exact["local_runs"] == 9 + len(anchors)
    assert max(exact["local_nfev"]) <= 200
    exact_error = float(np.linalg.norm(np.asarray(exact["position_m"]) - truth))
    assert exact_error < 1e-5
    checks.append("noiseless_position_and_all_fixed_starts")

    rerun = solver.solve(anchors, rss, intercepts)
    comparable = lambda x: {k: v for k, v in x.items() if k != "elapsed_seconds"}
    assert comparable(exact) == comparable(rerun)
    checks.append("identical_inputs_repeat_deterministically")

    shift = np.array([1e6, -2e6])
    translated = solver.solve(anchors + shift, rss, intercepts)
    covariance_error = float(np.linalg.norm(np.asarray(translated["position_m"]) - np.asarray(exact["position_m"]) - shift))
    assert covariance_error < 1e-6
    checks.append("translation_covariance_unique_synthetic_solution")

    line_anchors = np.array([[-100., 0], [0, 0], [100., 0], [200., 0]])
    line_intercepts = np.full(4, -30.)
    line_rss = rss_at(np.array([30., 40.]), line_anchors, line_intercepts)
    mirror = solver.solve(line_anchors, line_rss, line_intercepts)
    assert mirror["competitive_local_solution_count"] >= 2
    assert mirror["competitive_diameter_m"] > 79.9
    assert mirror["objective_db2"] < 1e-15
    assert not mirror["position_uniqueness_certified"]
    checks.append("collinear_mirror_ambiguity_retained")

    # Every start must still execute if SciPy rejects every attempted local fit.
    with patch.object(solver, "least_squares", side_effect=RuntimeError("synthetic injected failure")) as mocked:
        fallback = solver.solve(anchors, rss, intercepts)
    assert mocked.call_count == 9 + len(anchors)
    assert fallback["finite_output"]
    assert fallback["local_runs_failed"] == 9 + len(anchors)
    assert fallback["local_runs_converged"] == 0
    assert fallback["status"] == "finite_no_local_run_converged"
    assert fallback["best_candidate_source"] == "start"
    checks.append("all_solver_exceptions_explicit_and_finite_start_retained")

    for kwargs in ({"rss": np.full(len(anchors), np.nan)}, {"n": np.nan}, {"d0": np.inf}, {"d0": 0.}):
        arguments = dict(anchors=anchors, rss=rss, intercepts=intercepts)
        arguments.update(kwargs)
        try:
            solver.solve(**arguments)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid input was accepted")
    checks.append("invalid_and_nonfinite_inputs_rejected")

    # Check the analytic gradient away from receiver coincidences.
    jac = solver._jacobian(truth, anchors, rss, intercepts, 4.7, 1.)
    h = 1e-3
    fd = np.column_stack([(solver.residual(truth + np.eye(2)[i] * h, anchors, rss, intercepts) -
                           solver.residual(truth - np.eye(2)[i] * h, anchors, rss, intercepts)) / (2 * h)
                          for i in range(2)])
    jac_error = float(np.max(np.abs(jac - fd)))
    assert jac_error < 1e-8
    checks.append("jacobian_matches_central_difference_away_from_nonsmooth_points")

    noisy = rss + np.array([3., -4., 2., -1., 5., -2.])
    noisy_primary = solver.solve(anchors, noisy, intercepts)
    frozen_copy = copy.deepcopy(noisy_primary)
    audit_zero = solver.audit(anchors, noisy, intercepts, noisy_primary, max_splits=0, objective_tolerance_db2=1e-12)
    assert noisy_primary == frozen_copy
    assert audit_zero["splits"] == 0
    assert not audit_zero["objective_gap_met_numerically"]
    assert audit_zero["audit_objective_db2"] <= audit_zero["primary_objective_recomputed_db2"] + 1e-10
    assert audit_zero["local_runs"] == 25 + len(anchors)
    assert not audit_zero["exact_global_optimum_claimed"]
    checks.append("stronger_audit_independent_preserves_primary_and_exposes_unresolved_gap")

    audit_30k = solver.audit(anchors, noisy, intercepts, noisy_primary, max_splits=30000, objective_tolerance_db2=.01)
    assert noisy_primary == frozen_copy
    assert audit_30k["splits"] <= 30000
    assert audit_30k["objective_gap_db2"] <= audit_zero["objective_gap_db2"] + 1e-9
    assert audit_30k["audit_objective_db2"] <= audit_zero["audit_objective_db2"] + 1e-9
    assert audit_30k["objective_gap_met_numerically"] == (audit_30k["objective_gap_db2"] <= .01)
    checks.append("fixed_split_audit_reports_actual_gap_and_retains_primary")

    rng = np.random.default_rng(20261015)
    worst_violation = -float("inf")
    for _ in range(100):
        lo = rng.uniform(-2000, 1000, 2)
        hi = lo + rng.uniform(1, 1500, 2)
        lb = solver.rectangle_lower_bound(lo, hi, anchors, noisy, intercepts)
        points = rng.uniform(lo, hi, (100, 2))
        actual = min(solver.objective(point, anchors, noisy, intercepts) for point in points)
        worst_violation = max(worst_violation, lb - actual)
        assert lb <= actual + 1e-9
    checks.append("10000_sampled_rectangle_bound_checks")

    origin = anchors.mean(axis=0)
    a = anchors - origin
    radius, lower, doublings = solver.certified_radius(a, noisy, intercepts, noisy_primary["objective_db2"])
    assert lower > noisy_primary["objective_db2"]
    for factor in [1., 1.01, 2., 10.]:
        for angle in np.linspace(0, 2 * np.pi, 100, endpoint=False):
            point = radius * factor * np.array([np.cos(angle), np.sin(angle)])
            assert solver.objective(point, a, noisy, intercepts) >= lower - 1e-8
    checks.append("400_sampled_exterior_bound_checks")

    # Zero-radius receiver constellation is valid input: no geometry-derived
    # divide-by-zero or absent starts. It does not imply positional uniqueness.
    coincident = solver.solve(np.zeros((3, 2)), np.array([-60., -61., -62.]), np.full(3, -30.))
    assert coincident["finite_output"] and coincident["local_runs"] == 12
    checks.append("coincident_receiver_geometry_explicit_finite_algorithm_output")

    assert set(inspect.signature(solver.solve).parameters) == {"anchors", "rss", "intercepts", "n", "d0"}
    source = Path(solver.__file__).read_text()
    assert "time.monotonic() - clock >=" not in source
    checks.append("interface_has_no_query_reference_WCL_or_wallclock_stop_input")

    output = {
        "purpose": "Synthetic finite-algorithm and numerical-bound verification only; no calibration-effect experiment",
        "status": "PASS",
        "algorithm_id": solver.ALGORITHM_ID,
        "checks": checks,
        "check_count": len(checks),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "source_sha256": hashlib.sha256(Path(solver.__file__).read_bytes()).hexdigest(),
        "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "noiseless_error_m": exact_error,
        "translation_covariance_error_m": covariance_error,
        "jacobian_max_absolute_error": jac_error,
        "mirror_competitive_diameter_m": mirror["competitive_diameter_m"],
        "worst_sampled_rectangle_bound_minus_sample_min_db2": float(worst_violation),
        "noisy_audit_30000": audit_30k,
        "mathematical_audit": {
            "rectangle": "For each receiver, distance lies between exact rectangle nearest/farthest distances. Positive n makes residual monotone in distance. Squared-residual interval minimum is zero if residual straddles zero, otherwise nearer endpoint squared. Sum is a valid mathematical lower bound even when individual minima cannot occur together.",
            "exterior": "Reverse triangle inequality gives distance >= R-||a_i|| for ||x||>=R. Positive residual lower bounds alone contribute squared lower bounds; negative lower residual permits zero. For n>0 all residual lower bounds diverge with R; doubling eventually excludes an improving exterior in exact arithmetic.",
            "square": "The square [-R,R]^2 covers the ball. Every point outside the square is outside the ball, whose objective already exceeds the incumbent. A numerical lower bound over the square therefore supports a whole-plane objective gap under the stated floating-point caveat.",
            "precision": "nextafter and explicit guards are conservative checks, not formal directed-rounding interval arithmetic. Bound sampling is a regression check, not a proof of floating-point correctness.",
            "solver_scope": "Fixed finite algorithm; endpoints include nonconverged finite results, and finite starting points survive failures. Minimum objective is not positional accuracy or uniqueness.",
            "scaling": "Production uses M+9 local starts and at most 200 residual evaluations per start; analytic Jacobians cost O(M). Stronger audit uses M+25 starts at 1000 evaluations, then at most B splits, each with two O(M) bounds/objectives and heap O(log B); retained rectangle storage O(B)."
        },
        "elapsed_seconds": time.monotonic() - clock,
    }
    out = ROOT / "receipts" / "NUMERICAL_PRODUCTION_AUDIT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k not in {"mathematical_audit", "noisy_audit_30000"}}, indent=2))


if __name__ == "__main__":
    main()
