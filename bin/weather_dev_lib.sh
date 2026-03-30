#!/usr/bin/env bash
# Shared helpers for MRW local dev port safety (sourced by other scripts).
# Modeled after CCP_Core scripts/lib/port-check.cjs — macOS uses lsof.

weather_get_tcp_listener() {
  local port="$1"
  local out line
  out="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null)" || true
  line="$(echo "$out" | awk 'NR==2 {print $1"\t"$2}')"
  if [[ -z "$line" ]]; then
    return 1
  fi
  echo "$line"
  return 0
}

weather_listener_program() {
  cut -f1 <<<"$1"
}

weather_listener_pid() {
  cut -f2 <<<"$1"
}

weather_process_cmdline() {
  local pid="$1"
  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
    echo "(could not read process command)"
    return
  fi
  ps -p "$pid" -o command= 2>/dev/null | sed 's/^ *//'
}

# Best-effort: radar-foundry serve_frames.py (python ... serve_frames.py)
_weather_looks_like_serve_frames() {
  local cmd="$1"
  [[ "$cmd" == *"serve_frames.py"* ]] || [[ "$cmd" == *"serve_frames"* && "$cmd" == *"python"* ]]
}

# Best-effort: moonriverweather / Next dev
_weather_looks_like_next_mrw() {
  local cmd="$1"
  [[ "$cmd" == *"next dev"* ]] || [[ "$cmd" == *"moonriverweather-public"* && "$cmd" == *"node"* ]]
}

# Best-effort: Coastal Care Core backend (same Mac — often port 3001)
_weather_looks_like_ccp_backend() {
  local cmd="$1"
  [[ "$cmd" == *"CCP_Core"* && "$cmd" == *"backend"* ]] || [[ "$cmd" == *"/backend/"* && "$cmd" == *"server.ts"* ]] || [[ "$cmd" == *"coastal-care-core-backend"* ]]
}

weather_describe_port() {
  local name="$1"
  local port="$2"
  local kind="$3"
  echo "--- ${name} (port ${port}) ---"
  local row=""
  if row="$(weather_get_tcp_listener "$port")"; then
    :
  else
    row=""
  fi
  if [[ -z "$row" ]]; then
    echo "Status: nothing listening (free)"
    echo ""
    return 0
  fi
  local prog pid cmd ours
  prog="$(weather_listener_program "$row")"
  pid="$(weather_listener_pid "$row")"
  cmd="$(weather_process_cmdline "$pid")"
  ours="unknown / other project (do not kill blindly)"
  case "$kind" in
    serve_frames)
      if _weather_looks_like_serve_frames "$cmd"; then ours="matches this workspace’s usual serve_frames (radar-foundry)"; fi
      ;;
    moonriverweather)
      if _weather_looks_like_next_mrw "$cmd"; then ours="matches this workspace’s usual Next dev (moonriverweather-public)"; fi
      if _weather_looks_like_ccp_backend "$cmd"; then ours="WARNING: looks like CCP_Core API — if this is MRW’s dev port, stop Core or use a different MOONRIVERWEATHER_DEV_PORT"; fi
      ;;
  esac
  echo "Status: in use — ${ours}"
  echo "  Program: ${prog}  PID: ${pid}"
  echo "  ${cmd}"
  echo ""
}

weather_assert_port_free_or_ours() {
  local port="$1"
  local kind="$2"
  local row=""
  if row="$(weather_get_tcp_listener "$port")"; then
    :
  else
    row=""
  fi
  if [[ -z "$row" ]]; then
    return 0
  fi
  local pid cmd
  pid="$(weather_listener_pid "$row")"
  cmd="$(weather_process_cmdline "$pid")"
  case "$kind" in
    serve_frames)
      if _weather_looks_like_serve_frames "$cmd"; then
        echo "serve_frames already appears to be listening on port ${port} (PID ${pid})."
        echo "If http://127.0.0.1:${port}/player/ responds, you do not need another server."
        echo "To restart: stop that process, then run this script again."
        exit 0
      fi
      ;;
    moonriverweather)
      if _weather_looks_like_next_mrw "$cmd"; then
        echo "moonriverweather-public Next dev already appears to be running on port ${port} (PID ${pid})."
        echo "Open http://127.0.0.1:${port}/ — or stop that process to start fresh."
        exit 0
      fi
      ;;
  esac

  echo "" >&2
  echo "Port ${port} is already in use — not by the usual MRW ${kind} dev process." >&2
  echo "Do not stop that process until you confirm what owns it (CCP_Core, another app, etc.)." >&2
  echo "" >&2
  echo "  PID ${pid}" >&2
  echo "  ${cmd}" >&2
  echo "" >&2
  echo "Registry: radar-foundry/docs/local-dev/WEATHER_DEV_PORTS.md" >&2
  echo "" >&2
  exit 1
}
