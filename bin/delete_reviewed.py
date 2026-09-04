#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import hashlib
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path

CONFIRM = "DELETE_REVIEWED_MESSAGES"

def command_as_zimbra(program, *args):
    cmd = [f"/opt/zimbra/bin/{program}", *args]
    username = pwd.getpwuid(os.geteuid()).pw_name

    if username == "zimbra":
        return cmd

    if os.geteuid() == 0:
        runuser = shutil.which("runuser")
        if not runuser:
            raise RuntimeError("root execution requires runuser")
        return [runuser, "-u", "zimbra", "--", *cmd]

    raise RuntimeError("run as root or zimbra")

def run_zimbra(program, *args, timeout=60):
    """Run a Zimbra CLI command without allowing it to hang forever."""
    try:
        return subprocess.run(
            command_as_zimbra(program, *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        output = (output + " COMMAND_TIMEOUT").strip()
        return subprocess.CompletedProcess(
            command_as_zimbra(program, *args), 124, output
        )

def get_mailbox_id(account):
    p = run_zimbra("zmprov", "gmi", account)
    if p.returncode != 0:
        return None
    m = re.search(r"(?m)^mailboxId:\s*(\d+)\s*$", p.stdout or "")
    return m.group(1) if m else None

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.@-]+", "_", value)[:180]

def safe_unlink(path):
    """Python 3.6-compatible unlink-if-present."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass

def create_unique_evidence_dir(requested_path, stamp):
    """
    Create a new evidence directory without overwriting an older run.

    If the requested directory already exists, append -01, -02, ... until
    an unused path is found. Existing evidence is never deleted or reused.
    """
    base = Path(
        requested_path
        or "/tmp/zimbra-mail-removal-evidence-{}".format(stamp)
    )

    candidate = base
    counter = 1

    while candidate.exists():
        candidate = Path("{}-{:02d}".format(str(base), counter))
        counter += 1
        if counter > 999:
            raise RuntimeError(
                "cannot allocate a unique evidence directory for {}".format(base)
            )

    candidate.mkdir(parents=True, exist_ok=False)
    os.chmod(str(candidate), 0o700)

    if candidate != base:
        print(
            "\nNOTE: evidence directory already existed; "
            "using a new directory instead:\n  {}".format(candidate)
        )

    return candidate

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("review_csv")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--confirm", default="")
    ap.add_argument("--evidence-dir", default="")
    ap.add_argument(
        "--timeout", type=float, default=60,
        help="maximum seconds per Zimbra command (default: 60)",
    )
    args = ap.parse_args()

    if args.execute and args.confirm != CONFIRM:
        print(f"ERROR: use --confirm {CONFIRM}", file=sys.stderr)
        return 2

    selected = []
    with open(args.review_csv, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        required = {"account", "mailbox_id", "message_id", "decision"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print("ERROR: missing columns: " + ", ".join(sorted(missing)), file=sys.stderr)
            return 2
        for row in reader:
            if row.get("decision", "").strip().upper() == "DELETE":
                selected.append(row)

    if not selected:
        print("No rows marked DELETE.")
        return 0

    print(f"Rows marked DELETE: {len(selected)}")
    validated = []
    problems = []

    for row in selected:
        account = row.get("account", "").strip()
        expected = row.get("mailbox_id", "").strip()
        msgid = row.get("message_id", "").strip()

        if not account or "@" not in account or any(c.isspace() for c in account):
            problems.append(f"{account!r}/{msgid!r}: invalid account")
            continue
        if not expected.isdigit():
            problems.append(f"{account}/{msgid}: invalid CSV mailbox ID")
            continue
        if not msgid.isdigit() or int(msgid) <= 0:
            problems.append(f"{account}/{msgid!r}: invalid message ID")
            continue

        actual = get_mailbox_id(account)
        if actual is None:
            problems.append(f"{account}/{msgid}: cannot obtain current mailbox ID")
            continue
        if actual != expected:
            problems.append(
                f"{account}/{msgid}: mailbox mismatch CSV={expected} current={actual}"
            )
            continue
        validated.append(row)

    if problems:
        print("\nBLOCKED. No mailbox changes were made:")
        for problem in problems:
            print("  " + problem)
        return 1

    print("\nValidated:")
    for row in validated:
        print(
            f"  account={row['account']} message={row['message_id']} "
            f"mailbox={row['mailbox_id']} subject={row.get('subject','')[:80]!r}"
        )

    if not args.execute:
        print("\nDRY RUN ONLY. No messages were changed.")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence = create_unique_evidence_dir(args.evidence_dir, stamp)

    log_fields = [
        "account", "mailbox_id", "message_id", "subject",
        "source_path", "source_sha256", "copied_blob",
        "copied_blob_sha256", "eml_export", "eml_sha256",
        "delete_returncode", "delete_output"
    ]

    with open(evidence / "removal_log.csv", "w", newline="", encoding="utf-8") as lf:
        writer = csv.DictWriter(lf, fieldnames=log_fields)
        writer.writeheader()

        for row in validated:
            account = row["account"].strip()
            msgid = row["message_id"].strip()
            source = row.get("path", "").strip()

            itemdir = evidence / f"{safe_name(account)}__msg_{safe_name(msgid)}"
            itemdir.mkdir(mode=0o700)

            source_sha = row.get("sha256", "").strip()
            copied = ""
            copied_sha = ""

            if source and os.path.isfile(source):
                try:
                    source_sha = sha256_file(source)
                    dest = itemdir / Path(source).name
                    shutil.copy2(source, dest)
                    copied = str(dest)
                    copied_sha = sha256_file(dest)
                except Exception as exc:
                    copied = "COPY_FAILED: " + str(exc)

            eml = itemdir / f"{msgid}.eml"
            eml_sha = ""
            try:
                cmd = command_as_zimbra(
                    "zmmailbox", "-z", "-m", account,
                    "-t", "0", "getRestURL", f"//?id={msgid}"
                )
                with open(eml, "wb") as out:
                    export = subprocess.run(
                        cmd, stdout=out, stderr=subprocess.PIPE, check=False,
                        timeout=args.timeout,
                    )
                if export.returncode == 0 and eml.exists():
                    eml_sha = sha256_file(eml)
                else:
                    safe_unlink(eml)
            except Exception:
                safe_unlink(eml)

            # Mailbox change happens only here, after validation/evidence attempts.
            result = run_zimbra(
                "zmmailbox", "-z", "-m", account, "dm", msgid,
                timeout=args.timeout,
            )

            writer.writerow({
                "account": account,
                "mailbox_id": row["mailbox_id"],
                "message_id": msgid,
                "subject": row.get("subject", ""),
                "source_path": source,
                "source_sha256": source_sha,
                "copied_blob": copied,
                "copied_blob_sha256": copied_sha,
                "eml_export": str(eml) if eml.exists() else "",
                "eml_sha256": eml_sha,
                "delete_returncode": result.returncode,
                "delete_output": (result.stdout or "").replace("\r", " ").replace("\n", " ")[:1000],
            })
            lf.flush()

            if result.returncode == 0:
                print(f"REMOVAL COMMAND OK: {account} message={msgid}")
            else:
                print(f"REMOVAL COMMAND FAILED: {account} message={msgid}")

    print(f"\nEvidence/log directory: {evidence}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
