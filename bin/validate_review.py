#!/usr/bin/env python3
import csv
import sys

ALLOWED = {"REVIEW", "KEEP", "DELETE"}

def main():
    if len(sys.argv) != 2:
        print("Usage: validate_review.py reviewed_candidates.csv", file=sys.stderr)
        return 2

    errors = []
    counts = {x: 0 for x in ALLOWED}

    with open(sys.argv[1], newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        required = {"account", "mailbox_id", "message_id", "decision"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print("ERROR: missing columns: " + ", ".join(sorted(missing)), file=sys.stderr)
            return 2

        for line_no, row in enumerate(reader, 2):
            decision = row.get("decision", "").strip().upper()
            account = row.get("account", "").strip()
            mailbox_id = row.get("mailbox_id", "").strip()
            message_id = row.get("message_id", "").strip()

            if decision not in ALLOWED:
                errors.append(f"line {line_no}: invalid decision {decision!r}")
                continue
            counts[decision] += 1

            if decision == "DELETE":
                if not account or "@" not in account or any(c.isspace() for c in account):
                    errors.append(f"line {line_no}: invalid account")
                if not mailbox_id.isdigit():
                    errors.append(f"line {line_no}: invalid mailbox_id")
                if not message_id.isdigit() or int(message_id) <= 0:
                    errors.append(f"line {line_no}: invalid message_id")

    for key in ("REVIEW", "KEEP", "DELETE"):
        print(f"{key}: {counts[key]}")

    if errors:
        print("\nValidation errors:")
        for error in errors:
            print("  " + error)
        return 1

    print("\nValidation OK.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
