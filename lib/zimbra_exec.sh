#!/bin/bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: zimbra_exec.sh COMMAND [ARGS...]" >&2
    exit 2
fi

if [ "$(id -un)" = "zimbra" ]; then
    exec "$@"
fi

if [ "$(id -u)" -eq 0 ]; then
    if command -v runuser >/dev/null 2>&1; then
        exec runuser -u zimbra -- "$@"
    fi
    echo "ERROR: root execution requires runuser." >&2
    exit 1
fi

echo "ERROR: run as root or zimbra." >&2
exit 1
