# Changelog

## 2.2 maintenance update
- Fixed `delete_reviewed.py` for Python 3.6 (`universal_newlines=True`).
- Removed use of `Path.unlink(missing_ok=True)` for Python 3.6 compatibility.
- If `--evidence-dir` already exists, a unique `-01`, `-02`, ... directory is created automatically.
- Existing evidence directories are never overwritten or deleted.


## 2.2
- Added explicit RAW_BLOB_CORRUPT detection for headerless binary blobs.
- Added raw binary/NUL metrics, parser defects, missing-header fields, first-byte hex.
- Added transparent gzip blob parsing to avoid false corruption flags.
- Added scan_stats.json with exact scanned-file count.
- Fixed single-mailbox broken-log reporting: scoped to mailbox ID and deduplicated.
- Added broken_blob_results.csv with unique NO_SUCH_BLOB items.

## 2.1
- Added `--account EMAIL` for single-mailbox scans.
- Single-account mailbox map generation.
- Optional IOC search can target the same single account.
- Output metadata records account scope and mailbox ID.

## 2.0
- Streaming NUL-safe file-path scanner.
- CSV and TSV reports.
- Human review CSV.
- Dry-run-first removal workflow.
- Current mailbox-ID validation.
- Evidence copy/export before removal.
- SHA-256 for candidates/evidence.
- Multiple store/HSM path support.
- Optional known-IOC mailbox phase.
- Broken-mail log scan.
- Integrity manifest.
