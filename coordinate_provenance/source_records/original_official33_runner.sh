#!/usr/bin/env bash
set -euo pipefail

# Paper B B9C: official-33 / common-roster robustness core.
# This script does not edit the B9B manuscript or any source artifact.
# It writes only under PAPERB_B9C_OFFICIAL33_CORE_050926.

ROOT="${ROOT:-/Users/anik/TriMesh/DeltaMesh All Files}"
SRC="$ROOT/PAPERB_STAGE_B5_040926/scripts"
BATCH="$ROOT/PAPERB_B9C_INPUT_BATCH_20260905_055353/copied"
RUN="$ROOT/PAPERB_B9C_OFFICIAL33_CORE_050926"
INPUTS="$RUN/inputs"
RESULTS="$RUN/results"
mkdir -p "$INPUTS" "$RESULTS"

HARNESS="$SRC/baseline_001_e123_pairfallback_040926.py"
EVALUATOR="$SRC/deltamesh_antwerp_eval_v10_fixed_080826.py"
DATA="$SRC/lorawan_antwerp_2019_dataset.csv"
GWLOCS="$SRC/lorawan_antwerp_gateway_locations.json"
R29_SRC="$BATCH/bs_to_utm_extended.json"
O33R_SRC="$BATCH/bs_to_utm_repaired33.json"

fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
check_file() { [[ -f "$1" ]] || fail "Missing required file: $1"; }
check_hash() {
  local p="$1" expected="$2" actual
  check_file "$p"
  actual="$(sha256 "$p")"
  [[ "$actual" == "$expected" ]] || fail "SHA-256 mismatch: $p\nexpected=$expected\nactual=$actual"
  printf 'PASS  %s  %s\n' "$actual" "$p"
}

printf '\n=== B9C INPUT IDENTITY PREFLIGHT ===\n'
check_hash "$HARNESS"  "6e8881f3a83b70c49ee2b1f3892b9a2cf65e5491717c336b3e1cbace01943b2f"
check_hash "$EVALUATOR" "b14b35b5748e447971e5b22da7c39ededc8277aa04e5690eeff672bf1311cac5"
check_hash "$DATA"      "870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446"
check_hash "$GWLOCS"    "507f9bb266d23f59fdc2b743447cecf9c909290536e24de3f9483aaa178d374d"
check_hash "$R29_SRC"   "cfddca4fc5a0ad51fb4d8717be807454c891ba3c4872ff1a4e6b9aec3f5ae2da"
check_hash "$O33R_SRC"  "cae3b93e19ff1df8a9a1182ab4e422707af6647ab3ab4c3c4e67d7bd378199b9"

python3 - <<'PY'
import importlib
for name in ("numpy", "scipy", "pandas", "pyproj"):
    mod = importlib.import_module(name)
    print(f"PASS  import {name} {getattr(mod, '__version__', '')}")
PY

cp -p "$R29_SRC"  "$INPUTS/recovered29.json"
cp -p "$O33R_SRC" "$INPUTS/official33_repaired71.json"

# Build anomaly and assignment-isolation maps deterministically.
python3 - "$INPUTS/recovered29.json" "$INPUTS/official33_repaired71.json" "$INPUTS" <<'PY'
import hashlib, json, math, sys
from pathlib import Path
r_path, o_path, out_dir = map(Path, sys.argv[1:])
r = json.loads(r_path.read_text())
o = json.loads(o_path.read_text())
assert len(r) == 29, len(r)
assert len(o) == 33, len(o)
shared = sorted(set(r) & set(o), key=lambda x: int(x))
assert len(shared) == 27, (len(shared), shared)
assert "71" in shared
maps = {
    "official32_minus71.json": {k: v for k, v in o.items() if k != "71"},
    "official27_common.json": {k: o[k] for k in shared},
    "recovered27_common.json": {k: r[k] for k in shared},
    "official26_common_minus71.json": {k: o[k] for k in shared if k != "71"},
    "recovered26_common_minus71.json": {k: r[k] for k in shared if k != "71"},
}
for name, obj in maps.items():
    (out_dir / name).write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")
manifest = {
    "recovered29_n": len(r),
    "official33_repaired71_n": len(o),
    "shared_n": len(shared),
    "shared_ids": shared,
    "recovered_only": sorted(set(r)-set(o), key=int),
    "official_only": sorted(set(o)-set(r), key=int),
    "generated": {},
}
for name in maps:
    p = out_dir / name
    manifest["generated"][name] = {
        "n": len(json.loads(p.read_text())),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
(out_dir / "B9C_MAP_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
PY

# Search for the uncorrected published official-33 map. It is optional for the
# decisive anomaly-controlled gates, but will be run if uniquely identified.
python3 - "$ROOT" "$RUN" "$INPUTS/official33_repaired71.json" <<'PY'
import hashlib, json, os, shutil, sys
from pathlib import Path
root, run, repaired_path = map(Path, sys.argv[1:])
repaired = json.loads(repaired_path.read_text())
names = {"bs_to_utm_direct.json", "bs_to_utm_coords_direct.json", "bs_to_utm_33.json", "bs_to_utm_official.json"}
valid = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__"} and not d.startswith("PAPERB_B9C_OFFICIAL33_CORE_050926")]
    for fn in filenames:
        if fn not in names:
            continue
        p = Path(dirpath) / fn
        try:
            obj = json.loads(p.read_text())
            if len(obj) != 33 or set(obj) != set(repaired):
                continue
            non71_same = all([float(x) for x in obj[k]] == [float(x) for x in repaired[k]] for k in obj if k != "71")
            d71 = sum((float(obj["71"][i]) - float(repaired["71"][i]))**2 for i in (0,1))**0.5
            if non71_same and d71 > 10000:
                valid.append((p, hashlib.sha256(p.read_bytes()).hexdigest(), d71))
        except Exception:
            pass
report = {"valid_candidates": [{"path": str(p), "sha256": h, "bs71_delta_m": d} for p,h,d in valid]}
(run / "PUBLISHED_OFFICIAL33_SEARCH.json").write_text(json.dumps(report, indent=2) + "\n")
unique_hashes = {h for _,h,_ in valid}
if valid and len(unique_hashes) == 1:
    shutil.copy2(valid[0][0], run / "inputs" / "official33_published.json")
    print(f"PASS  published official-33 identified: {valid[0][0]}")
elif not valid:
    print("NOTE  uncorrected published official-33 not found; decisive O33-R71 and O33-minus-71 arms remain runnable.")
else:
    print("NOTE  multiple non-identical published official-33 candidates; not selected. See PUBLISHED_OFFICIAL33_SEARCH.json.")
PY

cat > "$RUN/RUN_ENVIRONMENT.txt" <<EOF
run_created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
root=$ROOT
python=$(python3 --version 2>&1)
harness=$HARNESS
harness_sha256=$(sha256 "$HARNESS")
evaluator=$EVALUATOR
evaluator_sha256=$(sha256 "$EVALUATOR")
data=$DATA
data_sha256=$(sha256 "$DATA")
gateway_locations=$GWLOCS
gateway_locations_sha256=$(sha256 "$GWLOCS")
scientific_authority_entering_stage=B9B
protocol=PAPERB-B9C-PREREGISTERED-PROTOCOL-001_050926.md
EOF

if [[ "${B9C_PREFLIGHT_ONLY:-0}" == "1" ]]; then
  printf '\nPREFLIGHT COMPLETE. No scientific run was started.\nPrepared inputs: %s\n' "$INPUTS"
  exit 0
fi

run_one() {
  local name="$1" map="$2" n="$3" disp="$4" maxg="$5" expose_k="$6" expose_dirs="$7" spatial="$8"
  local prefix="$RESULTS/$name"
  local done="$prefix.DONE"
  if [[ -f "$done" ]]; then
    printf '\nSKIP  %s (DONE marker exists)\n' "$name"
    return 0
  fi
  local cmd=(
    python3 "$HARNESS"
    --data "$DATA"
    --map "$map"
    --gw-locs "$GWLOCS"
    --blocks 0,1,21
    --samples 2500
    --floor-reps 40
    --corrupt-draws 8
    --corrupt-disp "$disp"
    --max-gws "$maxg"
    --assumed-n "$n"
    --seed 1
    --full-spread 1
    --out "$prefix"
  )
  if [[ "$expose_k" -gt 0 ]]; then
    cmd+=(--expose-k-max "$expose_k" --expose-dir-draws "$expose_dirs")
  fi
  if [[ "$spatial" == "1" ]]; then
    cmd+=(--affine 1 --dir-family 1 --dir-angles 12)
  fi
  printf '%q ' "${cmd[@]}" > "$prefix.command.sh"
  printf '\n' >> "$prefix.command.sh"
  printf '\n===== RUN %s =====\n' "$name"
  printf 'map=%s | n=%s | D=%s | max_gws=%s | expose_k=%s | expose_dirs=%s | spatial=%s\n' \
    "$map" "$n" "$disp" "$maxg" "$expose_k" "$expose_dirs" "$spatial"
  set +e
  PYTHONUNBUFFERED=1 "${cmd[@]}" 2>&1 | tee "$prefix.console.log"
  local rc=${PIPESTATUS[0]}
  set -e
  printf '%s\n' "$rc" > "$prefix.returncode.txt"
  [[ "$rc" -eq 0 ]] || fail "Run failed: $name (return code $rc). Prior completed runs are preserved."
  [[ -s "$prefix.txt" ]] || fail "Run returned zero but did not create $prefix.txt"
  touch "$done"
}

O33R="$INPUTS/official33_repaired71.json"
O32="$INPUTS/official32_minus71.json"
O27="$INPUTS/official27_common.json"
R27="$INPUTS/recovered27_common.json"
O26="$INPUTS/official26_common_minus71.json"
R26="$INPUTS/recovered26_common_minus71.json"

# Primary anomaly-controlled native official substrate: O33 minus BS 71.
run_one "O32M71_N4P7_D1000_W10"  "$O32" 4.7 1000  10 8  4 0
run_one "O32M71_N4P7_D5000_W10"  "$O32" 4.7 5000  10 14 8 1
run_one "O32M71_N4P7_D10000_W10" "$O32" 4.7 10000 10 0  1 0
run_one "O32M71_N4P7_D5000_W5"   "$O32" 4.7 5000  5  8  4 0

# Same official roster with BS 71 repaired rather than excluded.
run_one "O33R71_N4P7_D1000_W10"  "$O33R" 4.7 1000  10 8  4 0
run_one "O33R71_N4P7_D5000_W10"  "$O33R" 4.7 5000  10 14 8 0
run_one "O33R71_N4P7_D10000_W10" "$O33R" 4.7 10000 10 0  1 0
run_one "O33R71_N4P7_D5000_W5"   "$O33R" 4.7 5000  5  8  4 0

# Pure coordinate-assignment isolation on the identical common-27 roster.
run_one "O27_N4P7_D1000_W10"  "$O27" 4.7 1000  10 8  4 0
run_one "O27_N4P7_D5000_W10"  "$O27" 4.7 5000  10 14 8 0
run_one "O27_N4P7_D10000_W10" "$O27" 4.7 10000 10 0  1 0
run_one "R27_N4P7_D1000_W10"  "$R27" 4.7 1000  10 8  4 0
run_one "R27_N4P7_D5000_W10"  "$R27" 4.7 5000  10 14 8 0
run_one "R27_N4P7_D10000_W10" "$R27" 4.7 10000 10 0  1 0

# BS-71-free assignment isolation at the load-bearing 5-km transition.
run_one "O26M71_N4P7_D5000_W10" "$O26" 4.7 5000 10 8 8 0
run_one "R26M71_N4P7_D5000_W10" "$R26" 4.7 5000 10 8 8 0

# Optional raw published official-33 arms, only when uniquely reconstructed.
if [[ -f "$INPUTS/official33_published.json" ]]; then
  run_one "O33PUBLISHED_N4P7_D5000_W10"  "$INPUTS/official33_published.json" 4.7 5000  10 14 8 0
  run_one "O33PUBLISHED_N4P7_D10000_W10" "$INPUTS/official33_published.json" 4.7 10000 10 0  1 0
fi

printf '\n=== FINAL HASH MANIFEST ===\n'
(
  cd "$RUN"
  find . -type f ! -name 'SHA256SUMS.txt' -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS.txt
)

ZIP="$ROOT/PAPERB_B9C_OFFICIAL33_CORE_050926.zip"
rm -f "$ZIP"
(
  cd "$ROOT"
  zip -qry "$ZIP" "$(basename "$RUN")"
)
printf '\nCOMPLETE\nFolder: %s\nZIP:    %s\nSHA256: %s\n' "$RUN" "$ZIP" "$(sha256 "$ZIP")"
