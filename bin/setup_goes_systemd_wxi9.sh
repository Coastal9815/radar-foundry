#!/usr/bin/env bash
# Install systemd user timer for GOES watchdog (backup if cron fails).
# Run on wx-i9: ./bin/setup_goes_systemd_wxi9.sh
set -e
cd "$(dirname "$0")/.."
# Ensure user timers run when not logged in
loginctl enable-linger "$USER" 2>/dev/null || true
mkdir -p ~/.config/systemd/user
cp conf/systemd/mrw-goes-watchdog.service ~/.config/systemd/user/
cp conf/systemd/mrw-goes-watchdog.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable mrw-goes-watchdog.timer
systemctl --user start mrw-goes-watchdog.timer
systemctl --user status mrw-goes-watchdog.timer
