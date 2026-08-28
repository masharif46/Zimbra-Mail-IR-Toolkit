#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ZEXEC="$ROOT_DIR/lib/zimbra_exec.sh"

OUT="${1:-mailbox_map.tsv}"
TMP="${OUT}.tmp.$$"

"$ZEXEC" /opt/zimbra/bin/zmprov -l gaa 2>/dev/null |
while IFS= read -r acct; do
    [ -z "$acct" ] && continue
    mid="$("$ZEXEC" /opt/zimbra/bin/zmprov gmi "$acct" 2>/dev/null |
        awk '/mailboxId:/ {print $2; exit}')"
    if [ -n "$mid" ]; then
        printf '%s\t%s\n' "$mid" "$acct"
    fi
done > "$TMP"

mv "$TMP" "$OUT"
