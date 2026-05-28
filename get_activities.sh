#!/usr/bin/env bash
# Wrapper that runs get_activities.py from the repo directory, activating
# the local virtualenv if present. Arguments are forwarded verbatim.
set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.venv/bin/activate"
fi
exec python "$SCRIPT_DIR/get_activities.py" "$@"
