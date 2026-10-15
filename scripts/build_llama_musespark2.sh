#!/usr/bin/env bash
# Build llama.cpp with Muse Spark Open support (PR #30616, pre-merge) + CUDA + RPC.
# Shallow clone, retrying on network failure.  Usage: bash build_llama_musespark2.sh
set -uo pipefail

BRANCH="muse-spark-open"
REPO="https://github.com/ServeurpersoCom/llama.cpp"
DIR="$HOME/llama.cpp-musespark"
export PATH=/usr/local/cuda/bin:$PATH
JOBS="${JOBS:-12}"

for i in $(seq 1 8); do
  if [ -d "$DIR/.git" ]; then
    if git -C "$DIR" fetch --depth 1 origin "$BRANCH" 2>&1 | tail -2 && git -C "$DIR" checkout -f "$BRANCH" 2>&1 | tail -1; then
      echo "reused existing clone (attempt $i)"; break
    fi
  fi
  rm -rf "$DIR"
  echo "clone attempt $i/8 $(date +%H:%M:%S)"
  if git clone --depth 1 --branch "$BRANCH" "$REPO" "$DIR" 2>&1 | tail -3; then
    [ -d "$DIR/.git" ] && break
  fi
  sleep 15
done
[ -d "$DIR/.git" ] || { echo "CLONE_FAILED after 8 attempts"; exit 3; }
cd "$DIR" || exit 3
echo "HEAD=$(git rev-parse HEAD)"
git log -1 --format="%h %ad %s" --date=iso

for ARCH in 121a 121; do
  echo "=== configure/build: CUDA arch $ARCH, jobs=$JOBS $(date +%H:%M:%S) ==="
  rm -rf build
  if cmake -B build -DCMAKE_BUILD_TYPE=Release \
        -DGGML_CUDA=ON -DGGML_RPC=ON -DLLAMA_CURL=ON \
        -DCMAKE_CUDA_ARCHITECTURES="$ARCH" \
        -DLLAMA_BUILD_TESTS=OFF >"/tmp/cmake_cfg_$ARCH.log" 2>&1 \
     && cmake --build build -j"$JOBS" >"/tmp/cmake_build_$ARCH.log" 2>&1; then
    echo "BUILD_OK arch=$ARCH"
    ls build/bin/ | tr '\n' ' '; echo
    ./build/bin/llama-server --version 2>&1 | head -4
    ./build/bin/rpc-server --help 2>&1 | head -6
    exit 0
  fi
  echo "BUILD_FAILED arch=$ARCH — tail:"
  tail -30 "/tmp/cmake_build_$ARCH.log"
  tail -5 "/tmp/cmake_cfg_$ARCH.log"
done
exit 1