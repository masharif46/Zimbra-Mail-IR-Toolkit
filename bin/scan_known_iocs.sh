#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ZEXEC="$ROOT_DIR/lib/zimbra_exec.sh"

OUT="${1:-known_ioc_mail.txt}"
IOC_FILE="${2:-$ROOT_DIR/config/iocs.txt}"
QUERY_FILE="${3:-$ROOT_DIR/config/subject_queries.txt}"
ACCOUNT="${4:-}"

: > "$OUT"

mapfile -t IOCS < <(grep -v '^[[:space:]]*#' "$IOC_FILE" | sed '/^[[:space:]]*$/d')
mapfile -t SUBJECT_QUERIES < <(grep -v '^[[:space:]]*#' "$QUERY_FILE" | sed '/^[[:space:]]*$/d')

scan_account() {
    local acct="$1"
    local q result ioc

    for ioc in "${IOCS[@]}"; do
        q="content:\"$ioc\""
        result="$("$ZEXEC" /opt/zimbra/bin/zmmailbox -z -m "$acct" search -l 1000 "$q" 2>&1 || true)"
        if ! printf '%s\n' "$result" | grep -q '^num: 0, more: false'; then
            {
                printf '===== ACCOUNT: %s =====\n' "$acct"
                printf 'QUERY: %s\n' "$q"
                printf '%s\n\n' "$result"
            } >> "$OUT"
        fi
    done

    for q in "${SUBJECT_QUERIES[@]}"; do
        result="$("$ZEXEC" /opt/zimbra/bin/zmmailbox -z -m "$acct" search -l 1000 "$q" 2>&1 || true)"
        if ! printf '%s\n' "$result" | grep -q '^num: 0, more: false'; then
            {
                printf '===== ACCOUNT: %s =====\n' "$acct"
                printf 'QUERY: %s\n' "$q"
                printf '%s\n\n' "$result"
            } >> "$OUT"
        fi
    done
}

if [ -n "$ACCOUNT" ]; then
    scan_account "$ACCOUNT"
else
    "$ZEXEC" /opt/zimbra/bin/zmprov -l gaa 2>/dev/null |
    while IFS= read -r acct; do
        [ -z "$acct" ] && continue
        scan_account "$acct"
    done
fi
