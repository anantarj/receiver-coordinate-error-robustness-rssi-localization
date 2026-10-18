"""Read-only independent checks after primary completion; never invokes solver."""
from pathlib import Path
import hashlib
import json
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same(a, b):
    if np.asarray(a).dtype.kind in "fc":
        return np.array_equal(a, b, equal_nan=True)
    return np.array_equal(a, b)


def main():
    began = time.monotonic()
    primary_path = ROOT / "receipts/PRIMARY_RUN_RECEIPT.json"
    receipt = json.loads(primary_path.read_text())
    assert receipt["status"] == "COMPLETE", "No audit before all primary outputs complete"
    lock_path = ROOT / "protocol/EXECUTION_LOCK.json"
    lock = json.loads(lock_path.read_text())
    assert receipt["lock_sha256"] == sha(lock_path)
    for name, digest in lock["bound_files"].items():
        assert sha(ROOT / name) == digest, name
    registry = json.loads((ROOT / "inputs/INPUT_REGISTRY.json").read_text())
    nlls_objective_max_abs = 0.
    nlls_objective_max_fraction_of_tolerance = 0.
    wcl_position_max_discrepancy = 0.
    target_mass_max_discrepancy = 0.
    effective_count_max_discrepancy = 0.
    entries = unique = reused = finite_entries = unaffected_pairs = 0
    global_exceptions = local_failed_entries = local_unconverged_entries = 0
    per_block = []
    input_keys = ("source_rows", "selected_ids", "selected_mask", "query_rssi_dbm",
                  "reference_intercepts_dbm", "field_refit_intercepts_dbm", "field_anchors_m",
                  "field_target_mask", "field_D_m", "field_draw", "field_target_count")
    for item in registry["blocks"]:
        input_path = ROOT / item["path"]
        output_path = ROOT / "results/arrays" / (item["block_id"] + ".npz")
        assert sha(output_path) == receipt["output_arrays"][output_path.name]
        with np.load(input_path, allow_pickle=False) as z:
            b = {key: z[key] for key in input_keys}
        with np.load(output_path, allow_pickle=False) as z:
            out = {key: z[key] for key in z.files}
        assert same(out["source_rows"], b["source_rows"])
        assert same(out["query_indices"], np.arange(len(b["source_rows"])))
        for key in ("field_D_m", "field_draw", "field_target_count"):
            assert same(out[key], b[key])
        qn, fn = len(b["source_rows"]), len(b["field_D_m"])
        assert out["nlls_position_m"].shape == (fn, 2, qn, 2)
        assert out["wcl_position_m"].shape == (fn, 2, qn, 2)
        zero = np.flatnonzero(b["field_D_m"] == 0)
        assert len(zero) == 1
        zero = int(zero[0])
        per_query_keys = [dict() for _ in range(qn)]
        solver_fields = [key for key in out if key.startswith("nlls_")]
        prediction_fields = solver_fields + [key for key in out if key.startswith("wcl_")]
        for key in prediction_fields:
            assert same(out[key][zero, 0], out[key][zero, 1]), (item["block_id"], key, "zero policy mismatch")
        block_unique = block_reused = block_failures = block_unaffected = 0
        block_objective_max = block_wcl_max = 0.
        for fi in range(fn):
            for pi in range(2):
                fits = b["reference_intercepts_dbm"] if pi == 0 else b["field_refit_intercepts_dbm"][fi]
                for qi in range(qn):
                    index = fi, pi, qi
                    mask = b["selected_mask"][qi].astype(bool)
                    ids = b["selected_ids"][qi, mask].astype(int)
                    aa = b["field_anchors_m"][fi, ids - 1]
                    ss = b["query_rssi_dbm"][qi, mask]
                    fit = fits[ids - 1]
                    assert len(ids) >= 3 and len(ids) <= 10
                    # Independent direct-power expression, using supplied
                    # absolute positions rather than the runner's centred sum.
                    weights = np.power(10., (ss - fit) / 10.)
                    weights /= weights.sum()
                    expected_wcl = np.dot(weights, aa)
                    discrepancy = float(np.linalg.norm(expected_wcl - out["wcl_position_m"][index]))
                    assert discrepancy < 1e-7, (item["block_id"], index, "WCL", discrepancy)
                    block_wcl_max = max(block_wcl_max, discrepancy)
                    mass = float(np.sum(weights[b["field_target_mask"][fi, ids - 1]]))
                    neff = float(1. / np.dot(weights, weights))
                    mass_difference = abs(mass - out["wcl_target_mass"][index])
                    neff_difference = abs(neff - out["wcl_effective_weight_count"][index])
                    assert mass_difference < 1e-12 and neff_difference < 1e-11
                    target_mass_max_discrepancy = max(target_mass_max_discrepancy, mass_difference)
                    effective_count_max_discrepancy = max(effective_count_max_discrepancy, neff_difference)

                    point = out["nlls_position_m"][index]
                    value = float(out["nlls_objective_db2"][index])
                    finite = np.isfinite(point).all() and np.isfinite(value)
                    assert bool(out["nlls_finite"][index]) == bool(finite)
                    status = str(out["nlls_status"][index])
                    assert status != "not_executed"
                    runs = int(out["nlls_local_runs"][index])
                    converged = int(out["nlls_local_converged"][index])
                    failed = int(out["nlls_local_failed"][index])
                    exhausted = int(out["nlls_local_exhausted"][index])
                    nfev = int(out["nlls_nfev"][index])
                    assert min(runs, converged, failed, exhausted, nfev) >= 0
                    assert converged + failed + exhausted <= runs
                    assert nfev <= 200 * runs
                    assert runs - failed <= nfev if runs else nfev == 0
                    if status.startswith("exception_"):
                        assert not finite and runs == 0 and out["nlls_best_start"][index] == -1
                    else:
                        assert runs == 9 + len(ids)
                        if finite:
                            assert 0 <= out["nlls_best_start"][index] < runs
                            assert out["nlls_competitive_count"][index] >= 0
                            assert np.isfinite(out["nlls_competitive_diameter_m"][index]) and out["nlls_competitive_diameter_m"][index] >= 0
                            expected_status = ("finite_all_local_runs_converged" if converged == runs else
                                               "finite_some_local_runs_unconverged" if converged else
                                               "finite_no_local_run_converged")
                            assert status == expected_status
                    if finite:
                        # Stored positions include origin restoration; direct
                        # UTM subtraction can differ by sub-nanometre rounding.
                        residual = ss - fit + 47. * np.log10(1. + np.linalg.norm(point - aa, axis=1))
                        reconstructed = float(np.dot(residual, residual))
                        difference = abs(reconstructed - value)
                        tolerance = 5e-7 + 1e-9 * abs(value)
                        assert difference <= tolerance, (item["block_id"], index, "objective", difference, tolerance)
                        block_objective_max = max(block_objective_max, difference)
                        nlls_objective_max_fraction_of_tolerance = max(nlls_objective_max_fraction_of_tolerance, difference / tolerance)

                    key = aa.tobytes(), ss.tobytes(), fit.tobytes()
                    expected_reuse = key in per_query_keys[qi]
                    assert bool(out["exact_input_reused"][index]) == expected_reuse
                    if expected_reuse:
                        previous = per_query_keys[qi][key]
                        for name in solver_fields:
                            assert same(out[name][index], out[name][previous]), (item["block_id"], index, name, "cache mismatch")
                        block_reused += 1
                    else:
                        per_query_keys[qi][key] = index
                        block_unique += 1
                        if status.startswith("exception_"):
                            global_exceptions += 1
                    if fi != zero and not b["field_target_mask"][fi, ids - 1].any():
                        for name in prediction_fields:
                            assert same(out[name][index], out[name][zero, 0, qi]), (item["block_id"], index, name, "unexposed mismatch")
                        block_unaffected += 1
                    block_failures += int(not finite)
                    local_failed_entries += int(failed > 0)
                    local_unconverged_entries += int(converged < runs)
        block_entries = fn * 2 * qn
        assert block_unique + block_reused == block_entries
        entries += block_entries
        unique += block_unique
        reused += block_reused
        finite_entries += block_entries - block_failures
        unaffected_pairs += block_unaffected
        wcl_position_max_discrepancy = max(wcl_position_max_discrepancy, block_wcl_max)
        nlls_objective_max_abs = max(nlls_objective_max_abs, block_objective_max)
        per_block.append({"block": item["block_id"], "scheduled_entries": block_entries,
                          "unique_inputs": block_unique, "cached_entries": block_reused,
                          "nonfinite_entries": block_failures, "unexposed_arm_equalities": block_unaffected,
                          "maximum_WCL_discrepancy_m": block_wcl_max,
                          "maximum_NLLS_objective_discrepancy_db2": block_objective_max})
    assert entries == receipt["scheduled_entries_including_duplicate_zero_arm"]
    assert unique == receipt["unique_nlls_solves"]
    assert global_exceptions == receipt["exceptions"]
    assert entries == 195200
    shards = sorted((ROOT / "results/shards").glob("*.json"))
    assert len(shards) == receipt["shards"]
    shard_counts = dict(unique=0, cached=0, entries=0, finite=0, exceptions=0)
    for path in shards:
        s = json.loads(path.read_text())
        assert s["status"] == "COMPLETE"
        assert sha(path.with_suffix(".npz")) == s["output_sha256"]
        assert sha(ROOT / "inputs/blocks" / (s["block"] + ".npz")) == s["input_sha256"]
        assert s["runner_sha256"] == lock["bound_files"]["src/run_studies.py"]
        assert s["solver_sha256"] == lock["bound_files"]["src/rss_nlls_production.py"]
        shard_counts["unique"] += s["unique_nlls_solves"]
        shard_counts["cached"] += s["cached_entries"]
        shard_counts["entries"] += s["scheduled_entries_including_duplicate_zero_arm"]
        shard_counts["finite"] += s["finite_entries"]
        shard_counts["exceptions"] += len(s["exceptions"])
    assert shard_counts == dict(unique=unique, cached=reused, entries=entries, finite=finite_entries, exceptions=global_exceptions)
    for name, digest in lock["bound_files"].items():
        assert sha(ROOT / name) == digest
    for name, digest in receipt["output_arrays"].items():
        assert sha(ROOT / "results/arrays" / name) == digest
    final = {
        "status": "PASS", "purpose": "Independent read-only verification of all primary outputs; no solver rerun or localization-error analysis",
        "script_sha256": sha(Path(__file__)), "lock_sha256": sha(lock_path),
        "primary_receipt_sha256": sha(primary_path), "blocks": len(per_block),
        "scheduled_entries": entries, "unique_solver_inputs": unique, "cached_entries": reused,
        "finite_entries": finite_entries, "unique_global_exceptions": global_exceptions,
        "entries_with_any_local_exception": local_failed_entries,
        "entries_with_any_local_nonconvergence": local_unconverged_entries,
        "exact_unexposed_prediction_equalities": unaffected_pairs,
        "maximum_WCL_prediction_discrepancy_m": wcl_position_max_discrepancy,
        "maximum_target_weight_mass_discrepancy": float(target_mass_max_discrepancy),
        "maximum_effective_weight_count_discrepancy": float(effective_count_max_discrepancy),
        "maximum_NLLS_objective_discrepancy_db2": nlls_objective_max_abs,
        "maximum_NLLS_objective_discrepancy_fraction_of_tolerance": nlls_objective_max_fraction_of_tolerance,
        "objective_tolerance_definition": "5e-7 + 1e-9*abs(stored_objective) dB^2; covers restoration of local coordinates to UTM before independent direct subtraction",
        "zero_map_policies_identical": True, "exact_input_cache_verified": True,
        "input_lock_and_primary_arrays_verified_unchanged": True,
        "query_reference_coordinates_read": False, "solver_invoked": False,
        "blocks_verified": per_block, "elapsed_seconds": time.monotonic() - began}
    path = ROOT / "receipts/INDEPENDENT_PRIMARY_OUTPUT_AUDIT.json"
    path.write_text(json.dumps(final, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in final.items() if k != "blocks_verified"}, indent=2))


if __name__ == "__main__":
    main()
