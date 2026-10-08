#!/usr/bin/env bash
# Local PostgreSQL cluster for development and tests, kept inside the project directory.
# Usage: scripts/dev_db.sh start|stop|status|url
set -euo pipefail
export LC_ALL=C  # postmaster refuses to start on macOS without a valid locale

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/.pgdata"
PORT="${EVIGRAPH_PG_PORT:-54329}"
BIN="${EVIGRAPH_PG_BIN:-/opt/homebrew/bin}"

case "${1:-}" in
  start)
    if [ ! -d "$DATA" ]; then
      "$BIN/initdb-17" -D "$DATA" -U evigraph --auth=trust --encoding=UTF8 --locale=C >/dev/null
    fi
    if ! "$BIN/pg_ctl-17" -D "$DATA" status >/dev/null 2>&1; then
      "$BIN/pg_ctl-17" -D "$DATA" -l "$DATA/server.log" -w \
        -o "-p $PORT -k $DATA -c listen_addresses=127.0.0.1" start >/dev/null
    fi
    "$BIN/createdb-17" -h 127.0.0.1 -p "$PORT" -U evigraph evigraph 2>/dev/null || true
    echo "postgresql+psycopg://evigraph@127.0.0.1:$PORT/evigraph"
    ;;
  stop)
    "$BIN/pg_ctl-17" -D "$DATA" -m fast stop
    ;;
  status)
    "$BIN/pg_ctl-17" -D "$DATA" status
    ;;
  url)
    echo "postgresql+psycopg://evigraph@127.0.0.1:$PORT/evigraph"
    ;;
  *)
    echo "usage: $0 start|stop|status|url" >&2
    exit 2
    ;;
esac
