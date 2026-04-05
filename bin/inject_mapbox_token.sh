#!/usr/bin/env bash
# Replace YOUR_MAPBOX_PUBLIC_TOKEN in Mapbox-based player HTML with a real public token.
# Mapbox pk.* tokens are public; restrict by URL in Mapbox account. Do not commit real tokens.
#
# Usage (from repo root or via this script):
#   export MAPBOX_PUBLIC_TOKEN="pk...."
#   ./bin/inject_mapbox_token.sh
#
# Run before rsync/deploy to Cloudflare or wx-i9 if players show UI but blank maps.
#
# If MAPBOX_PUBLIC_TOKEN is unset, reads accessToken from conf/mapbox_config.json (same as local dev).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -z "${MAPBOX_PUBLIC_TOKEN:-}" ]]; then
  CONF="$ROOT/conf/mapbox_config.json"
  if [[ -f "$CONF" ]]; then
    MAPBOX_PUBLIC_TOKEN="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1],encoding=\"utf-8\"))[\"accessToken\"])" "$CONF")"
  else
    echo "MAPBOX_PUBLIC_TOKEN is not set and $CONF not found" >&2
    exit 1
  fi
fi
export MAPBOX_PUBLIC_TOKEN
export RF_ROOT="$ROOT"

python3 <<'PY'
import os
import pathlib
import sys

root = pathlib.Path(os.environ["RF_ROOT"])
token = os.environ["MAPBOX_PUBLIC_TOKEN"]
if "YOUR_MAPBOX" in token:
    print("Refusing: token looks like another placeholder", file=sys.stderr)
    sys.exit(1)
needle = "YOUR_MAPBOX_PUBLIC_TOKEN"
n = 0
for path in (root / "player").rglob("index.html"):
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        continue
    path.write_text(text.replace(needle, token), encoding="utf-8")
    n += 1
    print("Updated", path.relative_to(root))
if n == 0:
    print("No files contained", needle, "(maps may already use a real token)", file=sys.stderr)
    sys.exit(0)
print("Injected token into", n, "player file(s).")
PY
