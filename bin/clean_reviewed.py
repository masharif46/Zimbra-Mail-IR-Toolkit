#!/usr/bin/env python3
"""Remove duplicate account/message_id rows from a reviewed CSV."""

import argparse
import csv
import os
import sys


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Create a cleaned reviewed CSV, keeping the first row for each "
            "account + message_id pair."
        )
    )
    ap.add_argument("input_csv", help="reviewed CSV to clean")
    ap.add_argument(
        "-o", "--output",
        help="output CSV (default: <input>_clean.csv)",
    )
    args = ap.parse_args()

    if args.output:
        output_csv = args.output
    else:
        base, ext = os.path.splitext(args.input_csv)
        output_csv = base + "_clean" + (ext or ".csv")

    if os.path.abspath(args.input_csv) == os.path.abspath(output_csv):
        print("ERROR: input and output files must be different", file=sys.stderr)
        return 2

    seen = set()
    total = 0
    removed = 0

    try:
        with open(args.input_csv, newline="", encoding="utf-8-sig", errors="replace") as fin:
            reader = csv.DictReader(fin)
            if not reader.fieldnames:
                print("ERROR: CSV has no header", file=sys.stderr)
                return 2

            required = {"account", "message_id"}
            missing = required - set(reader.fieldnames)
            if missing:
                print(
                    "ERROR: missing columns: " + ", ".join(sorted(missing)),
                    file=sys.stderr,
                )
                return 2

            with open(output_csv, "w", newline="", encoding="utf-8") as fout:
                writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
                writer.writeheader()

                for row in reader:
                    total += 1
                    key = (row["account"].strip(), row["message_id"].strip())
                    if key in seen:
                        removed += 1
                        continue
                    seen.add(key)
                    writer.writerow(row)
    except OSError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2

    print("Input rows: {}".format(total))
    print("Removed duplicate rows: {}".format(removed))
    print("Output rows: {}".format(total - removed))
    print("Created: {}".format(output_csv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
