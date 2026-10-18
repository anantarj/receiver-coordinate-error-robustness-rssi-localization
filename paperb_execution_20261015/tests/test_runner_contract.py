"""Synthetic input-to-shard-to-merged-array checks; no research outcomes."""
from pathlib import Path
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import run_studies as runner

LOADED_RUNNER_SHA256 = hashlib.sha256(Path(runner.__file__).read_bytes()).hexdigest()


def synthetic_block(offset=0.):
    anchors = np.array([[-500., -300.], [100., -600.], [600., -200.],
                        [700., 500.], [400., 700.], [-200., 800.],
                        [-700., 400.], [-800., -500.]])
    selected = np.array([[1, 3, 5, 0], [1, 5, 7, 0], [3, 5, 7, 0]], np.int16)
    mask = selected > 0
    reference = np.full(8, -30.)
    points = np.array([[70., 40.], [50., 60.], [30., 10.]])
    rss = np.zeros(selected.shape)
    for q in range(3):
        ids = selected[q, mask[q]] - 1
        rss[q, mask[q]] = reference[ids] - 47. * np.log10(np.linalg.norm(points[q] - anchors[ids], axis=1) + 1.) + offset
    field_anchors = np.tile(anchors, (3, 1, 1))
    field_anchors[1, 2] += [100., 25.]
    field_anchors[2, 0] += [-70., 100.]
    refits = np.tile(reference, (3, 1))
    refits[1, 2] += 2.
    refits[2, 0] += 3.
    targets = np.zeros((3, 8), bool)
    targets[1, 2] = True
    targets[2, 0] = True
    return dict(selected_ids=selected, selected_mask=mask, query_rssi_dbm=rss,
                source_rows=np.array([101, 203, 307], np.int64),
                field_D_m=np.array([0., 100., 200.]), field_draw=np.array([-1, 0, 1]),
                field_target_count=np.array([0, 1, 1]), field_anchors_m=field_anchors,
                field_target_mask=targets, reference_intercepts_dbm=reference,
                field_refit_intercepts_dbm=refits)


def read_npz(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix="paperb_runner_contract_") as directory:
        root = Path(directory)
        block = synthetic_block()
        block_path = root / "unit_block.npz"
        runner.save_npz(block_path, **block)
        replica = root / "identical.npz"
        runner.save_npz(replica, **dict(reversed(list(block.items()))))
        assert runner.sha(replica) == runner.sha(block_path)
        checks.append("NPZ_writer_byte_determinism_independent_of_mapping_order")

        # Deliberately cause one distinct input to fail. Cached failed arms must
        # retain their explicit status, positions and denominator entries.
        calls = []
        def finite_or_injected_failure(anchors, rss, intercepts):
            calls.append((anchors.copy(), rss.copy(), intercepts.copy()))
            if len(calls) == 2:
                raise ValueError("synthetic injected failure")
            return dict(finite_output=True, position_m=anchors.mean(axis=0).tolist(),
                        objective_db2=float(np.sum((rss - intercepts) ** 2)), status="synthetic_finite",
                        local_runs=12, local_runs_converged=12, local_runs_failed=0,
                        local_runs_budget_exhausted=0, nfev_total=25,
                        competitive_local_solution_count=1, competitive_diameter_m=0., best_start_index=1)
        with patch.object(runner, "solve", side_effect=finite_or_injected_failure):
            rec = runner.run_shard((str(block_path), 0, 3, str(root / "unit_out")))
        out = read_npz(root / "unit_out" / "unit_block__00000_00003.npz")
        assert len(calls) == 11 == rec["unique_nlls_solves"]
        assert rec["cached_entries"] == 7
        assert rec["scheduled_entries_including_duplicate_zero_arm"] == 18
        assert len(rec["exceptions"]) == 1
        assert rec["finite_entries"] == 14
        assert np.count_nonzero(out["nlls_status"] == "exception_ValueError") == 4
        assert np.isnan(out["nlls_position_m"][:2, :, 1]).all()
        assert out["nlls_finite"][2, :, 1].all()
        checks.append("exact_input_cache_distinguishes_coordinates_and_calibration_and_retains_failures")

        for field in range(3):
            for policy in range(2):
                for query in range(3):
                    ids = block["selected_ids"][query, :3] - 1
                    intercepts = (block["reference_intercepts_dbm"] if policy == 0 else
                                  block["field_refit_intercepts_dbm"][field])
                    # Independently evaluate direct positive-power WCL formula,
                    # without copying the runner's log-sum-exp calculation.
                    w = 10. ** ((block["query_rssi_dbm"][query, :3] - intercepts[ids]) / 10.)
                    p = w / w.sum()
                    wanted = np.sum(p[:, None] * block["field_anchors_m"][field, ids], axis=0)
                    assert np.allclose(out["wcl_position_m"][field, policy, query], wanted, atol=1e-10, rtol=1e-13)
                    target_mass = p[block["field_target_mask"][field, ids]].sum()
                    assert np.isclose(out["wcl_target_mass"][field, policy, query], target_mass, atol=1e-14)
                    assert np.isclose(out["wcl_effective_weight_count"][field, policy, query], 1. / np.sum(p ** 2))
        assert np.array_equal(out["source_rows"], [101, 203, 307])
        checks.append("WCL_matches_independent_power_formula_with_one_based_IDs_and_padding")

        with patch.object(runner, "solve", side_effect=AssertionError("Resume attempted recomputation")):
            resumed = runner.run_shard((str(block_path), 0, 3, str(root / "unit_out")))
        assert resumed == rec
        checks.append("unchanged_completed_shard_resumes_without_recomputation")

        # Exercise actual numerical solver and complete CLI orchestration for
        # the runner's expected 18 blocks, using only this synthetic design.
        runroot = root / "e2e"
        (runroot / "src").mkdir(parents=True)
        for filename in ("run_studies.py", "rss_nlls_production.py"):
            shutil.copy2(ROOT / "src" / filename, runroot / "src" / filename)
        for i in range(18):
            runner.save_npz(runroot / "inputs" / "blocks" / f"synthetic_{i:02}.npz", **synthetic_block(i / 10000.))
        bound = {str(p.relative_to(runroot)): runner.sha(p)
                 for p in sorted(runroot.rglob("*")) if p.is_file()}
        lock = runroot / "protocol" / "EXECUTION_LOCK.json"
        runner.write_json(lock, {"bound_files": bound})
        with patch.object(runner, "ROOT", runroot), patch.object(sys, "argv", ["run_studies.py", "--workers", "1", "--chunk", "2", "--lock", str(lock)]):
            with contextlib.redirect_stdout(io.StringIO()):
                runner.main()
        receipt = json.loads((runroot / "receipts" / "PRIMARY_RUN_RECEIPT.json").read_text())
        assert receipt["blocks"] == 18 and receipt["shards"] == 36
        assert receipt["unique_nlls_solves"] == 18 * 11
        assert receipt["scheduled_entries_including_duplicate_zero_arm"] == 18 * 18
        assert receipt["exceptions"] == 0
        for path in sorted((runroot / "results" / "arrays").glob("*.npz")):
            merged = read_npz(path)
            assert np.array_equal(merged["source_rows"], [101, 203, 307])
            assert np.array_equal(merged["query_indices"], [0, 1, 2])
            assert merged["nlls_position_m"].shape == (3, 2, 3, 2)
            assert merged["nlls_finite"].all()
            shards = [read_npz(p) for p in sorted((runroot / "results" / "shards").glob(path.stem + "__*.npz"))]
            for key, value in merged.items():
                if key.startswith("field_"):
                    assert np.array_equal(value, shards[0][key])
                else:
                    axis = 0 if key in ("source_rows", "query_indices") else 2
                    expected = np.concatenate([s[key] for s in shards], axis=axis)
                    assert np.array_equal(value, expected, equal_nan=True) if value.dtype.kind in "fc" else np.array_equal(value, expected)
        checks.append("complete_18block_real_solver_synthetic_run_and_all_shard_merge_axes")

        # Resume with unchanged chunking must preserve every output byte.
        first_hashes = dict(receipt["output_arrays"])
        with patch.object(runner, "ROOT", runroot), patch.object(sys, "argv", ["run_studies.py", "--workers", "1", "--chunk", "2", "--lock", str(lock)]):
            with contextlib.redirect_stdout(io.StringIO()):
                runner.main()
        second_receipt = json.loads((runroot / "receipts" / "PRIMARY_RUN_RECEIPT.json").read_text())
        assert second_receipt["output_arrays"] == first_hashes
        checks.append("full_resume_preserves_merged_array_bytes")

        # Lock edits are rejected before additional production computation.
        changed = runroot / "inputs" / "blocks" / "synthetic_00.npz"
        changed.write_bytes(changed.read_bytes() + b"changed")
        with patch.object(runner, "ROOT", runroot):
            try:
                runner.verify_lock(lock)
            except ValueError:
                pass
            else:
                raise AssertionError("Changed bound input was accepted")
        checks.append("changed_input_rejected_by_execution_lock")

    final = {"status": "PASS", "purpose": "Synthetic orchestration contract only; no scientific outputs",
             "checks": checks, "check_count": len(checks),
             "runner_source_sha256_at_import": LOADED_RUNNER_SHA256,
             "solver_source_sha256": runner.sha(ROOT / "src" / "rss_nlls_production.py"),
             "test_source_sha256": runner.sha(Path(__file__)),
             "synthetic_end_to_end": {"blocks": 18, "shards": 36, "scheduled_entries": 324, "unique_solves": 198}}
    runner.write_json(ROOT / "receipts" / "RUNNER_CONTRACT_AUDIT.json", final)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
