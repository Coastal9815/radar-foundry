#!/bin/bash
# Wrapper for serve_frames.py: wait for external disk, then exec.
cd /Users/scott/wx/radar-foundry || exit 1
for i in $(seq 1 120); do
  [ -d /Volumes/WX_SCRATCH/mrw/radar ] && break
  sleep 1
done
[ ! -d /Volumes/WX_SCRATCH/mrw/radar ] && { echo "serve_frames: external dir not available" >&2; exit 1; }
exec /Users/scott/wx/radar-foundry/.venv/bin/python /Users/scott/wx/radar-foundry/bin/serve_frames.py
