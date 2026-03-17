#!/bin/bash
# Usage: curl_download.sh <url> <out_path>
/usr/bin/curl -sSf -o "$2" --max-time 180 "$1"
