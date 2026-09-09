#!/usr/bin/env python3
"""
sigfox_header_normalise_080826.py
=================================

THE DECLARED PREPROCESSING STEP -- NOT A LOADER CHANGE.

Manuscript Section 5.5, verbatim: the public Sigfox CSVs were used "after a
header-normalization pass that removes quote characters from BS and coordinate
column names; the measurements themselves are unchanged."

That pass exists in the manuscript and NOT in any released script. This is it,
written out so the step is auditable rather than assumed.

WHY THE LOADER REFUSED
----------------------
Every column name arrives quoted:

    'BS 1','BS 2',...,'BS 84','RX Time','Latitude','Longitude'

load_antwerp_csv lowercases and compares against ("lat","latitude","gps_lat",
"gpslat"). The string "'latitude'" matches none of them, so it raises
"Could not find latitude/longitude columns" -- and its error listing truncates
at BS 40, which is why the coordinate columns looked absent when they are simply
last.

WHAT THIS TOUCHES, AND WHAT IT DOES NOT
---------------------------------------
  * HEADER ROW ONLY. Quote characters are stripped from column NAMES.
  * DATA ROWS ARE COPIED BYTE-FOR-BYTE. No value is parsed, coerced, filtered,
    reordered, or rewritten. The -200 sentinels, the RSSI values and the
    coordinates pass through untouched.
  * No column is added, removed or renamed beyond the quote strip.

A receipt is printed: original header, normalised header, the count of names
changed, and the row count before and after. If those row counts differ,
something is wrong and the output must not be used.

DATASET SHAPES OBSERVED (from the header lines)
-----------------------------------------------
  sigfox urban :  84 BS columns + RX Time, Latitude, Longitude
  sigfox rural : 137 BS columns + RX Time, Latitude, Longitude
  sentinel     : -200, same as Antwerp
  no HDOP column in either (Antwerp has one; the loader defaults max_hdop=None)

CAUTION BEFORE READING THE RESULT
---------------------------------
`estimate_gateway_a0_from_known_positions` requires >=10 calibration links PER
GATEWAY. Rural spreads its receptions over 137 gateways and the sample row shows
only 4 non-sentinel values out of 137. Gateway-level A0 coverage may be thin, and
a0_offset_check skips any n with fewer than 5 usable gateways.

If coverage is thin, that is a property of the dataset, not a failure of the
measurement -- report it and say the deployment cannot support the test. Do NOT
lower the >=10 threshold to obtain an answer; that changes the procedure whose
disagreement is the thing being measured.

USAGE
    python3 sigfox_header_normalise_080826.py \
        --in  sigfox_urban_raw.csv --out sigfox_urban_norm.csv
    python3 sigfox_header_normalise_080826.py \
        --in  sigfox_rural_raw.csv --out sigfox_rural_norm.csv

Then, unchanged:
    python3 a0_offset_check_080826.py --data sigfox_urban_norm.csv \
        --label sigfox_urban --out ./a0_offset_sigfox_urban.txt
"""

from __future__ import annotations
import argparse, hashlib, os, sys


def md5(path, n=32):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--quotes", default="\"'",
                    help="characters stripped from column NAMES (default: single and double quote)")
    args = ap.parse_args()

    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        print("REFUSED: --in and --out are the same file. Never normalise in place.")
        return 2

    with open(args.src, "r", encoding="utf-8", errors="replace") as f:
        header = f.readline()
        rest = f.read()

    raw_names = header.rstrip("\r\n").split(",")
    new_names = [c.strip().strip(args.quotes).strip() for c in raw_names]
    changed = sum(1 for a, b in zip(raw_names, new_names) if a != b)

    out_header = ",".join(new_names) + "\n"
    with open(args.dst, "w", encoding="utf-8") as f:
        f.write(out_header)
        f.write(rest)

    n_src = sum(1 for _ in open(args.src, "r", encoding="utf-8", errors="replace"))
    n_dst = sum(1 for _ in open(args.dst, "r", encoding="utf-8", errors="replace"))

    print("=" * 78)
    print("SIGFOX HEADER NORMALISATION -- receipt")
    print("=" * 78)
    print(f"  in   : {args.src}   md5 {md5(args.src)}")
    print(f"  out  : {args.dst}   md5 {md5(args.dst)}")
    print(f"  columns: {len(raw_names)}   names changed: {changed}")
    print(f"  lines  : in {n_src}   out {n_dst}   "
          f"{'OK' if n_src == n_dst else '*** MISMATCH -- DO NOT USE ***'}")
    print()
    print(f"  first 4 in : {raw_names[:4]}")
    print(f"  first 4 out: {new_names[:4]}")
    print(f"  last  4 in : {raw_names[-4:]}")
    print(f"  last  4 out: {new_names[-4:]}")
    bs = [c for c in new_names if c.upper().startswith("BS ")]
    print(f"\n  BS columns detected: {len(bs)}")
    for want in ("Latitude", "Longitude"):
        hit = [c for c in new_names if c.strip().lower() == want.lower()]
        print(f"  '{want}' resolvable by the loader: {bool(hit)}")
    print()
    print("  DATA ROWS ARE UNCHANGED -- only the header line was rewritten.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
