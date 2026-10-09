#!/bin/sh
# Wait for the seed training loop, then run the protocol 3.0 dry run (final_test stays sealed).
cd "$(dirname "$0")/.." || exit 1
while kill -0 "$1" 2>/dev/null; do sleep 60; done
echo "$(date '+%F %T') seeds finished; dry run" >> reports/.seeds.log
uv run --no-sync evigraph-research final --dry-run > reports/.final_dryrun.log 2>&1
echo "$(date '+%F %T') dry run exit $?" >> reports/.seeds.log
