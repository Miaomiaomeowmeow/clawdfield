#!/bin/sh
# Clawdfield - double-click (macOS) or run ./start.command (Linux). Original work: Miaomiao, CC BY-NC-SA 4.0
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then exec python3 server.py --open; fi
if command -v python >/dev/null 2>&1; then exec python server.py --open; fi
echo "Python was not found. Install it from https://www.python.org/downloads/ and run this again."
