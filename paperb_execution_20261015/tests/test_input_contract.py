"""Independently reconstruct prepared identities/fits from raw data, no estimates."""
from pathlib import Path
import hashlib
import json
import random
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = ROOT.parent / "paperb_development_20261015"
sys.path.insert(0, str(DEVELOPMENT / "private/audit_dependencies"))
from pyproj import Transformer

RAW_SHA = "870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446"
OFFICIAL_SHA = "487b4853a364921c36c624485be4831f96d2c4db8bd2082529bc9136fb58172f"
RECOVERED_SHA = "cfddca4fc5a0ad51fb4d8717be807454c891ba3c4872ff1a4e6b9aec3f5ae2da"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unpack(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def rank_query(rows):
    return np.asarray(sorted(map(int, rows), key=lambda r: (hashlib.sha256(
        ("paperb_broader_validation_v1:query:" + str(r)).encode()).hexdigest(), r)))


def equal(actual, expected):
    assert np.array_equal(actual, expected, equal_nan=True) if np.asarray(actual).dtype.kind in "fc" else np.array_equal(actual, expected)


def main():
    clock = time.monotonic()
    registry_path = ROOT / "inputs/INPUT_REGISTRY.json"
    registry = json.loads(registry_path.read_text())
    manifest_path = ROOT / "inputs/INPUT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest.items():
        assert sha(ROOT / name) == digest, name
    raw = DEVELOPMENT / "inputs/lorawan_antwerp_2019_dataset.csv"
    assert sha(raw) == RAW_SHA
    data = pd.read_csv(raw)
    rss = data[["BS " + str(i) for i in range(1, 73)]].to_numpy(float)
    valid = np.isfinite(rss) & (rss >= -150.) & (rss <= -20.)
    lon, lat = data.Longitude.to_numpy(float), data.Latitude.to_numpy(float)
    working = np.flatnonzero(np.isfinite(lon) & np.isfinite(lat) & (valid.sum(axis=1) >= 3))
    assert len(working) == 55375
    tx, ty = Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True).transform(lon, lat)
    xy = np.column_stack((tx, ty))
    shuffled = working.tolist()
    random.Random(1).shuffle(shuffled)
    original_train = np.asarray(shuffled[:16612])
    original_test = np.asarray(shuffled[16612:])
    midpoint = np.median(xy[working], axis=0)
    equal(registry["spatial_split"]["center_EPSG32631_m"], midpoint)

    keys = {}
    for r in working:
        received = np.flatnonzero(valid[r])
        keys[int(r)] = (round(float(xy[r, 0]), 3), round(float(xy[r, 1]), 3),
                       tuple((int(i + 1), round(float(rss[r, i]), 3)) for i in received))
    maps = {}
    for name, info in registry["maps"].items():
        path = ROOT / info["path"]
        assert sha(path) == info["sha256"]
        if name == "official32_minus71":
            assert sha(path) == OFFICIAL_SHA
        elif name == "recovered29_sensitivity":
            assert sha(path) == RECOVERED_SHA
        original = json.loads(path.read_text())
        coords = np.full((72, 2), np.nan)
        for rx, position in original.items():
            coords[int(rx) - 1] = position
        maps[name] = np.asarray(sorted(map(int, original))), coords

    population_cache = {}
    records = []
    maximum_fit_difference = 0.
    reconstructed_fit_count = 0
    for block_info in registry["blocks"]:
        block_path = ROOT / block_info["path"]
        metadata = json.loads((ROOT / block_info["metadata_path"]).read_text())
        assert sha(block_path) == block_info["sha256"]
        assert sha(ROOT / block_info["metadata_path"]) == block_info["metadata_sha256"]
        b = unpack(block_path)
        mapped, base_coordinates = maps[block_info["map"]]
        if block_info["study"] == "study1":
            expected_train, expected_test = original_train, original_test
            sample_size = 512
        else:
            fold = block_info["fold"]
            east, north = fold[1] == "E", fold[0] == "N"
            points = xy[working]
            in_x = points[:, 0] >= midpoint[0]
            in_y = points[:, 1] >= midpoint[1]
            test_mask = (in_x if east else ~in_x) & (in_y if north else ~in_y)
            # Distance to the corresponding closed quadrant, independently
            # obtained as projection onto its Cartesian product of half-lines.
            projected = points.copy()
            projected[:, 0] = (np.maximum(points[:, 0], midpoint[0]) if east else
                               np.minimum(points[:, 0], midpoint[0]))
            projected[:, 1] = (np.maximum(points[:, 1], midpoint[1]) if north else
                               np.minimum(points[:, 1], midpoint[1]))
            distances = np.linalg.norm(points - projected, axis=1)
            expected_train = working[(~test_mask) & (distances > 250.)]
            expected_test = working[test_mask]
            sample_size = 500
        population_name = metadata["population_path"]
        if population_name not in population_cache:
            p = unpack(ROOT / population_name)
            equal(p["training_source_rows"], expected_train)
            equal(p["test_source_rows"], expected_test)
            assert not np.intersect1d(expected_train, expected_test).size
            support = valid[expected_train].sum(axis=0)
            roster = mapped[support[mapped - 1] >= 10]
            equal(p["training_reception_support"], support)
            equal(p["roster_ids"], roster)
            initial = expected_test[valid[expected_test][:, roster - 1].sum(axis=1) >= 3]
            train_keys = set(keys[int(r)] for r in expected_train)
            overlap = np.asarray([keys[int(r)] in train_keys for r in initial])
            eligible = rank_query(initial[~overlap])
            equal(p["eligible_before_duplicate_filter_source_rows"], initial)
            equal(p["excluded_train_content_overlap_source_rows"], initial[overlap])
            equal(p["eligible_source_rows"], eligible)
            equal(p["sample_source_rows"], eligible[:sample_size])
            full_selected = np.zeros((len(eligible), 10), dtype=np.int16)
            for q, source in enumerate(eligible):
                heard = [int(g) for g in roster if valid[source, g - 1]]
                chosen = sorted(heard, key=lambda g: (-rss[source, g - 1], g))[:10]
                full_selected[q, :len(chosen)] = chosen
            equal(p["eligible_selected_ids"], full_selected)
            population_cache[population_name] = (p, roster, full_selected[:sample_size])
        p, roster, selected = population_cache[population_name]
        equal(b["source_rows"], p["sample_source_rows"])
        equal(b["query_xy_m"], xy[b["source_rows"]])
        equal(b["calibration_population_source_rows"], expected_train)
        equal(b["receiver_ids"], np.arange(1, 73))
        equal(b["selected_ids"], selected)
        equal(b["selected_mask"], selected > 0)
        equal(b["roster_mask"], np.isin(np.arange(1, 73), roster))
        equal(b["reference_anchors_m"], base_coordinates)
        for q, source in enumerate(b["source_rows"]):
            mask = selected[q] > 0
            equal(b["query_rssi_dbm"][q, mask], rss[source, selected[q, mask] - 1])
            assert np.count_nonzero(mask) >= 3
            assert not np.isin(source, expected_train)
            assert not np.any(b["query_rssi_dbm"][q, ~mask])

        equal(b["cal_receiver_ids"], roster)
        assert len(b["cal_offsets"]) == len(roster) + 1
        assert b["cal_offsets"][0] == 0 and b["cal_offsets"][-1] == len(b["cal_source_rows_flat"])
        expected_counts = []
        calibration = {}
        for gi, receiver in enumerate(roster):
            expected_rows = expected_train[valid[expected_train, receiver - 1]]
            if block_info["budget"] == 10:
                rep = block_info["replicate"]
                expected_rows = np.asarray(sorted(map(int, expected_rows), key=lambda r: (
                    hashlib.sha256(f"paperb_broader_validation_v1:cal:{rep}:{receiver}:{r}".encode()).hexdigest(), r))[:10])
            start, stop = b["cal_offsets"][gi:gi + 2]
            equal(b["cal_source_rows_flat"][start:stop], expected_rows)
            equal(b["cal_rssi_flat"][start:stop], rss[expected_rows, receiver - 1])
            equal(b["cal_xy_m_flat"][start:stop], xy[expected_rows])
            calibration[int(receiver)] = expected_rows
            expected_counts.append(len(expected_rows))
        flat_rows = np.concatenate(list(calibration.values()))
        equal(b["cal_unique_source_rows"], np.unique(flat_rows))
        assert metadata["calibration_cost"]["total_receiver_receptions"] == len(flat_rows)
        assert metadata["calibration_cost"]["distinct_labeled_source_rows"] == len(np.unique(flat_rows))

        expected_fields = [(0., -1, [])]
        if block_info["study"] == "study1":
            target_sets, magnitudes = ([14], [14, 69]), (100., 1000., 5000.)
        else:
            target_sets, magnitudes = ([14, 69],), (1000., 5000.)
        for targets in target_sets:
            for distance in magnitudes:
                for draw in range(4):
                    expected_fields.append((distance, draw, targets))
        assert len(b["field_D_m"]) == len(expected_fields)
        for fi, (distance, draw, targets) in enumerate(expected_fields):
            assert b["field_D_m"][fi] == distance and b["field_draw"][fi] == draw
            assert b["field_target_count"][fi] == len(targets)
            expected_coordinates = base_coordinates.copy()
            for receiver in targets:
                rng = np.random.default_rng(np.random.SeedSequence([20261007, 2, draw, receiver]))
                theta = rng.uniform(0., 2. * np.pi)
                expected_coordinates[receiver - 1] += distance * np.array([np.cos(theta), np.sin(theta)])
            equal(b["field_anchors_m"][fi], expected_coordinates)
            equal(b["field_target_mask"][fi], np.isin(np.arange(1, 73), targets))
            for receiver, rows in calibration.items():
                distances = np.linalg.norm(xy[rows] - expected_coordinates[receiver - 1], axis=1)
                expected_intercept = np.median(rss[rows, receiver - 1] + 47. * np.log10(1. + distances))
                difference = abs(b["field_refit_intercepts_dbm"][fi, receiver - 1] - expected_intercept)
                assert difference < 1e-10
                maximum_fit_difference = max(maximum_fit_difference, float(difference))
                reconstructed_fit_count += 1
            assert np.isnan(b["field_refit_intercepts_dbm"][fi, ~b["roster_mask"]]).all()
        equal(b["reference_intercepts_dbm"], b["field_refit_intercepts_dbm"][0])
        records.append({"block": block_info["block_id"], "query_count": len(b["source_rows"]),
                        "receiver_count": len(roster), "field_count": len(expected_fields),
                        "calibration_receptions": len(flat_rows), "distinct_calibration_source_rows": len(np.unique(flat_rows)),
                        "input_sha256": sha(block_path)})

    assert len(records) == 18 and len(population_cache) == 6
    # Hash the final inputs again to reject concurrent modifications during this audit.
    for name, digest in manifest.items():
        assert sha(ROOT / name) == digest
    output = {
        "status": "PASS", "scope": "Independent reconstruction of prepared inputs, not localization performance",
        "scientific_localization_comparisons_run": False,
        "source_sha256": sha(ROOT / "src/prepare_studies.py"),
        "test_sha256": sha(Path(__file__)), "raw_sha256": sha(raw),
        "registry_sha256": sha(registry_path), "manifest_sha256": sha(manifest_path),
        "verified_blocks": len(records), "verified_full_populations": len(population_cache),
        "independently_recomputed_receiver_field_intercepts": reconstructed_fit_count,
        "maximum_intercept_discrepancy_db": maximum_fit_difference,
        "verified": ["raw_source_row_identity_and_RSSI", "original_random_split",
                     "spatial_splits_and_250m_buffer", "training_reception_support_and_fixed_rosters",
                     "train_content_duplicate_exclusion", "hash_cohorts_and_full_eligible_population",
                     "raw_RSSI_top10_selection_and_numeric_ties", "same_query_slots_all_budgets_and_policies",
                     "each_per_receiver_calibration_source_record", "each_reference_and_perturbed_median_intercept",
                     "direction_seed_coupling", "unchanged_nontarget_coordinates_and_intercepts",
                     "calibration_reception_vs_labeled_message_costs", "file_manifest_unchanged_during_audit"],
        "map_provenance": registry["maps"],
        "map_recovery_receipt_sha256": sha(ROOT / "receipts/MAP_RECOVERY.json"),
        "provenance_scope": "Official map hash independently matches the prior verified catalogue artifact. R29 hash independently matches the protected-v1.1.0 archive member recorded in MAP_RECOVERY.json; neither check establishes physical coordinate accuracy.",
        "interpretation_limits": ["Geographic splitting uses positions for benchmark construction; it does not establish independent deployments.",
                                  "R29 is a supplied sensitivity map, not independently surveyed physical receiver truth.",
                                  "No prediction, localization error, favorable-result selection, or performance inference was executed."],
        "blocks": records, "elapsed_seconds": time.monotonic() - clock}
    destination = ROOT / "receipts/INPUT_REVIEW.json"
    destination.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k not in ("blocks", "map_provenance")}, indent=2))


if __name__ == "__main__":
    main()
