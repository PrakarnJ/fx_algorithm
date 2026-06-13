"""
Serve the dashboard with no-cache headers so a regenerated data.json /
app.js is always picked up on reload (plain http.server caches aggressively).

Run: python report/serve.py [--port 8765]
"""
import argparse
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    directory = str(Path(__file__).parent)
    handler = lambda *a, **k: NoCacheHandler(*a, directory=directory, **k)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Dashboard (no-cache) → http://localhost:{args.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
