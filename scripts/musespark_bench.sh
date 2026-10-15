#!/usr/bin/env bash
# llama-bench across two Sparks over RPC. Requires ggml-rpc-server running on both nodes.
# Tunable: MODEL_DIR PEER TS (tensor split, e.g. "1,1") BIN OUT
set -uo pipefail
BIN="${BIN:-$HOME/llama.cpp-musespark/build/bin}"
MODEL_DIR="${MODEL_DIR:-$HOME/models/Muse-Spark-Open-816B-A42B-GGUF/UD-IQ1_M}"
PEER="${PEER:-10.0.1.15}"
OUT="${OUT:-$HOME/musespark_bench.csv}"
TS="${TS:-}"
MODEL=$(ls "$MODEL_DIR"/*-00001-of-*.gguf 2>/dev/null | head -1)
[ -n "$MODEL" ] || { echo "NO_MODEL in $MODEL_DIR"; exit 3; }
echo "bench model=$MODEL peer=$PEER ts=${TS:-default} node=$(hostname) $(date +%H:%M:%S)"

TS_ARG=()
[ -n "$TS" ] && TS_ARG=(-ts "$TS")

"$BIN/llama-bench" \
  -m "$MODEL" \
  --rpc "$PEER:50052,127.0.0.1:50052" \
  -ngl 99 -sm layer -fa on \
  "${TS_ARG[@]}" \
  -p 512,2048 -n 128 -r 3 -o csv 2>&1 | tee "$OUT"