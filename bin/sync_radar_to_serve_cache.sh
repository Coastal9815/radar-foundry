#!/bin/bash
# Sync external radar frames to internal serve cache.
# LaunchAgents cannot read from external volumes (TCC), so we mirror to internal for serving.
SRC="/Volumes/WX_SCRATCH/mrw/radar"
DST="/Users/scott/wx/radar-foundry/serve_cache/radar"
[ ! -d "$SRC" ] && exit 0
mkdir -p "$DST"
rsync -a --delete "$SRC/" "$DST/" 2>/dev/null || true
