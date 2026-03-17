#!/usr/bin/env bash
# Create a timestamped restore-point backup. Run from project root.
set -e
cd "$(dirname "$0")/.."
mkdir -p backups
name="radar-foundry-restore-$(date +%Y%m%d-%H%M).tar.gz"
tar --exclude='.venv' --exclude='.git' --exclude='__pycache__' --exclude='serve_cache' \
    --exclude='scratch' --exclude='raw_level2' --exclude='raw' --exclude='logs' --exclude='logs_level2' --exclude='work' \
    -czvf "backups/$name" .
echo "Backup: backups/$name"
