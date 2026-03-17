#!/bin/bash
# Build flashgate_relay.exe for Windows (run on wx-core or any machine with Go).
# Output: flashgate_relay.exe in this directory.
set -e
cd "$(dirname "$0")"
GOOS=windows GOARCH=amd64 go build -o flashgate_relay.exe .
echo "Built: $(pwd)/flashgate_relay.exe"
