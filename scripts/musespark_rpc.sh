#!/usr/bin/env bash
# Start a ggml-rpc-server (compute endpoint only - no model file needed) on this node.
# Run this in the FOREGROUND of a tracked session on every node in the pair.
set -uo pipefail
BIN="${BIN:-$HOME/llama.cpp-musespark/build/bin}"
PORT="${PORT:-50052}"
DEV="${DEV:-CUDA0}"
echo "rpc-server on $(hostname) port=$PORT device=$DEV bin=$BIN"
exec "$BIN/ggml-rpc-server" -H 0.0.0.0 -p "$PORT" -d "$DEV"