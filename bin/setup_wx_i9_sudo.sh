#!/bin/bash
# One-time setup on wx-i9: install sudoers file so scott can manage mrw-serve-frames without password.
# Run as: sudo bash bin/setup_wx_i9_sudo.sh
# Must be run from project root.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SUDOERS_SRC="$PROJECT_ROOT/conf/sudoers.d/mrw-serve-frames"
SUDOERS_DEST="/etc/sudoers.d/mrw-serve-frames"

[ -f "$SUDOERS_SRC" ] || { echo "Missing $SUDOERS_SRC"; exit 1; }
cp "$SUDOERS_SRC" "$SUDOERS_DEST"
chmod 440 "$SUDOERS_DEST"
echo "Installed $SUDOERS_DEST - scott can now run systemctl for mrw-serve-frames without password"
