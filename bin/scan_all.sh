#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ZEXEC="$ROOT_DIR/lib/zimbra_exec.sh"

START=""
END=""
ALL_TIME=0
DELAY="0"
REP="0.02"
CTRL="0.02"
NUL="0.001"
RAW_BINARY="0.20"
RAW_NUL="0.001"
MISSING_HEADERS="4"
OUTDIR=""
IOC_SEARCH=0
ACCOUNT=""
STORES=()

usage() {
    cat <<EOF
Zimbra Mail IR Toolkit v2.2

Usage:
  $0 --start YYYY-MM-DD --end YYYY-MM-DD [options]
  $0 --all-time [options]

Options:
  --account EMAIL          Scan one mailbox only
  --start DATE
  --end DATE               End is exclusive at 00:00:00
  --all-time
  --delay SECONDS
  --replacement FRACTION   default 0.02
  --control FRACTION       default 0.02
  --nul FRACTION           default 0.001
  --raw-binary FRACTION    default 0.20
  --raw-nul FRACTION       default 0.001
  --missing-headers N      default 4
  --out DIR
  --store PATH             May be repeated
  --ioc-search
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --account) ACCOUNT="$2"; shift 2 ;;
        --start) START="$2"; shift 2 ;;
        --end) END="$2"; shift 2 ;;
        --all-time) ALL_TIME=1; shift ;;
        --delay) DELAY="$2"; shift 2 ;;
        --replacement) REP="$2"; shift 2 ;;
        --control) CTRL="$2"; shift 2 ;;
        --nul) NUL="$2"; shift 2 ;;
        --raw-binary) RAW_BINARY="$2"; shift 2 ;;
        --raw-nul) RAW_NUL="$2"; shift 2 ;;
        --missing-headers) MISSING_HEADERS="$2"; shift 2 ;;
        --out) OUTDIR="$2"; shift 2 ;;
        --store) STORES+=("$2"); shift 2 ;;
        --ioc-search) IOC_SEARCH=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

if [ "$ALL_TIME" -eq 0 ] && { [ -z "$START" ] || [ -z "$END" ]; }; then
    echo "ERROR: provide --start and --end, or use --all-time" >&2
    exit 2
fi

if [ "${#STORES[@]}" -eq 0 ]; then
    STORES=("/opt/zimbra/store")
fi

for store in "${STORES[@]}"; do
    [ -d "$store" ] || {
        echo "ERROR: no such store: $store" >&2
        exit 1
    }
done

if [ -z "$OUTDIR" ]; then
    if [ -n "$ACCOUNT" ]; then
        SAFE_ACCOUNT="$(printf '%s' "$ACCOUNT" | tr -c 'A-Za-z0-9_.@-' '_')"
        OUTDIR="/tmp/zimbra-mail-ir-${SAFE_ACCOUNT}-$(date +%Y%m%d-%H%M%S)"
    else
        OUTDIR="/tmp/zimbra-mail-ir-$(date +%Y%m%d-%H%M%S)"
    fi
fi

mkdir -p "$OUTDIR"
chmod 700 "$OUTDIR"

MAILBOX_ID=""

if [ -n "$ACCOUNT" ]; then
    if [[ "$ACCOUNT" != *@* ]]; then
        echo "ERROR: invalid account: $ACCOUNT" >&2
        exit 2
    fi

    MAILBOX_ID="$("$ZEXEC" /opt/zimbra/bin/zmprov gmi "$ACCOUNT" 2>/dev/null |
        awk '/mailboxId:/ {print $2; exit}')"

    if ! [[ "$MAILBOX_ID" =~ ^[0-9]+$ ]]; then
        echo "ERROR: could not resolve mailbox ID for $ACCOUNT" >&2
        exit 1
    fi

    printf '%s\t%s\n' "$MAILBOX_ID" "$ACCOUNT" \
        > "$OUTDIR/mailbox_map.tsv"

    echo "[1/5] Single mailbox: $ACCOUNT (mailbox ID $MAILBOX_ID)"
else
    echo "[1/5] Building mailbox map..."
    "$SCRIPT_DIR/build_mailbox_map.sh" "$OUTDIR/mailbox_map.tsv"
fi

{
    echo "Zimbra Mail IR Toolkit v2.2"
    echo "Started: $(date -Is)"
    echo "User: $(id -un)"
    echo "Host: $(hostname -f 2>/dev/null || hostname)"
    echo "Account: ${ACCOUNT:-ALL}"
    echo "Mailbox ID: ${MAILBOX_ID:-ALL}"
    echo "All time: $ALL_TIME"
    echo "Start: $START"
    echo "End: $END"
    echo "Date filter basis: blob filesystem mtime"
    echo "Delay: $DELAY"
    echo "Raw binary threshold: $RAW_BINARY"
    echo "Raw NUL threshold: $RAW_NUL"
    echo "Missing header threshold: $MISSING_HEADERS"
    echo "Stores:"
    printf '  %s\n' "${STORES[@]}"
} > "$OUTDIR/run_metadata.txt"

SCAN=(
    python3 "$SCRIPT_DIR/scan_binary_mail.py"
    --map "$OUTDIR/mailbox_map.tsv"
    --tsv "$OUTDIR/binary_text_results.tsv"
    --csv "$OUTDIR/binary_text_results.csv"
    --parse-tsv "$OUTDIR/parse_errors.tsv"
    --parse-csv "$OUTDIR/parse_errors.csv"
    --stats "$OUTDIR/scan_stats.json"
    --replacement "$REP"
    --control "$CTRL"
    --nul "$NUL"
    --raw-binary "$RAW_BINARY"
    --raw-nul "$RAW_NUL"
    --missing-headers "$MISSING_HEADERS"
    --delay "$DELAY"
)

if command -v ionice >/dev/null 2>&1; then
    LOW=(ionice -c2 -n7 nice -n 10)
else
    LOW=(nice -n 10)
fi

echo "[2/5] Streaming message-store scan..."

# Build find expression explicitly. The scanner records the exact scanned count
# in scan_stats.json, which makes selection problems visible immediately.
FIND_ARGS=("${STORES[@]}" -type f -name '*.msg')

if [ -n "$ACCOUNT" ]; then
    FIND_ARGS+=(-path "*/${MAILBOX_ID}/msg/*/*.msg")
fi

if [ "$ALL_TIME" -eq 0 ]; then
    FIND_ARGS+=(
        -newermt "$START 00:00:00"
        ! -newermt "$END 00:00:00"
    )
fi

find "${FIND_ARGS[@]}" -print0 |
    "${LOW[@]}" "${SCAN[@]}"

echo "[3/5] Scanning mailbox logs for unique NO_SUCH_BLOB items..."

BROKEN_ARGS=(
    python3 "$SCRIPT_DIR/scan_broken_logs.py"
    --csv "$OUTDIR/broken_blob_results.csv"
    --txt "$OUTDIR/broken_mail_log.txt"
)

if [ -n "$MAILBOX_ID" ]; then
    BROKEN_ARGS+=(--mailbox-id "$MAILBOX_ID")
fi

"${BROKEN_ARGS[@]}"

if [ "$IOC_SEARCH" -eq 1 ]; then
    echo "[4/5] Running optional IOC mailbox searches..."
    if [ -n "$ACCOUNT" ]; then
        "$SCRIPT_DIR/scan_known_iocs.sh" \
            "$OUTDIR/known_ioc_mail.txt" \
            "$ROOT_DIR/config/iocs.txt" \
            "$ROOT_DIR/config/subject_queries.txt" \
            "$ACCOUNT"
    else
        "$SCRIPT_DIR/scan_known_iocs.sh" \
            "$OUTDIR/known_ioc_mail.txt" \
            "$ROOT_DIR/config/iocs.txt" \
            "$ROOT_DIR/config/subject_queries.txt"
    fi
else
    echo "IOC mailbox search skipped; use --ioc-search to enable." \
        > "$OUTDIR/known_ioc_mail.txt"
    echo "[4/5] IOC mailbox search skipped."
fi

echo "[5/5] Creating review CSV..."
python3 "$SCRIPT_DIR/make_review_csv.py" \
    "$OUTDIR/binary_text_results.csv" \
    "$OUTDIR/parse_errors.csv" \
    "$OUTDIR/review_candidates.csv"

read_stat() {
    python3 - "$OUTDIR/scan_stats.json" "$1" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
print(d.get(sys.argv[2], 0))
PY
}

SCANNED="$(read_stat scanned_files)"
CANDIDATES="$(read_stat candidate_rows)"
RAW="$(read_stat raw_blob_corrupt)"
BTEXT="$(read_stat binary_text)"
PARSE="$(read_stat parse_errors)"
GZIP="$(read_stat gzip_blobs)"
BROKEN="$(
    awk 'END {print (NR>0 ? NR-1 : 0)}' \
        "$OUTDIR/broken_blob_results.csv"
)"

cat > "$OUTDIR/summary.txt" <<EOF
Zimbra Mail IR Toolkit v2.2
Output directory: $OUTDIR
Account scope: ${ACCOUNT:-ALL}
Mailbox ID: ${MAILBOX_ID:-ALL}

Message blobs actually scanned: $SCANNED
Candidate rows: $CANDIDATES
RAW_BLOB_CORRUPT flags: $RAW
BINARY_TEXT flags: $BTEXT
Parser errors: $PARSE
Gzip-compressed blobs handled: $GZIP
Unique NO_SUCH_BLOB items in scope: $BROKEN
IOC search enabled: $IOC_SEARCH

Primary review file:
  $OUTDIR/review_candidates.csv

Candidate report:
  $OUTDIR/binary_text_results.csv

Scoped broken-blob report:
  $OUTDIR/broken_blob_results.csv

No messages were deleted or modified by this scan.
EOF

cat "$OUTDIR/summary.txt"
