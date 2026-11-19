#!/bin/sh
# Same entry point for a user's private prefix and an administrator-owned prefix.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/deploy-tigu-modules.py" "$@"
