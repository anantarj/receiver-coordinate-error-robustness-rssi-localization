# Zenodo v1.1.0 reserved DOI

Reserved DOI: **10.5281/zenodo.23061691**

This DOI is reserved for version 1.1.0 in the existing Zenodo record family. The preceding v1.0.0 DOI is **10.5281/zenodo.22680802** and remains baseline-only.

Do not overwrite v1.0.0. Before publishing the new-version draft:

1. Verify the final v1.1.0 archive with `python3 verify_evidence.py`.
2. Run `python3 scripts/run_release_checks.py --out /new/external/output`.
3. Confirm the GitHub `v1.1.0` tag points to the approved commit and the release asset is the exact verified archive.
4. Upload that same archive to this Zenodo draft.
5. Confirm title, version, creators, DOI, repository link, license description and checksum.
6. Publish the Zenodo draft only after the GitHub release and archive checksum are final.

DOI reservation is not publication; the DOI may not resolve until the draft is published.
