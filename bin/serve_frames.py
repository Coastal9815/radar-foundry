#!/usr/bin/env python3
"""HTTP server for radar frames and players. Serves combined root at http://0.0.0.0:8080/
Uses ThreadingHTTPServer so one slow client cannot block others. Socket timeout prevents hung connections.
Proxies /pi-wx-data/* to pi-wx (192.168.2.174) for master-mrw and other dashboards."""
import http.server
import os
import socketserver
import sys
import time
import urllib.request

PORT = 8080
PI_WX_BASE = "http://192.168.2.174"
SOCKET_TIMEOUT = 30  # seconds; prevents hung clients from holding connections forever
EXTERNAL_RADAR = "/Volumes/WX_SCRATCH/mrw/radar"

def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _serve_root():
    """Combined root: radar (KCLX/KJAX) + player + basemaps."""
    root = os.path.join(_project_root(), "serve_root")
    if not os.path.isdir(root):
        return None
    # Must have KCLX or KJAX (radar) and player
    has_radar = os.path.exists(os.path.join(root, "KCLX")) or os.path.exists(os.path.join(root, "KJAX"))
    if not has_radar:
        return None
    if not os.path.isdir(os.path.join(root, "player")):
        return None
    return root

def _radar_only():
    if os.path.isdir(EXTERNAL_RADAR):
        return EXTERNAL_RADAR
    return None

def _choose_dir():
    return _serve_root() or _radar_only()

def _wait_for_dir(max_wait_sec=120):
    for _ in range(max_wait_sec):
        d = _choose_dir()
        if d:
            return d
        time.sleep(1)
    return None

DIR = _wait_for_dir() or _choose_dir()
if DIR is None:
    print("serve_frames: no radar dir available", file=sys.stderr)
    sys.exit(1)

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def handle_one_request(self):
        self.connection.settimeout(SOCKET_TIMEOUT)
        super().handle_one_request()

    def do_GET(self):
        path = (self.path or "").split("?")[0]
        if path.startswith("/pi-wx-data/"):
            self._proxy_pi_wx(path)
            return
        if path == "/drought-data/chatham.json":
            self._proxy_drought(path)
            return
        if path == "/api/air/summary":
            self._serve_air_api(path)
            return
        if path == "/api/celestial/summary":
            self._serve_celestial_api(path)
            return
        super().do_GET()

    def _proxy_pi_wx(self, path):
        """Proxy /pi-wx-data/foo -> http://192.168.2.174/foo"""
        suffix = path[len("/pi-wx-data"):]
        url = PI_WX_BASE + suffix
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "radar-foundry-serve-frames/1"})
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
                self.send_response(200)
                self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
                self.send_header("Cache-Control", "no-cache, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except Exception as e:
            self.send_error(502, f"pi-wx proxy error: {e}")

    def _proxy_drought(self, path):
        """Drought at MRW coords via USDM ArcGIS point query + county stats fallback."""
        import json as _json

        MRW_LAT, MRW_LON = 31.919, -81.076
        ARCGIS_URL = (
            "https://services5.arcgis.com/0OTVzJS4K09zlixn/arcgis/rest/services/"
            "USDM_current/FeatureServer/0/query"
            f"?geometry={MRW_LON},{MRW_LAT}&geometryType=esriGeometryPoint"
            "&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=DM"
            "&returnGeometry=false&f=json"
        )

        point_dm = None
        try:
            req = urllib.request.Request(ARCGIS_URL, headers={
                "User-Agent": "radar-foundry-serve-frames/1"
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                data = _json.loads(r.read().decode())
            features = data.get("features", [])
            dm_vals = [f["attributes"]["DM"] for f in features
                       if "attributes" in f and "DM" in f["attributes"]]
            if dm_vals:
                point_dm = max(dm_vals)
        except Exception:
            pass

        # Also fetch county stats for backward compatibility
        from datetime import datetime
        now = datetime.now()
        today = f"{now.month}/{now.day}/{now.year}"
        start = f"{now.month}/1/{now.year}"
        county_url = (
            "https://usdmdataservices.unl.edu/api/CountyStatistics/"
            "GetDroughtSeverityStatisticsByAreaPercent"
            f"?aoi=13051&startdate={start}&enddate={today}&statisticsType=1"
        )
        county_data = []
        try:
            req = urllib.request.Request(county_url, headers={
                "User-Agent": "radar-foundry-serve-frames/1",
                "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                county_data = _json.loads(r.read().decode())
        except Exception:
            pass

        result = {"point_dm": point_dm, "county": county_data}
        body = _json.dumps(result).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_air_api(self, path):
        """Serve /api/air/summary: PM, ozone, smoke (NOAA HMS), saharan dust, pollen (server-side)."""
        import json
        proj = _project_root()
        if str(proj) not in sys.path:
            sys.path.insert(0, str(proj))
        try:
            from bin.air_api import fetch_summary
        except ImportError:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "air_api module not available"}).encode())
            return
        try:
            data = fetch_summary()
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, max-age=300")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _serve_celestial_api(self, path):
        """Serve /api/celestial/summary: sunrise, sunset, day_length, moonrise, moonset, next_season_start."""
        import json
        proj = _project_root()
        if str(proj) not in sys.path:
            sys.path.insert(0, str(proj))
        try:
            from bin.celestial_api import fetch_summary
        except ImportError:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "celestial_api module not available"}).encode())
            return
        try:
            data = fetch_summary()
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, max-age=300")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def end_headers(self):
        path = (self.path or "").split("?")[0]
        if "/basemaps/" in path or "/KCLX/" in path or "/KJAX/" in path or path == "/alerts.json" or path == "/lightning_points.geojson" or path == "/lightning_points_v2.geojson" or path == "/lightning_points_xweather_local.geojson" or path == "/lightning_range_rings.geojson" or "/player/" in path or "/satellite/" in path:
            # Player content: no-store so dashboard changes show immediately after sync
            cache = "no-store, no-cache, must-revalidate" if "/player/" in path else "no-cache, must-revalidate"
            self.send_header("Cache-Control", cache)
            if "/player/" in path:
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    time.sleep(3)  # let previous process release port on restart
    print(f"serve_frames: serving {DIR} at http://0.0.0.0:{PORT}/ (threaded, {SOCKET_TIMEOUT}s timeout)", file=sys.stderr)
    if "serve_root" in DIR:
        print("  Players: /player/kclx/  /player/kjax/  /player/master-mrw/  (pi-wx proxy: /pi-wx-data/)", file=sys.stderr)
    with ThreadedHTTPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
