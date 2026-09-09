# Zenodo DOI insertion step

Do not create a fictitious DOI.

After creating the Zenodo draft and reserving its DOI, update these two files **before** creating GitHub release `v1.0.0`:

1. `README.md`
   - replace the line `Zenodo DOI: to be inserted ...` with the actual DOI and preferably a DOI link.
2. `CITATION.cff`
   - add:

```yaml
doi: "10.5281/zenodo.XXXXXXXX"
```

Optionally add a `url:` field for the specific Zenodo record.

Commit and push those metadata changes. Only after that commit is on `main` should the `v1.0.0` tag/release be created.
