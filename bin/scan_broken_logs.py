#!/usr/bin/env python3
import argparse
import csv
import glob
import re

PAT = re.compile(
    r"No such blob:\s*mailbox=(\d+),\s*item=(\d+),\s*change=(\d+)",
    re.IGNORECASE,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--txt", required=True)
    ap.add_argument("--mailbox-id", default="")
    ap.add_argument(
        "--glob",
        dest="log_glob",
        default="/opt/zimbra/log/mailbox.log*",
    )
    args = ap.parse_args()

    wanted = args.mailbox_id.strip()
    counts = {}

    for path in sorted(glob.glob(args.log_glob)):
        try:
            f = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue

        with f:
            for line in f:
                m = PAT.search(line)
                if not m:
                    continue

                mailbox_id, item_id, change_id = m.groups()
                if wanted and mailbox_id != wanted:
                    continue

                key = (mailbox_id, item_id, change_id)
                if key not in counts:
                    counts[key] = {
                        "mailbox_id": mailbox_id,
                        "message_id": item_id,
                        "change_id": change_id,
                        "occurrences": 0,
                        "first_log_file": path,
                    }
                counts[key]["occurrences"] += 1

    rows = sorted(
        counts.values(),
        key=lambda r: (
            int(r["mailbox_id"]),
            int(r["message_id"]),
            int(r["change_id"]),
        ),
    )

    fields = [
        "mailbox_id",
        "message_id",
        "change_id",
        "occurrences",
        "first_log_file",
    ]

    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    with open(args.txt, "w", encoding="utf-8") as f:
        scope = wanted or "ALL"
        f.write(f"Mailbox scope: {scope}\n")
        f.write(f"Unique NO_SUCH_BLOB items: {len(rows)}\n\n")
        for row in rows:
            f.write(
                "mailbox={mailbox_id} item={message_id} "
                "change={change_id} occurrences={occurrences}\n".format(**row)
            )


if __name__ == "__main__":
    main()
