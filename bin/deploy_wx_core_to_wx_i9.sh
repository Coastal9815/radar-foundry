#!/usr/bin/env bash
# Run sync_to_wx_i9 on wx-core (preferred: wx-core has lightning ndjson for geo generators).
# Run from Office Mac. SSHs to wx-core and runs sync_to_wx_i9 there.
#
# Usage: ./bin/deploy_wx_core_to_wx_i9.sh
set -e
cd "$(dirname "$0")/.."
WX_CORE="${WX_CORE:-wx-core}"
echo "Running sync_to_wx_i9 on $WX_CORE ..."
ssh "$WX_CORE" "cd ~/wx/radar-foundry && ./bin/sync_to_wx_i9.sh"
echo "Done."
