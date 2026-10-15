# Muse Spark Open 816B-A42B on two DGX Sparks

A measured, reproducible recipe for running Meta's **Muse-Spark-Open-816B-A42B** (816B total /
42B active MoE) on the smallest DGX Spark pair that can hold it: **two GB10 nodes, ~121 GB
unified memory each, split over the 200 GbE fabric with llama.cpp RPC.**

Verified working: model loads, serves an OpenAI-compatible API, tool calls parse, reasoning
works. Measured numbers are in [`docs/RESULTS.md`](docs/RESULTS.md) — every figure there came
off this hardware.

## Why this needs a fork build

llama.cpp master does **not** know this architecture — it registers `muse-glimmer` only.
Muse Spark support lives in **PR #30616** (`ServeurpersoCom/llama.cpp`, branch
`muse-spark-open`). This recipe pins the exact commit it was measured on; the branch is under
active development, so treat the pin as part of the recipe, not a suggestion.

## Hard requirement: two nodes, and only two

The quant that fits is `UD-IQ1_M` — **194.6 GiB** of weights. Two GB10 nodes give ~243 GiB,
which after OS overhead, the CUDA context and KV/compute buffers lands at roughly 97 GiB of
weights per node. One Spark cannot hold it; three or four are unnecessary unless you want
more context or slots.

`rpc-server` has **no model argument** — it is a pure compute endpoint (`-H/-t/-d/-p/-c`).
The GGUF is read by the head node only and the tensors are pushed to the peer. Practical
consequence: **you download ~195 GB once per pair, not once per node.**

## Steps

### 1. Build llama.cpp with this architecture (both nodes)

```bash
bash scripts/build_llama_musespark2.sh          # pins PR #30616, CUDA 13, arch 121a, GGML_RPC=ON
```

Expect `BUILD_OK arch=121a` and `muse-spark` present in `libllama.so`. The RPC binary this
build produces is `build/bin/ggml-rpc-server` (not `rpc-server`).

### 2. Fetch the quant (head node only)

```bash
bash scripts/fetch_shards.sh UD-IQ1_M /path/to/models/Muse-Spark-Open-816B-A42B-GGUF/UD-IQ1_M
```

The script resumes, retries, and then **verifies every shard against the size declared by the
HF API** — trust the `VERIFY_OK` line, not the file listing. Use `aria2c` (the script prefers
it when present): single-stream downloads ran ~20 MB/s, eight connections ran **115 MB/s**.

Quant sizes from `unsloth/Muse-Spark-Open-816B-A42B-GGUF` (public, not gated):

| Quant | Size | Two Sparks? |
|---|---|---|
| `UD-IQ1_S` | 163.6 GiB | fits with room |
| `UD-IQ1_M` | 194.6 GiB | **fits, tight — this recipe** |
| `UD-IQ2_XXS` | 210.1 GiB | under test; only ~19 GB headroom exists |
| `UD-IQ2_S` | 256.6 GiB | no |
| `UD-Q2_K_XL` | 289.9 GiB | no |

### 3. Start the RPC endpoint on **both** nodes

```bash
bash scripts/musespark_rpc.sh      # ggml-rpc-server -H 0.0.0.0 -p 50052 -d CUDA0, foreground
```

### 4. Serve from the head node

```bash
PEER=10.0.1.15 CTX=32768 NP=4 PORT=8080 bash scripts/musespark_serve.sh
```

which runs:

```bash
llama-server -m <shard-00001-of-00006.gguf> \
  --rpc "$PEER:50052,127.0.0.1:50052" --tensor-split 50,50 \
  -ngl 99 -c 32768 -fa on --cache-type-k q8_0 --cache-type-v q8_0 \
  --host 0.0.0.0 --port 8080 --jinja --no-warmup -np 4 --metrics --slots
```

Notes that cost time to learn:
- The head node needs a **local** `ggml-rpc-server` on `127.0.0.1:50052`; both ends are RPC
  backends. Point `--rpc` at the peer *and* at localhost.
- RPC auto-negotiates **RoCEv2 RDMA** on the ConnectX-7 ports (`dev=rocep1s0f0 gid=3`), so
  keep the fabric addresses in the same subnet and don't force plain TCP.
- Load takes **~11 minutes**. Nothing is wrong while the log sits at `loading model` — that
  line is buffered; watch node memory (`~97 GiB` per node) or `/proc/<pid>/io` instead.
- Port 50052 collides with vLLM worker sockets if any vLLM job is still up on the pair.

### 5. Talk to it

```bash
curl localhost:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "messages":[{"role":"user","content":"Write a Python function that reverses a linked list."}],
  "max_tokens":512, "temperature":1.0, "top_p":1.0,
  "chat_template_kwargs":{"reasoning_effort":"low"}}'
```

Client gotchas:
- **This is a reasoning model.** `reasoning_effort` (`low`/`medium`/`high`/`xhigh`, default
  `xhigh`) is set via `chat_template_kwargs`. Reasoning arrives in `message.reasoning_content`
  and the answer in `message.content`. With a tight `max_tokens` the budget is consumed by
  reasoning and **`content` comes back empty** — budget generously or the failure looks like a
  broken model.
- Recommended sampling: `temperature=1.0`, `top_p=1.0`, `top_k` disabled.
- Tool calling works (`--jinja` + the PR's chat template); `--enable-auto-tool-choice` and a
  parser are not needed with the template in place.

## Caveats, stated plainly

- **Unmerged upstream support.** Pinned commit, actively changing branch.
- **Slow by design:** ~6.9 tok/s decode, ~263 tok/s prefill on 9k-token prompts. Fine for
  batch/agentic work with patience; not interactive.
- **Memory ceiling.** ~10 GB free per node while serving. Do not co-schedule anything else on
  the pair.
- **One slot with `-np 1`**; concurrent requests queue rather than batch. Use `-np 4`
  (`-c` is the *total* context, split across slots — `-c 32768 -np 4` = 8K/slot): measured
  **14–16 tok/s aggregate vs 6.1 at c=1**, saturating at 3–4 in-flight requests, with
  per-request decode dropping from 7.0 to ~4.1 tok/s.
- **Weights are not redistributable** under the Muse Model License — this repo ships scripts
  and numbers only, and fetches from Meta/Unsloth's own repos.

## Repo layout

```
scripts/   build, fetch, rpc, serve, bench, and the measurement probes
docs/      RESULTS.md — every measured figure, with open items listed honestly
logs/      raw logs from the measured run (serve, tests, concurrency, download verify)
results/   CSV/JSON outputs
```