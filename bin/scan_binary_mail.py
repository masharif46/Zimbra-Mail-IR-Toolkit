#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import sys
import time
from email import policy
from email.parser import BytesParser

KEY_HEADERS = ("From", "To", "Subject", "Date", "Message-ID", "Content-Type")


def iter_nul_paths(stream):
    pending = b""
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        pending += chunk
        parts = pending.split(b"\0")
        pending = parts.pop()
        for raw in parts:
            if raw:
                yield raw.decode(sys.getfilesystemencoding(), errors="replace")
    if pending:
        yield pending.decode(sys.getfilesystemencoding(), errors="replace")


def load_map(path):
    mapping = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2:
                mapping[parts[0]] = parts[1]
    return mapping


def ids_from_path(path):
    # Standard primary store:
    # /opt/zimbra/store/0/600/msg/3/14828-34445.msg
    m = re.search(r"/store/\d+/(\d+)/msg/\d+/(\d+)-", path)
    if m:
        return m.group(1), m.group(2)

    # Fallback for custom/HSM roots that retain:
    # .../<mailbox_id>/msg/<group>/<item>-<revision>.msg
    m = re.search(r"/(\d+)/msg/\d+/(\d+)-", path)
    if m:
        return m.group(1), m.group(2)

    return "?", "?"


def safe_header(value, limit):
    return str(value or "").replace("\r", " ").replace("\n", " ")[:limit]


def percent_bad_bytes(data):
    if not data:
        return 0.0, 0.0
    bad = sum(
        1 for b in data
        if b not in (9, 10, 13) and not (32 <= b <= 126)
    )
    nul = data.count(b"\x00")
    return bad / len(data), nul / len(data)


def analyze_text_payload(data, charset):
    if not data:
        return None

    try:
        text = data.decode(charset or "utf-8", errors="replace")
    except Exception:
        text = data.decode("utf-8", errors="replace")

    if not text:
        return None

    replacement = text.count("\ufffd") / max(len(text), 1)
    control = sum(
        1 for c in text
        if ((ord(c) < 32 and c not in "\t\r\n") or 127 <= ord(c) <= 159)
    ) / max(len(text), 1)
    nul = data.count(b"\x00") / max(len(data), 1)

    return replacement, control, nul


def read_blob(path):
    with open(path, "rb") as f:
        stored = f.read()

    stored_sha256 = hashlib.sha256(stored).hexdigest()
    stored_first16 = stored[:16].hex()
    compression = "none"
    parse_data = stored

    # Avoid falsely treating a legitimate compressed Zimbra blob as corruption.
    if stored.startswith(b"\x1f\x8b"):
        compression = "gzip"
        try:
            parse_data = gzip.decompress(stored)
        except Exception as exc:
            return {
                "stored": stored,
                "parse_data": b"",
                "sha256": stored_sha256,
                "first16_hex": stored_first16,
                "compression": compression,
                "decompression_error": str(exc),
            }

    return {
        "stored": stored,
        "parse_data": parse_data,
        "sha256": stored_sha256,
        "first16_hex": stored_first16,
        "compression": compression,
        "decompression_error": "",
    }


def defect_names(msg):
    return ",".join(type(d).__name__ for d in getattr(msg, "defects", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--parse-tsv", required=True)
    ap.add_argument("--parse-csv", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--replacement", type=float, default=0.02)
    ap.add_argument("--control", type=float, default=0.02)
    ap.add_argument("--nul", type=float, default=0.001)
    ap.add_argument("--raw-binary", type=float, default=0.20)
    ap.add_argument("--raw-nul", type=float, default=0.001)
    ap.add_argument("--missing-headers", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.0)
    args = ap.parse_args()

    mailbox_map = load_map(args.map)

    fields = [
        "status", "flags", "account", "mailbox_id", "message_id",
        "replacement_pct", "control_pct", "text_nul_pct",
        "raw_binary_pct", "raw_nul_pct",
        "missing_header_count", "missing_headers", "parser_defects",
        "compression", "first16_hex", "text_parts", "size_bytes",
        "parsed_size_bytes", "date", "from", "to", "subject",
        "message_id_header", "content_type", "path", "sha256"
    ]

    parse_fields = [
        "status", "account", "mailbox_id", "message_id", "size_bytes",
        "compression", "first16_hex", "error", "path", "sha256"
    ]

    stats = {
        "scanned_files": 0,
        "candidate_rows": 0,
        "raw_blob_corrupt": 0,
        "binary_text": 0,
        "gzip_blobs": 0,
        "parse_errors": 0,
        "decompression_errors": 0,
    }

    with open(args.tsv, "w", newline="", encoding="utf-8") as ft, \
         open(args.csv, "w", newline="", encoding="utf-8") as fc, \
         open(args.parse_tsv, "w", newline="", encoding="utf-8") as fpt, \
         open(args.parse_csv, "w", newline="", encoding="utf-8") as fpc:

        tw = csv.DictWriter(ft, fieldnames=fields, delimiter="\t")
        cw = csv.DictWriter(fc, fieldnames=fields)
        ptw = csv.DictWriter(fpt, fieldnames=parse_fields, delimiter="\t")
        pcw = csv.DictWriter(fpc, fieldnames=parse_fields)

        for writer in (tw, cw, ptw, pcw):
            writer.writeheader()

        for path in iter_nul_paths(sys.stdin.buffer):
            stats["scanned_files"] += 1
            mailbox_id, item_id = ids_from_path(path)
            account = mailbox_map.get(mailbox_id, "UNKNOWN")

            try:
                size_bytes = os.path.getsize(path)
            except OSError:
                size_bytes = 0

            try:
                blob = read_blob(path)
            except Exception as exc:
                stats["parse_errors"] += 1
                row = {
                    "status": "READ_ERROR",
                    "account": account,
                    "mailbox_id": mailbox_id,
                    "message_id": item_id,
                    "size_bytes": size_bytes,
                    "compression": "",
                    "first16_hex": "",
                    "error": str(exc)[:500],
                    "path": path,
                    "sha256": "",
                }
                ptw.writerow(row)
                pcw.writerow(row)
                fpt.flush()
                fpc.flush()
                if args.delay:
                    time.sleep(args.delay)
                continue

            if blob["compression"] == "gzip":
                stats["gzip_blobs"] += 1

            if blob["decompression_error"]:
                stats["decompression_errors"] += 1
                row = {
                    "status": "DECOMPRESSION_ERROR",
                    "account": account,
                    "mailbox_id": mailbox_id,
                    "message_id": item_id,
                    "size_bytes": size_bytes,
                    "compression": blob["compression"],
                    "first16_hex": blob["first16_hex"],
                    "error": blob["decompression_error"][:500],
                    "path": path,
                    "sha256": blob["sha256"],
                }
                ptw.writerow(row)
                pcw.writerow(row)
                fpt.flush()
                fpc.flush()
                if args.delay:
                    time.sleep(args.delay)
                continue

            parse_data = blob["parse_data"]
            raw_binary, raw_nul = percent_bad_bytes(parse_data)

            try:
                msg = BytesParser(policy=policy.default).parsebytes(parse_data)
            except Exception as exc:
                stats["parse_errors"] += 1
                row = {
                    "status": "PARSE_ERROR",
                    "account": account,
                    "mailbox_id": mailbox_id,
                    "message_id": item_id,
                    "size_bytes": size_bytes,
                    "compression": blob["compression"],
                    "first16_hex": blob["first16_hex"],
                    "error": str(exc)[:500],
                    "path": path,
                    "sha256": blob["sha256"],
                }
                ptw.writerow(row)
                pcw.writerow(row)
                fpt.flush()
                fpc.flush()
                if args.delay:
                    time.sleep(args.delay)
                continue

            defects = defect_names(msg)
            missing = [h for h in KEY_HEADERS if msg.get(h) is None]
            missing_count = len(missing)

            # Explicit raw-blob corruption detector.
            #
            # A valid message may legitimately lack one or two optional headers,
            # so this requires multiple missing headers PLUS a parser structural
            # defect PLUS a strongly binary body. Gzip blobs are decompressed
            # before this decision.
            has_header_separator_defect = (
                "MissingHeaderBodySeparatorDefect" in defects
            )
            raw_blob_corrupt = (
                missing_count >= args.missing_headers
                and has_header_separator_defect
                and (
                    raw_binary >= args.raw_binary
                    or raw_nul >= args.raw_nul
                )
            )

            worst_rep = 0.0
            worst_ctrl = 0.0
            worst_text_nul = 0.0
            text_parts = 0
            binary_text = False

            for part in msg.walk():
                if part.is_multipart():
                    continue
                if not part.get_content_type().startswith("text/"):
                    continue

                text_parts += 1

                try:
                    payload = part.get_payload(decode=True)
                except Exception:
                    payload = None

                if payload is None:
                    value = part.get_payload()
                    if not isinstance(value, str):
                        continue
                    try:
                        payload = value.encode(
                            part.get_content_charset() or "utf-8",
                            errors="replace",
                        )
                    except Exception:
                        payload = value.encode("utf-8", errors="replace")

                result = analyze_text_payload(
                    payload, part.get_content_charset()
                )
                if result is None:
                    continue

                rep, ctrl, text_nul = result
                worst_rep = max(worst_rep, rep)
                worst_ctrl = max(worst_ctrl, ctrl)
                worst_text_nul = max(worst_text_nul, text_nul)

                if (
                    rep >= args.replacement
                    or ctrl >= args.control
                    or text_nul >= args.nul
                ):
                    binary_text = True

            flags = []
            if raw_blob_corrupt:
                flags.append("RAW_BLOB_CORRUPT")
                stats["raw_blob_corrupt"] += 1
            if binary_text:
                flags.append("BINARY_TEXT")
                stats["binary_text"] += 1

            if flags:
                stats["candidate_rows"] += 1
                status = (
                    "RAW_BLOB_CORRUPT"
                    if raw_blob_corrupt
                    else "BINARY_TEXT"
                )

                row = {
                    "status": status,
                    "flags": "|".join(flags),
                    "account": account,
                    "mailbox_id": mailbox_id,
                    "message_id": item_id,
                    "replacement_pct": f"{worst_rep * 100:.2f}",
                    "control_pct": f"{worst_ctrl * 100:.2f}",
                    "text_nul_pct": f"{worst_text_nul * 100:.2f}",
                    "raw_binary_pct": f"{raw_binary * 100:.2f}",
                    "raw_nul_pct": f"{raw_nul * 100:.2f}",
                    "missing_header_count": missing_count,
                    "missing_headers": "|".join(missing),
                    "parser_defects": defects,
                    "compression": blob["compression"],
                    "first16_hex": blob["first16_hex"],
                    "text_parts": text_parts,
                    "size_bytes": size_bytes,
                    "parsed_size_bytes": len(parse_data),
                    "date": safe_header(msg.get("Date", ""), 160),
                    "from": safe_header(msg.get("From", ""), 240),
                    "to": safe_header(msg.get("To", ""), 240),
                    "subject": safe_header(msg.get("Subject", ""), 320),
                    "message_id_header": safe_header(
                        msg.get("Message-ID", ""), 320
                    ),
                    "content_type": safe_header(
                        msg.get("Content-Type", ""), 200
                    ),
                    "path": path,
                    "sha256": blob["sha256"],
                }

                tw.writerow(row)
                cw.writerow(row)
                ft.flush()
                fc.flush()

            if args.delay:
                time.sleep(args.delay)

    with open(args.stats, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
