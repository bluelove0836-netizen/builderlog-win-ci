"""운영 서버처럼 charset=utf-8 로 내주는 로컬 서버(127.0.0.1 만)."""
import http.server, sys
class H(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        return "text/plain; charset=utf-8"
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), lambda *a: H(*a, directory=sys.argv[2])).serve_forever()
