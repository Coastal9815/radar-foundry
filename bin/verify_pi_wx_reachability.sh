#!/bin/bash
# Verify wx-i9 can reach pi-wx. Run on wx-i9 or via: ssh wx-i9 "~/wx/radar-foundry/bin/verify_pi_wx_reachability.sh"
# Exit 0 if OK, 1 if unreachable.
PI_WX="http://192.168.2.174"
TIMEOUT=5

code=$(curl -s -o /dev/null -w '%{http_code}' -m "$TIMEOUT" "$PI_WX/data/wind.json" 2>/dev/null)
if [[ "$code" == "200" ]]; then
  echo "OK: pi-wx reachable (HTTP $code)"
  exit 0
else
  echo "FAIL: pi-wx unreachable or error (HTTP $code)"
  exit 1
fi
