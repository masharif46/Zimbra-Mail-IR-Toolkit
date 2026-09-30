# Zimbra Mail IR Toolkit v2.2

[![GitHub repository](https://img.shields.io/badge/GitHub-masharif46%2FZimbra--Mail--IR--Toolkit-181717?logo=github)](https://github.com/masharif46/Zimbra-Mail-IR-Toolkit)

Repository: <https://github.com/masharif46/Zimbra-Mail-IR-Toolkit>

A conservative incident-response toolkit for finding, reviewing, preserving, and
removing suspicious/broken Zimbra messages, including messages that render as
binary garbage such as `����...`.

## Professional workflow

1. **Discover** with read-only scans.
2. **Review** candidates in an Excel-friendly CSV.
3. **Preserve evidence** for messages approved for removal.
4. **Remove** only rows explicitly marked `DELETE`, using Zimbra CLI.

A detection hit is **not proof of malware**.

## Usage and risk notice

Use this toolkit only on Zimbra systems that you own or are explicitly
authorized to investigate. You are responsible for confirming the scope,
permissions, backups, change approvals, and legal requirements that apply to
your environment before running it.

This software is provided **as is**, without guarantees that scans will be
complete, accurate, or suitable for a particular environment. Running it may
consume substantial disk I/O, CPU, memory, and mailbox/CLI resources, which can
affect a live Zimbra server. Results may include false positives or false
negatives.

The deletion workflow can permanently remove messages. Always review the CSV,
preserve required evidence, verify backups, perform a dry run, and obtain the
necessary approval before using `--execute`. Do not use the toolkit as a
substitute for a complete host-level incident-response process.

By using this toolkit, you accept responsibility for validating commands and
results and for any loss, interruption, corruption, or other damage arising
from its use. The project author and contributors are not responsible for any
damage, data loss, service interruption, security incident, or other consequence
resulting from the use or misuse of this toolkit, to the extent permitted by
applicable law.

## Safety

The normal scan does not delete mail, update MariaDB/MySQL, modify LDAP, modify
Zimbra configuration, or write into `/opt/zimbra/store`.

The only mailbox-changing tool is:

```bash
bin/delete_reviewed.py
```

It is dry-run by default and requires both:

```text
--execute
--confirm DELETE_REVIEWED_MESSAGES
```

It validates the current mailbox ID before any removal and attempts to preserve
the selected message first.

The main scan risk is server load (disk I/O/CPU), not database damage. Start with
a short date range and use `--delay 0.02` on a busy live server.

## Requirements

- Linux
- Python 3
- Zimbra under `/opt/zimbra`
- `find`, `grep`, `awk`, `sha256sum`
- `ionice` optional
- Run as `zimbra` (preferred) or `root`

## Install

Clone the repository on the Zimbra server, or copy the release archive:

```bash
git clone https://github.com/masharif46/Zimbra-Mail-IR-Toolkit.git
cd Zimbra-Mail-IR-Toolkit
```

For an archive installation:

```bash
unzip zimbra_mail_ir_toolkit_v2.zip
cd zimbra_mail_ir_toolkit_v2
chmod 700 bin/* lib/*
./bin/verify_package.sh
```


## Scan one mailbox only

Version 2.2 supports a single-mailbox scan directly:

```bash
./bin/scan_all.sh \
  --account itlead@example.com \
  --start 2026-08-20 \
  --end 2026-08-29 \
  --delay 0.02
```

For the full history of one mailbox:

```bash
./bin/scan_all.sh \
  --account itlead@example.com \
  --all-time \
  --delay 0.02
```

The output directory name includes the account, and `mailbox_map.tsv` contains
only that mailbox. This is faster and lower-load than scanning every mailbox.

You can also combine a single mailbox with the optional IOC search:

```bash
./bin/scan_all.sh \
  --account itlead@example.com \
  --start 2026-08-20 \
  --end 2026-08-29 \
  --ioc-search
```

## Recommended first run

```bash
./bin/scan_all.sh \
  --start 2026-08-20 \
  --end 2026-08-29 \
  --delay 0.02
```

Default store:

```text
/opt/zimbra/store
```

For HSM/custom mail volumes, add every message-store path:

```bash
./bin/scan_all.sh \
  --start 2026-08-20 \
  --end 2026-08-29 \
  --store /opt/zimbra/store \
  --store /path/to/another/store \
  --delay 0.02
```

A full-history scan is available but can be I/O intensive:

```bash
./bin/scan_all.sh --all-time --delay 0.02
```

## Optional known-IOC search

The normal filesystem/MIME scan is independent of mailbox search. To additionally
search all accounts for configured incident indicators:

```bash
./bin/scan_all.sh \
  --start 2026-08-20 \
  --end 2026-08-29 \
  --ioc-search
```

IOC files:

```text
config/iocs.txt
config/subject_queries.txt
```

The IOC mailbox phase can be expensive on a server with many accounts.

## Output

Each run creates a new directory, for example:

```text
/tmp/zimbra-mail-ir-20260828-221500/
```

Files:

```text
binary_text_results.csv       Excel-friendly binary-looking candidates
binary_text_results.tsv       same data as TSV
parse_errors.csv              messages Python could not parse
parse_errors.tsv
review_candidates.csv         human review/decision file
mailbox_map.tsv               mailbox ID -> account map for this run
broken_mail_log.txt           matching Zimbra mailbox errors
known_ioc_mail.txt            IOC search report, or a "skipped" note
summary.txt
run_metadata.txt
```

### Main CSV fields

```text
status
account
mailbox_id
message_id
replacement_pct
control_pct
nul_pct
text_parts
size_bytes
date
from
subject
path
sha256
```

A typical candidate can look like:

```text
BINARY_TEXT,itlead@example.com,123,14828,77.45,...
```

## How binary-looking detection works

Only MIME parts declared as `text/*` are scored. Normal PDF, ZIP, XLSX, image,
and other non-text MIME attachments are not scored as binary text.

Default thresholds:

- Unicode replacement characters: >= 2%
- control characters: >= 2%
- NUL bytes: >= 0.1%

This targets the type of broken rendering that appears as `����` without simply
flagging every message that has a binary attachment.

## Review process

Copy the generated review CSV before editing:

```bash
cp /tmp/zimbra-mail-ir-*/review_candidates.csv ./reviewed_candidates.csv
```

Open `reviewed_candidates.csv` in Excel. The important columns are:

```text
decision
reviewer
notes
```

Allowed decisions:

```text
REVIEW
KEEP
DELETE
```

The default is `REVIEW`.

Validate after editing:

```bash
./bin/validate_review.py reviewed_candidates.csv
```

## Dry-run removal

```bash
./bin/delete_reviewed.py reviewed_candidates.csv
```

Nothing is changed. The command prints the account/message pairs that have
`decision=DELETE` and verifies their current mailbox IDs.

## Approved removal

After review/change approval:

```bash
./bin/delete_reviewed.py \
  reviewed_candidates.csv \
  --execute \
  --confirm DELETE_REVIEWED_MESSAGES \
  --evidence-dir /root/zimbra-ir/mail-removal-approved
```

For large review files, process messages in batches and show live progress in
the terminal:

```bash
./bin/delete_reviewed.py reviewed_candidates.csv \
  --execute \
  --confirm DELETE_REVIEWED_MESSAGES \
  --evidence-dir /root/zimbra-ir/mail-removal-approved \
  --timeout 120 \
  --batch-size 200
```

```bash
sed -i 's/\r$//' bin/delete_reviewed.py
chmod +x bin/delete_reviewed.py
```

```bash
python3 ./bin/delete_reviewed.py reviewed_candidates.csv \
  --execute \
  --confirm DELETE_REVIEWED_MESSAGES \
  --evidence-dir /opt/Zimbra-Mail-IR-Toolkit/mail-removal-approved \
  --timeout 60 \
  --batch-size 200
```


`--batch-size` defaults to `200`. The tool reports selected-row totals,
validation progress, batch progress, per-message results, and the completed
evidence directory. Mailbox-ID lookups are cached per account to avoid
repeating the same validation command for every message in that mailbox.

For very large files, first test with a small reviewed CSV and confirm the
deletion rate, evidence storage, and `removal_log.csv` output. Batching limits
the amount of work handled in one group, but the complete operation can still
be lengthy because each message is preserved, exported where possible, and
removed through Zimbra CLI commands.

Each Zimbra CLI operation has a 60-second timeout by default. A different
limit can be selected with `--timeout SECONDS`; timed-out operations are
recorded as failures and processing continues with the next approved row:

```bash
./bin/delete_reviewed.py reviewed_candidates.csv \
  --execute --confirm DELETE_REVIEWED_MESSAGES --timeout 120
```

If running as `zimbra`, choose an evidence directory writable by `zimbra`.

Before each removal the tool attempts to preserve:

- the current Zimbra store blob when the CSV path still exists
- SHA-256
- an RFC822 REST export where possible
- message/account metadata
- removal command result

The removal action uses `zmmailbox ... dm MESSAGE_ID`. It does not edit DB rows
or remove files directly from the Zimbra store.

## Critical message-ID rule

Zimbra message IDs are mailbox-local. Therefore:

```text
user1@example.com / message 14828
```

and:

```text
user2@example.com / message 14828
```

are different items. The removal tool always uses both account and message ID
and validates the account's current mailbox ID.

## Never do this

Do not:

- automatically delete all `BINARY_TEXT` candidates
- delete directly from `/opt/zimbra/store`
- manually delete/update Zimbra DB rows
- use conversation deletion when only one message should be removed
- restore copied blobs by manually placing files back in the mail store
- rely on `/tmp` for evidence that must survive reboot/cleanup

## Limitations

- Binary-looking text can be malformed but legitimate.
- The fast date-window scan uses message-blob filesystem modification time, not
  the RFC822 `Date:` field.
- HSM/custom message volumes outside `/opt/zimbra/store` must be specified.
- This toolkit does not repair missing blobs or database inconsistency.
- This toolkit does not make a compromised host trustworthy and does not replace
  host-level incident response.

## Monitoring live-server impact

In another terminal:

```bash
top
free -h
iostat -xz 5
```

If load is too high, `Ctrl+C` is safe. Partial reports remain available.


## v2.2 raw-blob corruption detection

v2.2 adds an explicit `RAW_BLOB_CORRUPT` flag for Zimbra blobs that resemble the
confirmed example where the stored `.msg` file has:

- no normal RFC822 headers
- `MissingHeaderBodySeparatorDefect`
- strongly binary raw content
- NUL bytes / replacement characters

The detector is intentionally conservative. It requires multiple missing
headers, a structural parser defect, and a high raw-binary or NUL ratio.

The candidate CSV now includes:

```text
flags
raw_binary_pct
raw_nul_pct
missing_header_count
missing_headers
parser_defects
compression
first16_hex
```

Example:

```text
RAW_BLOB_CORRUPT,
RAW_BLOB_CORRUPT|BINARY_TEXT,
itlead@example.com,
600,
14828,
...
```

v2.2 also records the exact number of message blobs actually scanned in
`scan_stats.json` and `summary.txt`.

### Single-mailbox broken-log fix

When `--account` is used, the `NO_SUCH_BLOB` report is now filtered to that
mailbox ID and deduplicated by mailbox/item/change. Therefore a server-wide
mailbox.log history is no longer reported as if it belonged to one account.

Files:

```text
broken_blob_results.csv
broken_mail_log.txt
```

### Date range note

`--start` / `--end` select files using the `.msg` blob filesystem mtime. For
maximum coverage of a mailbox when investigating corruption, use:

```bash
./bin/scan_all.sh --account user@example.com --all-time --delay 0.02
```

## Troubleshooting

### Reusing an existing `--evidence-dir`

The updated v2.2 deletion script never overwrites an existing evidence directory.
If the path supplied with `--evidence-dir` already exists, the script automatically
selects a new sibling directory:

```text
removal-20260828-181852
removal-20260828-181852-01
removal-20260828-181852-02
```

This means a second execute run can safely reuse the same shell `$EVIDENCE` value.
The previous evidence directory is preserved and a new directory is created for the
new run.

The deletion script is also compatible with Python 3.6.x used by older RHEL7/Zimbra
9 hosts. It uses `universal_newlines=True` instead of `text=True` and does not use
`Path.unlink(missing_ok=True)`.
