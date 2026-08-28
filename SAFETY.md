# Safety / Change Control

## Read-only tools

- `scan_all.sh`
- `scan_binary_mail.py`
- `build_mailbox_map.sh`
- `scan_broken_logs.sh`
- `scan_known_iocs.sh`
- `make_review_csv.py`
- `validate_review.py`
- `verify_package.sh`

They write report files only.

## Mailbox-changing tool

Only:

```text
delete_reviewed.py --execute --confirm DELETE_REVIEWED_MESSAGES
```

changes selected mailboxes.

There are no direct SQL UPDATE/DELETE/TRUNCATE statements and no direct
mail-store deletion commands in this toolkit.

## Recommended approval sequence

1. Scan.
2. Preserve the untouched scan directory.
3. Copy `review_candidates.csv`.
4. Review each candidate.
5. Mark only confirmed items `DELETE`.
6. Validate the CSV.
7. Dry-run the deletion tool.
8. Review dry-run output.
9. Select a persistent evidence directory.
10. Execute approved removals.
11. Preserve the reviewed CSV, evidence, and removal log.
