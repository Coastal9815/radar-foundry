#!/bin/bash
# Run MRW Lightning .nex tail pipeline. Used by launchd.
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] && exec .venv/bin/python bin/lightning_nex_tail.py --interval 3 --output-remote
exec python3 bin/lightning_nex_tail.py --interval 3 --output-remote
