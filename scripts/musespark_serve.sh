#!/usr/bin/env bash
# Serve Muse Spark Open across two DGX Sparks via llama.cpp RPC.
# Head node runs this; it also runs a LOCAL ggml-rpc-server (127.0.0.1:50052).
#   MODEL_DIR / PEER / CTX / PORT / SPLIT are env-overridable.
set -uo pipefail
BIN="${BIN:-$HOME/llama.cpp-musespark/build/bin}"
MODEL_DIR="${MODEL_DIR:-$HOME/models/Muse-Spark-Open-816B-A42B-GGUF/UD-IQ1_M}"
PEER="${PEER:-}"
# No default on purpose: a wrong address here means llama-server dials a
# stranger's box, or silently falls back to single-node.
if [ -z "$PEER" ]; then
  echo "set PEER to the peer node's fabric IP (200 GbE interface)" >&2
  exit 2
fi
# No default on purpose: a wrong address here means llama-server dials a
# stranger's box, or silently falls back to single-node.
if [ -z "$PEER" ]; then
  echo "set PEER to the peer node's fabric IP (200 GbE interface)" >&2
  exit 2
fi
PORT="${PORT:-8080}"
CTX="${CTX:-32768}"
SPLIT="${SPLIT:-50,50}"
KV="${KV:-q8_0}"
NP="${NP:-1}"

MODEL=$(ls "$MODEL_DIR"/*-00001-of-*.gguf 2>/dev/null | head -1)
if [ -z "$MODEL" ]; then echo "NO_MODEL in $MODEL_DIR"; exit 3; fi
echo "model=$MODEL"
echo "peer=$PEER ctx=$CTX split=$SPLIT kv=$KV port=$PORT np=$NP node=$(hostname)"

exec "$BIN/llama-server" \
  -m "$MODEL" \
  --rpc "$PEER:50052,127.0.0.1:50052" \
  --tensor-split "$SPLIT" \
  -ngl 99 \
  -c "$CTX" \
  -fa on \
  --cache-type-k "$KV" --cache-type-v "$KV" \
  --host 0.0.0.0 --port "$PORT" \
  --jinja --no-warmup \
  -np "$NP" --metrics --slots