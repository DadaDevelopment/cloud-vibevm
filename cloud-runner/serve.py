import http.server, functools, sys
d, p = sys.argv[1], int(sys.argv[2])
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=d)
http.server.ThreadingHTTPServer(("0.0.0.0", p), h).serve_forever()
