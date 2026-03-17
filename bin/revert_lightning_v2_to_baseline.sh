#!/bin/bash
# Revert Full View Lightning Map to baseline
# Usage: ./bin/revert_lightning_v2_to_baseline.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASELINE="$ROOT/player/lightning-full-view-baseline"
TARGET="$ROOT/player/lightning-full-view"

echo "Reverting lightning-full-view to baseline..."
rm -rf "$TARGET"
cp -r "$BASELINE" "$TARGET"
echo "Done. Deploy with: rsync -az $TARGET/ wx-i9:~/wx/radar-foundry/player/lightning-full-view/"
