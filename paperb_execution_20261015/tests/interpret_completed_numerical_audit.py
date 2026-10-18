"""Separate objective quality from positional sensitivity in locked spot audits."""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distribution(values):
    a = np.asarray(values, float)
    return {"minimum": float(np.min(a)), "median": float(np.median(a)),
            "p95": float(np.quantile(a, .95)), "maximum": float(np.max(a))}


def main():
    receipt_path = ROOT / "receipts/NUMERICAL_AUDIT_RECEIPT.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "COMPLETE"
    primary_path = ROOT / "receipts/PRIMARY_RUN_RECEIPT.json"
    primary = json.loads(primary_path.read_text())
    lock_path = ROOT / "protocol/EXECUTION_LOCK.json"
    lock = json.loads(lock_path.read_text())
    for name, digest in lock["bound_files"].items():
        assert sha(ROOT / name) == digest
    for name, digest in primary["output_arrays"].items():
        assert sha(ROOT / "results/arrays" / name) == digest
    cells = []
    input_cache = {}
    max_objective_difference = 0.
    for cell_id, digest in receipt["cell_outputs"].items():
        path = ROOT / "results/numerical_audits/cells" / (cell_id + ".json")
        assert sha(path) == digest
        record = json.loads(path.read_text())
        assert not record["primary_output_changed"] and not record["localization_errors_scored"]
        if record["status"] != "COMPLETE":
            continue
        spec = record["specification"]
        block = spec["block"]
        if block not in input_cache:
            with np.load(ROOT / "inputs/blocks" / (block + ".npz"), allow_pickle=False) as z:
                input_cache[block] = {key: z[key] for key in (
                    "selected_mask", "selected_ids", "query_rssi_dbm", "field_anchors_m",
                    "reference_intercepts_dbm", "field_refit_intercepts_dbm")}
        b = input_cache[block]
        qi, fi, pi = spec["query_index"], spec["field_index"], spec["policy_index"]
        mask = b["selected_mask"][qi].astype(bool)
        ids = b["selected_ids"][qi, mask].astype(int) - 1
        a = b["field_anchors_m"][fi, ids]
        s = b["query_rssi_dbm"][qi, mask]
        fitted = (b["reference_intercepts_dbm"] if pi == 0 else b["field_refit_intercepts_dbm"][fi])[ids]
        initial = record["initial_audit"]
        threshold = max(1e-4, 1e-6 * (1. + record["primary_objective_db2"]))
        expected_triggers = []
        if record["primary_local_runs_converged"] < record["primary_local_runs"]:
            expected_triggers.append("any_primary_local_start_unconverged")
        if initial["objective_improvement_db2"] > threshold:
            expected_triggers.append("objective_improvement_above_threshold")
        if initial["position_shift_m"] > 1.:
            expected_triggers.append("position_shift_above_1m")
        assert record["escalation_triggered_by"] == expected_triggers
        assert record["final_audit_stage"] == ("escalated_audit" if expected_triggers else "initial_audit")
        for stage in ("initial_audit", "escalated_audit"):
            if record[stage] is None:
                continue
            result = record[stage]
            max_splits = 30000 if stage == "initial_audit" else 100000
            assert result["max_splits"] == max_splits and result["splits"] <= max_splits
            assert result["local_runs"] == 25 + len(ids)
            assert not result["primary_result_changed"]
            assert not result["exact_global_optimum_claimed"]
            assert not result["position_uniqueness_certified"]
            point = np.asarray(result["audit_position_m"])
            residual = s - fitted + 47. * np.log10(1. + np.linalg.norm(point - a, axis=1))
            reconstructed = float(residual @ residual)
            difference = abs(reconstructed - result["audit_objective_db2"])
            max_objective_difference = max(max_objective_difference, difference)
            assert difference <= 5e-7 + 1e-9 * abs(result["audit_objective_db2"])
            assert result["global_lower_bound_db2"] <= result["audit_objective_db2"] + 1e-12
            gap = max(0., result["audit_objective_db2"] - result["global_lower_bound_db2"])
            assert abs(gap - result["objective_gap_db2"]) < 1e-9
            assert result["objective_gap_met_numerically"] == (gap <= .01)
            shift = float(np.linalg.norm(point - record["primary_position_m"]))
            assert abs(shift - result["position_shift_m"]) < 1e-6
        final = record[record["final_audit_stage"]]
        cells.append({"cell_id": cell_id, "block": block, "source_row": spec["source_row"], "field_index": fi,
                      "kind": spec["kind"], "field_D_m": record["field_D_m"], "policy": record["policy"],
                      "gap_met": final["objective_gap_met_numerically"],
                      "gap_db2": final["objective_gap_db2"],
                      "gap_over_one_plus_objective": final["objective_gap_db2"] / (1. + final["audit_objective_db2"]),
                      "objective_improvement_db2": final["objective_improvement_db2"],
                      "objective_improvement_above_threshold": final["objective_improvement_db2"] > threshold,
                      "position_shift_m": final["position_shift_m"], "position_shift_above_1m": final["position_shift_m"] > 1.,
                      "competitive_diameter_m": final["competitive_diameter_m"],
                      "escalated": bool(expected_triggers)})
    assert len(cells) == receipt["completed_audits"]
    assert sum(c["gap_met"] for c in cells) == receipt["final_numerical_objective_gap_met"]
    assert sum(c["escalated"] for c in cells) == receipt["escalated_cells"]
    matrix = []
    for objective_changed in (False, True):
        for position_changed in (False, True):
            selected = [c for c in cells if c["objective_improvement_above_threshold"] == objective_changed
                        and c["position_shift_above_1m"] == position_changed]
            matrix.append({"objective_improvement_above_locked_threshold": objective_changed,
                           "position_shift_above_1m": position_changed, "audited_states": len(selected),
                           "gap_met_states": sum(c["gap_met"] for c in selected)})
    for name, digest in primary["output_arrays"].items():
        assert sha(ROOT / "results/arrays" / name) == digest
    paired = {}
    zero_shifts = {}
    for c in cells:
        paired.setdefault((c["block"], c["source_row"], c["field_index"]), {})[c["policy"]] = c
        if c["field_D_m"] == 0.:
            zero_shifts[c["block"], c["source_row"]] = c["position_shift_m"]
    calibration_bounds = []
    perturbation_bounds = []
    for key, policies in paired.items():
        if {"frozen", "receiver_specific_refit"}.issubset(policies):
            bound = policies["frozen"]["position_shift_m"] + policies["receiver_specific_refit"]["position_shift_m"]
            calibration_bounds.append({"block": key[0], "source_row": key[1], "field_index": key[2], "upper_bound_m": bound})
        for c in policies.values():
            if c["field_D_m"] != 0.:
                bound = c["position_shift_m"] + zero_shifts[c["block"], c["source_row"]]
                perturbation_bounds.append({"cell_id": c["cell_id"], "upper_bound_m": bound})
    final = {
        "status": "PASS", "scope": "Read-only numerical-audit integrity and interpretation; no physical localization-error analysis",
        "script_sha256": sha(Path(__file__)), "numerical_audit_receipt_sha256": sha(receipt_path),
        "completed_audits": len(cells), "scheduled_audits": receipt["scheduled_cells"],
        "audit_exceptions": receipt["audit_exceptions"], "primary_nonfinite": receipt["primary_nonfinite"],
        "gap_met_states": sum(c["gap_met"] for c in cells),
        "unresolved_gap_states": sum(not c["gap_met"] for c in cells),
        "position_shift_above_1m_states": sum(c["position_shift_above_1m"] for c in cells),
        "competitive_diameter_above_1m_states": sum(c["competitive_diameter_m"] > 1. for c in cells),
        "objective_improvement_vs_position_shift": matrix,
        "objective_gap_db2": distribution([c["gap_db2"] for c in cells]),
        "relative_gap_over_one_plus_objective": distribution([c["gap_over_one_plus_objective"] for c in cells]),
        "objective_improvement_db2": distribution([c["objective_improvement_db2"] for c in cells]),
        "position_shift_m": distribution([c["position_shift_m"] for c in cells]),
        "competitive_diameter_m": distribution([c["competitive_diameter_m"] for c in cells]),
        "largest_position_shifts": sorted(cells, key=lambda c: (-c["position_shift_m"], c["cell_id"]))[:10],
        "maximum_recomputed_audit_objective_discrepancy_db2": max_objective_difference,
        "paired_numerical_sensitivity_bounds": {
            "derivation": "Reverse triangle inequality: replacing prediction x by x' changes its Euclidean error against any fixed reference by at most ||x'-x||. A difference of two errors changes by at most the sum of the two prediction shifts. This is a worst-case bound, not a measured error change.",
            "calibration_paired_states": len(calibration_bounds),
            "maximum_bound_for_refit_minus_frozen_error_contrast_m": max(c["upper_bound_m"] for c in calibration_bounds),
            "largest_calibration_contrast_bound": max(calibration_bounds, key=lambda c: c["upper_bound_m"]),
            "positive_vs_reference_states": len(perturbation_bounds),
            "maximum_bound_for_positive_minus_reference_error_contrast_m": max(c["upper_bound_m"] for c in perturbation_bounds),
            "scope": "Only the fully paired audited rows and states; does not bound unsampled queries or certify global numerical optima."
        },
        "interpretation": [
            "Audit cases were selected by exposure and source ID, then crossed with study states. Counts are diagnostic, not a population optimizer-failure rate.",
            "Unresolved objective gaps mean the finite numerical audit did not bound the optimum to its requested tolerance. They do not establish a bad location estimate.",
            "A stronger-search positional shift is a numerical sensitivity measure. Without reference-position scoring it has no established direction of physical accuracy change.",
            "A large positional shift with little objective improvement indicates near-competitive locations or a shallow objective, but does not by itself prove multiple exact global minimizers.",
            "Meeting a numerical objective-gap tolerance does not certify positional uniqueness or accuracy.",
            "Primary finite-algorithm outputs remain unchanged; no audited endpoint replaces them."
        ],
        "primary_output_hashes_verified_unchanged": True,
        "query_reference_coordinates_read": False, "solver_invoked": False}
    destination = ROOT / "receipts/INDEPENDENT_NUMERICAL_AUDIT_INTERPRETATION.json"
    destination.write_text(json.dumps(final, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in final.items() if k not in ("largest_position_shifts", "interpretation")}, indent=2))


if __name__ == "__main__":
    main()
