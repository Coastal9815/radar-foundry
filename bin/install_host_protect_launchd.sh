#!/usr/bin/env bash
# Install daily/12-hour MRW host protection job on this Mac (intended: wx-core).
# Run: cd ~/wx/radar-foundry && ./bin/install_host_protect_launchd.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$REPO/conf/launchd/com.mrw.host_protect.plist"
DEST="$HOME/Library/LaunchAgents/com.mrw.host_protect.plist"
chmod +x "$REPO/bin/mrw_host_protect.sh"
cp "$PLIST_SRC" "$DEST"
launchctl bootout "gui/$(id -u)/com.mrw.host_protect" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "OK: com.mrw.host_protect loaded. Log: /tmp/mrw_host_protect.log"
