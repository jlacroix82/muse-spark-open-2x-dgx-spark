#!/usr/bin/env bash
# Robust GGUF shard fetcher for public HF repos: resumes, retries, verifies sizes.
# usage: bash fetch_shards.sh <QUANT> <DEST_DIR>
set -uo pipefail

QUANT="${1:?quant}"; DEST="${2:?dest}"
REPO="unsloth/Muse-Spark-Open-816B-A42B-GGUF"
mkdir -p "$DEST"
LIST="/tmp/shards_${QUANT}.txt"

curl -sS --max-time 90 "https://huggingface.co/api/models/${REPO}?blobs=true" > "/tmp/api_${QUANT}.json" || { echo "API_FAIL"; exit 4; }
python3 - "$QUANT" > "$LIST" <<'PY'
import json, sys
q = sys.argv[1]
d = json.load(open(f"/tmp/api_{q}.json"))
rows = [(s['rfilename'], s.get('size') or 0) for s in d['siblings']
        if s['rfilename'].startswith(q + '/') and s['rfilename'].endswith('.gguf')]
for n, sz in sorted(rows):
    print(n, sz)
PY

total=$(wc -l < "$LIST")
[ "$total" -gt 0 ] || { echo "NO_SHARDS_FOR_$QUANT"; exit 4; }
echo "quant=$QUANT shards=$total dest=$DEST fetcher=$(command -v aria2c >/dev/null && echo aria2c || echo curl)"

i=0
while read -r rel size; do
  i=$((i + 1)); name=$(basename "$rel"); out="$DEST/$name"
  url="https://huggingface.co/${REPO}/resolve/main/${QUANT}/${name}?download=true"
  for attempt in $(seq 1 40); do
    cur=$(stat -c%s "$out" 2>/dev/null || echo 0)
    if [ "$cur" -ge "$size" ] && [ "$size" -gt 0 ]; then break; fi
    echo "[$i/$total] $name attempt=$attempt have=$((cur / 1000000))MB of $((size / 1000000))MB $(date +%H:%M:%S)"
    if command -v aria2c >/dev/null 2>&1; then
      aria2c -c -x 8 -s 8 -k 4M --file-allocation=none --summary-interval=60 \
             --console-log-level=warn --max-tries=8 --retry-wait=5 \
             -d "$DEST" -o "$name" "$url" || true
    else
      curl -sS -L -C - --max-time 5400 --retry 5 --retry-all-errors -o "$out" "$url" || true
    fi
    sleep 3
  done
  final=$(stat -c%s "$out" 2>/dev/null || echo 0)
  if [ "$final" -ge "$size" ] && [ "$size" -gt 0 ]; then
    echo "[$i/$total] OK $name $((final / 1000000000))GB"
  else
    echo "[$i/$total] FAIL $name $((final / 1000000000))GB of $((size / 1000000000))GB"
  fi
done < "$LIST"

echo "=== final listing ==="
ls -l "$DEST"
echo "=== VERIFY ==="
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
    print(f"  {'OK  ' if ok else 'BAD '} {n} got={got} want={sz}")
print("VERIFY_OK" if bad == 0 else f"VERIFY_BAD count={bad}")
PY