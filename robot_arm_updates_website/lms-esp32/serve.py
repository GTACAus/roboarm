import http.server
import sys

class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Serving HTTP on port {port} (http://localhost:{port}/) ...")
    http.server.ThreadingHTTPServer(("", port), NoCache).serve_forever()