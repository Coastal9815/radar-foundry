#!/bin/bash
# Deploy MRW FlashGate relay to Lightning-PC (192.168.2.223).
# Run from wx-core. Requires SSH access to scott@192.168.2.223.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE="scott@192.168.2.223"
REMOTE_DIR="C:/MRW/lightning"

echo "=== Building flashgate_relay.exe ==="
cd "$SCRIPT_DIR"
GOOS=windows GOARCH=amd64 go build -o flashgate_relay.exe .
echo "Built: $SCRIPT_DIR/flashgate_relay.exe"

echo "=== Deploying to Lightning-PC ==="
ssh "$REMOTE" "if not exist $REMOTE_DIR mkdir $REMOTE_DIR"
scp "$SCRIPT_DIR/flashgate_relay.exe" "$REMOTE:$REMOTE_DIR/"
scp "$SCRIPT_DIR/start_lightning_pipeline.bat" "$REMOTE:$REMOTE_DIR/"
scp "$SCRIPT_DIR/start_lightning_pipeline.vbs" "$REMOTE:$REMOTE_DIR/"
scp "$SCRIPT_DIR/setup_autologon.ps1" "$REMOTE:$REMOTE_DIR/"

echo "=== Removing old Task Scheduler task ==="
ssh "$REMOTE" "schtasks /delete /tn \"MRW FlashGate Relay\" /f 2>nul || true"

echo "=== Adding MRW Lightning pipeline to Startup (runs in user session) ==="
ssh "$REMOTE" "powershell -NoProfile -Command \"\$WshShell = New-Object -ComObject WScript.Shell; \$startup = [Environment]::GetFolderPath('Startup'); \$shortcut = \$WshShell.CreateShortcut(\$startup + '\\\\MRW Lightning.lnk'); \$shortcut.TargetPath = 'C:\\\\Windows\\\\System32\\\\wscript.exe'; \$shortcut.Arguments = 'C:\\\\MRW\\\\lightning\\\\start_lightning_pipeline.vbs'; \$shortcut.WorkingDirectory = 'C:\\\\MRW\\\\lightning'; \$shortcut.WindowStyle = 7; \$shortcut.Description = 'MRW Lightning: NexStorm + FlashGate relay'; \$shortcut.Save()\""

echo "=== Deployment complete ==="
echo "Relay: $REMOTE_DIR/flashgate_relay.exe"
echo "Pipeline: start_lightning_pipeline.bat (NexStorm + relay, restart on crash)"
echo "Startup: MRW Lightning.lnk -> runs pipeline at logon (hidden)"
echo ""
echo "REQUIRED for 24/7 unattended: Run ONCE on Lightning-PC as Administrator:"
echo "  powershell -ExecutionPolicy Bypass -File C:\\MRW\\lightning\\setup_autologon.ps1 -Username scott -Password YOUR_PASSWORD"
