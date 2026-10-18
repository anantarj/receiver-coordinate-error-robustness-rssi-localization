#!/usr/bin/env python3
"""Prepare outcome-free, reconstructable inputs for Paper B's two studies.

Fits permitted calibration parameters only. No localization estimator is called,
no evaluation error is computed, and no execution lock is created by this script.
"""
from __future__ import annotations
import argparse, collections, hashlib, io, json, os, platform, random, sys, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = ROOT.parent / 'paperb_development_20261015'
sys.path.insert(0, str(DEVELOPMENT / 'private/audit_dependencies'))
from pyproj import Transformer, __version__ as pyproj_version

CSV_SHA = '870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446'
OFFICIAL_MAP_SHA = '487b4853a364921c36c624485be4831f96d2c4db8bd2082529bc9136fb58172f'
QUERY_NAMESPACE = 'paperb_broader_validation_v1:query:'
CAL_NAMESPACE = 'paperb_broader_validation_v1:cal:'
EXPECTED_SPATIAL = {'SW': (42179, 2683, 10513, 10447, 32),
                    'SE': (35478, 2723, 17174, 17142, 32),
                    'NW': (35290, 2911, 17174, 17092, 30),
                    'NE': (40336, 4525, 10514, 10514, 32)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def js(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def npz(path, **arrays):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+f'.{os.getpid()}.tmp')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for key in sorted(arrays):
            value = np.asarray(arrays[key]); assert value.dtype.kind != 'O'
            stream = io.BytesIO(); np.lib.format.write_array(stream, value, allow_pickle=False)
            info = zipfile.ZipInfo(key + '.npy', (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, stream.getvalue())
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None, 'Failed input archive CRC check.'
    temporary.replace(path)


def rowhash(row):
    return hashlib.sha256(f'{QUERY_NAMESPACE}{int(row)}'.encode()).hexdigest()


def ordered(rows):
    return np.asarray(sorted(map(int, rows), key=lambda row: (rowhash(row), row)), dtype=np.int64)


def content_key(row, xy, rss, valid):
    return (round(float(xy[row, 0]), 3), round(float(xy[row, 1]), 3),
            tuple((int(j+1), round(float(rss[row, j]), 3)) for j in np.flatnonzero(valid[row])))


def selected_slots(rows, roster, rss, valid):
    ids = np.zeros((len(rows), 10), dtype=np.int16)
    values = np.zeros((len(rows), 10), dtype=float)
    for qi, row in enumerate(rows):
        heard = [int(g) for g in roster if valid[row, g-1]]
        heard.sort(key=lambda g: (-float(rss[row, g-1]), g))
        heard = heard[:10]; assert len(heard) >= 3
        ids[qi, :len(heard)] = heard
        values[qi, :len(heard)] = rss[row, np.asarray(heard)-1]
    return ids, values


def exposure(ids):
    return {','.join(map(str, targets)): {
        str(k): int((np.isin(ids, targets).sum(axis=1) == k).sum())
        for k in range(len(targets)+1)} for targets in ([14], [14, 69])}


def duplicate_summary(rows, keys):
    counts = collections.Counter(keys[int(r)] for r in rows)
    return {'unique_content_groups': len(counts),
            'duplicate_content_groups': sum(n > 1 for n in counts.values()),
            'duplicate_extra_rows': sum(n-1 for n in counts.values())}


def load_map(path, expected_n):
    record = json.loads(path.read_text()); ids = np.asarray(sorted(map(int, record)), dtype=int)
    assert len(ids) == expected_n and len(set(ids)) == expected_n
    assert np.all((ids >= 1) & (ids <= 72)) and {14, 69}.issubset(ids)
    anchors = np.full((72, 2), np.nan)
    for g in ids:
        xy = np.asarray(record[str(g)], dtype=float)
        assert xy.shape == (2,) and np.isfinite(xy).all()
        anchors[g-1] = xy
    return ids, anchors


def fields(study):
    result = [{'field_index': 0, 'D_m': 0., 'draw': -1, 'target_ids': []}]
    targets = ([14], [14, 69]) if study == 'study1' else ([14, 69],)
    magnitudes = (100., 1000., 5000.) if study == 'study1' else (1000., 5000.)
    for target in targets:
        for distance in magnitudes:
            for draw in range(4):
                result.append({'field_index': len(result), 'D_m': distance, 'draw': draw, 'target_ids': target})
    return result


def direction(draw, receiver):
    theta = float(np.random.default_rng(np.random.SeedSequence([20261007, 2, draw, receiver])).uniform(0, 2*np.pi))
    return np.array([np.cos(theta), np.sin(theta)])


def cal_rows(training, roster, valid, budget, replicate):
    result = {}
    for g in roster:
        rows = np.asarray(training[valid[training, g-1]], dtype=np.int64)
        assert len(rows) >= 10
        if budget == 10:
            rows = np.asarray(sorted(map(int, rows), key=lambda row: (
                hashlib.sha256(f'{CAL_NAMESPACE}{replicate}:{int(g)}:{row}'.encode()).hexdigest(), row))[:10], dtype=np.int64)
            assert len(rows) == 10 and len(np.unique(rows)) == 10
        result[int(g)] = rows
    return result


def fit_intercepts(cal, anchors, xy, rss):
    result = np.full(72, np.nan)
    for g, rows in cal.items():
        dist = np.linalg.norm(xy[rows]-anchors[g-1], axis=1)
        result[g-1] = np.median(rss[rows, g-1] + 47.*np.log10(dist+1.))
    return result


def make_cohort(name, study, map_name, fold, training, test, mapped, xy, rss, valid, keys, sample_n, extra):
    support = valid[training].sum(axis=0)
    roster = mapped[support[mapped-1] >= 10]
    initial = test[valid[test][:, roster-1].sum(axis=1) >= 3]
    train_keys = {keys[int(r)] for r in training}
    overlap = np.array([keys[int(r)] in train_keys for r in initial], bool)
    eligible = ordered(initial[~overlap]); chosen = eligible[:sample_n]
    assert len(chosen) == sample_n and len(set(map(int, training)) & set(map(int, test))) == 0
    assert not any(keys[int(r)] in train_keys for r in chosen)
    full_ids, _ = selected_slots(eligible, roster, rss, valid)
    selected, selected_rss = selected_slots(chosen, roster, rss, valid)
    population = {'working_n': 55375, 'training_n': len(training), 'test_denominator_n': len(test),
                  'eligible_before_duplicate_filter_n': len(initial), 'excluded_train_content_overlap_n': int(overlap.sum()),
                  'eligible_n': len(eligible), 'sample_n': len(chosen), 'fixed_roster_n': len(roster),
                  'full_eligible_duplicate_content': duplicate_summary(eligible, keys),
                  'sample_duplicate_content': duplicate_summary(chosen, keys),
                  'full_eligible_selected_target_exposure': exposure(full_ids),
                  'sample_selected_target_exposure': exposure(selected), **extra}
    path = ROOT/'inputs/populations'/(name+'.npz')
    npz(path, training_source_rows=training, test_source_rows=test,
        eligible_before_duplicate_filter_source_rows=initial,
        excluded_train_content_overlap_source_rows=initial[overlap],
        eligible_source_rows=eligible, sample_source_rows=chosen,
        eligible_selected_ids=full_ids, roster_ids=roster, training_reception_support=support)
    meta = {'identity': {'study': study, 'map': map_name, 'fold': fold}, 'population': population,
            'fixed_roster_receiver_ids': roster.tolist(), 'population_npz_sha256': sha(path)}
    js(path.with_suffix('.json'), meta)
    return dict(name=name, study=study, map_name=map_name, fold=fold, training=training, test=test,
                roster=roster, chosen=chosen, eligible=eligible, selected=selected,
                selected_rss=selected_rss, population=population, population_path=str(path.relative_to(ROOT)))


def make_block(cohort, anchors, xy, rss, valid, budget, replicate, map_sha):
    suffix = 'all' if budget == 'all' else f'b10_r{replicate}'
    name = cohort['name']+'_'+suffix
    roster = cohort['roster']; training = cohort['training']; chosen = cohort['chosen']
    cal = cal_rows(training, roster, valid, budget, replicate)
    reference_fit = fit_intercepts(cal, anchors, xy, rss)
    field_records = fields(cohort['study'])
    field_anchors = np.repeat(anchors[None, :, :], len(field_records), axis=0)
    field_fit = np.repeat(reference_fit[None, :], len(field_records), axis=0)
    targetmask = np.zeros((len(field_records), 72), bool)
    for field in field_records[1:]:
        fi = field['field_index']
        for g in field['target_ids']:
            assert g in cal
            field_anchors[fi, g-1] += field['D_m']*direction(field['draw'], g)
            rows = cal[g]
            distance = np.linalg.norm(xy[rows]-field_anchors[fi, g-1], axis=1)
            field_fit[fi, g-1] = np.median(rss[rows, g-1]+47.*np.log10(distance+1.))
            targetmask[fi, g-1] = True
        unaffected = np.isin(np.arange(1, 73), roster) & ~targetmask[fi]
        assert np.array_equal(field_fit[fi, unaffected], reference_fit[unaffected])
    flat = np.concatenate([cal[int(g)] for g in roster])
    offsets = np.r_[0, np.cumsum([len(cal[int(g)]) for g in roster])]
    flat_rssi = np.concatenate([rss[cal[int(g)], g-1] for g in roster])
    union = np.unique(flat)
    identity = {'study': cohort['study'], 'map': cohort['map_name'], 'fold': cohort['fold'],
                'budget': budget, 'replicate': replicate}
    costs = {'total_receiver_receptions': len(flat), 'distinct_labeled_source_rows': len(union),
             'distinct_reference_coordinate_pairs': len(np.unique(xy[union], axis=0)),
             'receiver_reception_counts': {str(g): len(rows) for g, rows in cal.items()},
             'interpretation': 'Budget10 means10 receptions for each receiver, not10 labeled transmissions overall; source records can support multiple receivers.'}
    path = ROOT/'inputs/blocks'/(name+'.npz')
    npz(path, source_rows=chosen, query_xy_m=xy[chosen], selected_ids=cohort['selected'],
        selected_mask=cohort['selected']>0, query_rssi_dbm=cohort['selected_rss'],
        receiver_ids=np.arange(1, 73), reference_anchors_m=anchors,
        roster_mask=np.isin(np.arange(1, 73), roster), reference_intercepts_dbm=reference_fit,
        field_anchors_m=field_anchors, field_refit_intercepts_dbm=field_fit,
        field_target_mask=targetmask, field_D_m=np.array([f['D_m'] for f in field_records]),
        field_draw=np.array([f['draw'] for f in field_records]),
        field_target_count=np.array([len(f['target_ids']) for f in field_records]),
        cal_receiver_ids=roster, cal_offsets=offsets, cal_source_rows_flat=flat,
        cal_rssi_flat=flat_rssi, cal_xy_m_flat=xy[flat], cal_unique_source_rows=union,
        calibration_population_source_rows=training)
    meta = {'block_id': name, 'identity': identity, 'fields': field_records,
            'population': cohort['population'], 'population_path': cohort['population_path'],
            'calibration_cost': costs, 'map_sha256': map_sha,
            'input_npz_sha256': sha(path), 'field_zero_semantics': 'Unique reference input; frozen/refit coincide exactly.'}
    js(path.with_suffix('.json'), meta)
    return {'block_id': name, 'path': str(path.relative_to(ROOT)), 'sha256': sha(path),
            'metadata_path': str(path.with_suffix('.json').relative_to(ROOT)),
            'metadata_sha256': sha(path.with_suffix('.json')), **identity,
            'query_count': len(chosen), 'field_count': len(field_records)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', type=Path, default=DEVELOPMENT/'inputs/lorawan_antwerp_2019_dataset.csv')
    ap.add_argument('--map-official', type=Path, default=DEVELOPMENT/'inputs/official32_minus71.json')
    ap.add_argument('--map-r29', type=Path, required=True)
    args = ap.parse_args()
    assert not (ROOT/'protocol/EXECUTION_LOCK.json').exists(), 'Inputs must not be rewritten after lock.'
    assert sha(args.csv) == CSV_SHA
    assert sha(args.map_official) == OFFICIAL_MAP_SHA
    frame = pd.read_csv(args.csv)
    rss = frame[[f'BS {i}' for i in range(1, 73)]].to_numpy(float)
    valid = np.isfinite(rss) & (rss >= -150.) & (rss <= -20.)
    lon = frame.Longitude.to_numpy(float); lat = frame.Latitude.to_numpy(float)
    working = np.flatnonzero(np.isfinite(lon) & np.isfinite(lat) & (valid.sum(axis=1) >= 3))
    assert len(working) == 55375
    x, y = Transformer.from_crs('EPSG:4326', 'EPSG:32631', always_xy=True).transform(lon, lat)
    xy = np.column_stack([x, y]); assert np.isfinite(xy[working]).all()
    keys = {int(row): content_key(int(row), xy, rss, valid) for row in working}
    order = working.tolist(); random.Random(1).shuffle(order)
    cal = np.asarray(order[:16612], dtype=np.int64); held = np.asarray(order[16612:], dtype=np.int64)
    maps = {'official32_minus71': (args.map_official, 32), 'recovered29_sensitivity': (args.map_r29, 29)}
    cohorts = []; blocks = []; maps_provenance = {}
    for name, (path, n) in maps.items():
        ids, anchors = load_map(path, n)
        destination = ROOT/'inputs/maps'/(name+'.json'); destination.parent.mkdir(parents=True, exist_ok=True)
        if path.resolve() != destination.resolve(): destination.write_bytes(path.read_bytes())
        maps_provenance[name] = {'path': str(destination.relative_to(ROOT)), 'sha256': sha(destination), 'receiver_ids': ids.tolist()}
        c = make_cohort('study1_'+name, 'study1', name, None, cal, held, ids, xy, rss, valid, keys, 512, {})
        cohorts.append(c); blocks.append(make_block(c, anchors, xy, rss, valid, 'all', None, sha(path)))
        print('Prepared', c['name'], c['population'], flush=True)
    cx, cy = np.median(xy[working], axis=0)
    official_ids, official_anchors = load_map(args.map_official, 32)
    for fold, east, north in [('SW', False, False), ('SE', True, False), ('NW', False, True), ('NE', True, True)]:
        xx, yy = xy[working].T
        istest = ((xx >= cx) if east else (xx < cx)) & ((yy >= cy) if north else (yy < cy))
        dx = np.maximum(cx-xx, 0) if east else np.maximum(xx-cx, 0)
        dy = np.maximum(cy-yy, 0) if north else np.maximum(yy-cy, 0)
        distance = np.hypot(dx, dy); istrain = (~istest) & (distance > 250.)
        training = working[istrain]; test = working[istest]
        extra = {'buffer_excluded_n': int((~istest & ~istrain).sum()),
                 'minimum_training_distance_to_test_quadrant_m': float(distance[istrain].min())}
        c = make_cohort('study2_'+fold, 'study2', 'official32_minus71', fold,
                        training, test, official_ids, xy, rss, valid, keys, 500, extra)
        p = c['population']
        assert (len(training), extra['buffer_excluded_n'], len(test), p['eligible_before_duplicate_filter_n'], len(c['roster'])) == EXPECTED_SPATIAL[fold]
        assert p['excluded_train_content_overlap_n'] == 0
        cohorts.append(c)
        for budget, replicate in [('all', None), (10, 0), (10, 1), (10, 2)]:
            blocks.append(make_block(c, official_anchors, xy, rss, valid, budget, replicate, sha(args.map_official)))
        print('Prepared', c['name'], c['population'], flush=True)
    shared = np.intersect1d(cohorts[0]['chosen'], cohorts[1]['chosen'])
    shared_eligible = np.intersect1d(cohorts[0]['eligible'], cohorts[1]['eligible'])
    npz(ROOT/'inputs/populations/STUDY1_CROSSMAP_INTERSECTION.npz',
        sample_source_rows=ordered(shared), eligible_source_rows=ordered(shared_eligible))
    registry = {'status': 'PREPARED_INPUTS_NOT_EXECUTION_LOCKED',
        'scientific_outcomes_evaluated': False, 'script_sha256': sha(__file__), 'raw_csv_sha256': CSV_SHA,
        'source_row_identity': 'Zero-based original CSV record number excluding header, before any row filtering.',
        'raw_n': len(frame), 'working_n': len(working), 'original_random_calibration_n': len(cal),
        'original_random_split': 'Python random.Random(1).shuffle on working source rows in ascending CSV order; first16612 calibration.',
        'query_order': f'Lexicographic SHA256 UTF8({QUERY_NAMESPACE}<source-row>), numeric source row tie-break. Common acrossmaps/folds.',
        'calibration_permutation': f'Lexicographic SHA256 UTF8({CAL_NAMESPACE}<replicate>:<numeric-receiver-id>:<source-row>), source row tie-break; restrict to foldtraining candidates first.',
        'duplicate_rule': 'Remove all eligible query rows whose full valid-RSSI/UTM content key matches any calibration-population row; UTM positions/RSSI round3decimals. No within-test deduplication.',
        'selection': 'Fixed training-support>=10 roster, validRSSI[-150,-20]inclusive; rawRSSI descending, numericreceiverID tie-break, first10,min3. No perturbation/policy/budget reselection.',
        'fit': 'Per receiver median(RSSI+47log10(distance_m+1)), n4.7,d0=1m; samecalrows atreferenceandperturbedmaps.',
        'direction': 'NumPy default_rng(SeedSequence([20261007,2,draw,numeric_receiver_id])).uniform(0,2pi); unitcos/sin; common across maps,budgets,D,targetsets.',
        'spatial_split': {'center_EPSG32631_m': [float(cx), float(cy)], 'buffer_m': 250.,
                          'definition': 'Four medianquadrants;>=east/north;trainingoutsideclosedheldoutquadrantbyEuclideandistance>250m.',
                          'interpretation': 'Geographic separation; not independent deployment or guaranteed stochastic independence.'},
        'crossmap': {'sample_common_n': len(shared), 'eligible_common_n': len(shared_eligible),
                     'comparison_rule': 'Map-specific samples describe their own populations; matchedcrossmap effects require these exactintersection rows.'},
        'maps': maps_provenance, 'blocks': blocks,
        'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__, 'pyproj': pyproj_version}}
    js(ROOT/'inputs/INPUT_REGISTRY.json', registry)
    manifest = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT/'inputs').rglob('*')) if p.is_file() and p.name != 'INPUT_MANIFEST.json'}
    js(ROOT/'inputs/INPUT_MANIFEST.json', manifest)
    print(json.dumps({'blocks': len(blocks), 'crossmap': registry['crossmap'], 'registry_sha256': sha(ROOT/'inputs/INPUT_REGISTRY.json')}), flush=True)


if __name__ == '__main__':
    main()
