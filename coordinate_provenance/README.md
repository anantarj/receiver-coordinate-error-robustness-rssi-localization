# Coordinate-input evidence — RC7

This package contains the exact inputs used by the perturbation study and the minimum source evidence needed to inspect them. Main reference 15 credits Ananta Ranjan's **unsubmitted R5.1 resource audit**; its headline 7.54-fold result is not evidence for, or a new contribution of, this manuscript.

## Read first

- `MAP_PARENT_REGISTER.json` fixes eight map parents, bytes, membership and populations. **O27 is the common subset of the substituted-BS71 map, not the wholly unrepaired catalogue map.** Both 27-arms retain BS71 at the R29 position.
- `used_receiver_crosswalk.csv` identifies the 35 consumed receivers, including explicit lack of catalogue coordinates for BS35/BS41. The input derivative excludes the audit's new RSSFIT results and primary selection counts.
- `SOURCE_MANIFEST.json` identifies the author-created source members copied unchanged from the R5.1 archive; `DERIVATION_RECORD.json` identifies the crosswalk extraction.
- `INPUT_CONTINUITY_CHECKS.json` records 35 identity checks, 33 catalogue pairs, frozen parent-map equality and the actual scope. `BS71_INPUT_CHECK.json` and the per-row CSV document CSV-only remoteness/selection checks.
- `sources/rebuild_join.py` is the credited unchanged CSV/JSON producer; `source_records/` preserves its existing execution records. `EXTERNAL_INPUTS.json` identifies the required public payloads by hash.

## Verification and reproduction are different

Run from the evidence root:

```bash
python scripts/verify_coordinate_provenance.py --out ../coordinate_verify
python scripts/verify_coordinate_provenance.py --rebuild --csv /path/source.csv --json /path/source.json --catalogue /path/gateway_locations.json --out ../coordinate_rebuild
```

Every output directory must be new and outside this package. The first route verifies saved evidence, map algebra and population pairing; it does not rerun the raw join or localization. The second replays the source identity join and compares projections to the unchanged analysis maps. It accepts plain or single-payload ZIP inputs and rejects different bytes. It does not select a different roster or overwrite package files. The raw JSON was unavailable in the revision runtime; the fresh join was **not** rerun here. Supplied saved producer records and actual performed input checks are distinguished.

## Historical R29 boundary

R29 is a frozen historical correlation-selected assignment with a retained rank audit. The original 27-core generator/selection population is unavailable. A later consistency audit, a map checksum, or finding a coordinate in a catalogue does not reconstruct those decisions or establish surveyed truth. The perturbation experiments are reproducible **conditional on the frozen map**. No script here claims to recreate its complete historical selection.

## BS71 boundary

The catalogue entry is remote relative to recorded traffic. The observed distances do not prove a typo, relocation, impossible reception, physical error, or the original flagging rationale. Existing catalogue/substituted/excluded configurations and numerical outcomes stay fixed. BS10's rank migration is a different phenomenon.

## Attribution and licensing

Copied producer code is attributed to Ananta Ranjan with source archive/member hashes. Project code follows the approved MIT plan; author-created documentation and derived records use CC BY 4.0. Public source observations/catalogue are obtained separately under their original terms. This small used-input account does not claim the full benchmark resource as new, or certify any companion's journal status.
