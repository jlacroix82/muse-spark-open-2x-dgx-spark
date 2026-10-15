#!/usr/bin/env bash
# Parallel GGUF shard fetcher: one aria2c per missing shard, then size verification.
# usage: bash fetch_shards_par.sh <QUANT> <DEST_DIR> [CONNS_PER_SHARD]
set -uo pipefail

QUANT="${1:?quant}"; DEST="${2:?dest}"; CONN="${3:-8}"
REPO="unsloth/Muse-Spark-Open-816B-A42B-GGUF"
mkdir -p "$DEST"
API="/tmp/api_${QUANT}.json"; LIST="/tmp/par_${QUANT}.txt"

curl -sS --max-time 90 "https://huggingface.co/api/models/${REPO}?blobs=true" -o "$API" || { echo "API_FAIL"; exit 4; }
python3 - "$QUANT" > "$LIST" <<'PY'
import json, sys
q = sys.argv[1]
d = json.load(open(f"/tmp/api_{q}.json"))
rows = sorted([s for s in d['siblings'] if s['rfilename'].startswith(q + '/') and s['rfilename'].endswith('.gguf')],
              key=lambda x: x['rfilename'])
for s in rows:
    print(s['rfilename'], s.get('size') or 0)
PY

echo "quant=$QUANT shards=$(wc -l < "$LIST") dest=$DEST conns_per_shard=$CONN $(date +%H:%M:%S)"
pids=()
while read -r rel size; do
  name=$(basename "$rel"); out="$DEST/$name"
  cur=$(stat -c%s "$out" 2>/dev/null || echo 0)
  if [ "$cur" -ge "$size" ] && [ "$size" -gt 0 ]; then echo "SKIP $name already complete ($((cur / 1000000))MB)"; continue; fi
  echo "START $name have=$((cur / 1000000))MB want=$((size / 1000000))MB"
  (
    for a in $(seq 1 40); do
      c=$(stat -c%s "$out" 2>/dev/null || echo 0)
      if [ "$c" -ge "$size" ] && [ "$size" -gt 0 ]; then break; fi
      echo "  $name attempt=$a have=$((c / 1000000))MB $(date +%H:%M:%S)"
      aria2c -c -x "$CONN" -s "$CONN" -k 4M --file-allocation=none --summary-interval=120 \
             --console-log-level=warn --max-tries=8 --retry-wait=5 \
             -d "$DEST" -o "$name" \
             "https://huggingface.co/${REPO}/resolve/main/${QUANT}/${name}?download=true" || true
      sleep 3
    done
  ) &
  pids+=($!)
done < "$LIST"

echo "launched ${#pids[@]} fetcher(s) $(date +%H:%M:%S)"
wait
echo "=== all fetchers returned $(date +%H:%M:%S) ==="

python3 - "$QUANT" "$DEST" <<'PY'
import json, os, sys
q, dest = sys.argv[1], sys.argv[2]
d = json.load(open(f"/tmp/api_{q}.json"))
want = {os.path.basename(s['rfilename']): (s.get('size') or 0)
        for s in d['siblings'] if s['rfilename'].startswith(q + '/') and s['rfilename'].endswith('.gguf')}
bad = 0
for n, sz in sorted(want.items()):
    p = os.path.join(dest, n)
    got = os.path.getsize(p) if os.path.exists(p) else 0
    ok = got == sz
    bad += (not ok)
    print(f"  {'OK ' if ok else 'BAD'} {n} got={got} want={sz}")
print("VERIFY_OK" if bad == 0 else f"VERIFY_BAD count={bad}")
PY