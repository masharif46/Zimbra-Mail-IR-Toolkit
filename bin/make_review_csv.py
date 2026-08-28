#!/usr/bin/env python3
import argparse
import csv

FIELDS = [
    "source", "status", "flags", "account", "mailbox_id", "message_id",
    "replacement_pct", "control_pct", "text_nul_pct",
    "raw_binary_pct", "raw_nul_pct",
    "missing_header_count", "missing_headers", "parser_defects",
    "compression", "first16_hex", "text_parts",
    "size_bytes", "parsed_size_bytes",
    "date", "from", "to", "subject", "message_id_header",
    "content_type", "path", "sha256", "error",
    "decision", "reviewer", "notes"
]


def add_rows(path, source, output):
    with open(
        path,
        newline="",
        encoding="utf-8-sig",
        errors="replace",
    ) as f:
        for row in csv.DictReader(f):
            item = {k: row.get(k, "") for k in FIELDS}
            item["source"] = source
            item["decision"] = "REVIEW"
            item["reviewer"] = ""
            item["notes"] = ""
            output.append(item)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate_csv")
    ap.add_argument("parse_csv")
    ap.add_argument("output_csv")
    args = ap.parse_args()

    rows = []
    add_rows(args.candidate_csv, "MESSAGE_SCAN", rows)
    add_rows(args.parse_csv, "PARSE_SCAN", rows)

    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
