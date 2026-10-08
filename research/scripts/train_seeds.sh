#!/bin/sh
# Train extra LEGAL-BERT seeds; each seed resumes from its checkpoint after a failure.
cd "$(dirname "$0")/.."
export HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1
for seed in 1 2; do
  for attempt in 1 2 3; do
    .venv/bin/evigraph-research strong-text --seed "$seed" >> "reports/.strong_seed${seed}.stdout" 2>&1
    code=$?
    echo "$(date '+%F %T') seed${seed} attempt${attempt} exit ${code}" >> reports/.seeds.log
    [ "$code" -eq 0 ] && break
    sleep 30
  done
done
