#!/bin/sh
# Starts a local server for MEDvital (no caching, stores feedback) and opens it in the default browser.
cd "$(dirname "$0")"
PORT=8080
(sleep 1; open "http://localhost:$PORT") &
if command -v node >/dev/null 2>&1; then PORT=$PORT exec node server.mjs; fi
echo "Node.js not found: falling back to a plain server (feedback button cannot save)."
exec python3 -m http.server $PORT -d public
