#!/bin/sh
# Serve the viewer (it loads out/*.glb and out/*.stl, which browsers won't read from file://).
# Sends no-cache headers so a reload always picks up rebuilt models and page edits.
cd "$(dirname "$0")" && exec python3 - "${1:-8765}" <<'PY'
import http.server, sys
class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
http.server.ThreadingHTTPServer(("", int(sys.argv[1])), NoCache).serve_forever()
PY
