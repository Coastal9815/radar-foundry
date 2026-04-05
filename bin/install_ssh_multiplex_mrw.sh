#!/usr/bin/env bash
# One-time on wx-core (or any MRW Mac that floods wx-i9 / Lightning-PC with ssh):
#   cd ~/wx/radar-foundry && ./bin/install_ssh_multiplex_mrw.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/.ssh/sockets" "$HOME/.ssh/config.d"
install -m 0644 "$REPO/conf/ssh/mrw-multiplex.conf" "$HOME/.ssh/config.d/mrw-multiplex.conf"
CFG="$HOME/.ssh/config"
if [[ ! -f "$CFG" ]]; then
  touch "$CFG"
  chmod 0600 "$CFG"
fi
if ! grep -qE '^[[:space:]]*Include[[:space:]]+.*config\.d/mrw-multiplex\.conf' "$CFG" 2>/dev/null; then
  printf '\n# MRW: shared SSH sessions (see conf/ssh/mrw-multiplex.conf)\nInclude config.d/mrw-multiplex.conf\n' >> "$CFG"
fi
echo "OK: $HOME/.ssh/config.d/mrw-multiplex.conf installed and main config includes it."
