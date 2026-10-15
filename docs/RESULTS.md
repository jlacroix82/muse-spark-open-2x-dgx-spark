# Muse Spark Open 816B-A42B on two DGX Sparks — measured results

All numbers below were measured on this hardware, not estimated. Anything not measured
is explicitly marked as open.

## Pinned configuration

| Component | Identity |
|---|---|
| Hardware | 2 × NVIDIA DGX Spark (GB10), 121.6 GB unified memory each |
| Fabric | ConnectX-7 200 GbE, `enp1s0f0np0` = 10.0.1.14 / 10.0.1.15, RoCEv2 |
| Engine | llama.cpp PR #30616, fork `ServeurpersoCom/llama.cpp`, branch `muse-spark-open`, commit `335916ad3f0cab876a7a3cf16faaaaea28bf9a96` |
| Build | CUDA 13.0.88, driver 580.173.02, `-DGGML_CUDA=ON -DGGML_RPC=ON -DCMAKE_CUDA_ARCHITECTURES=121a`, build 11678 |
| Model | `unsloth/Muse-Spark-Open-816B-A42B-GGUF` → `UD-IQ1_M`, 6 shards, 208.9 GB on disk (194.6 GiB) |
| Serving | `llama-server --rpc 10.0.1.15:50052,127.0.0.1:50052 -ngl 99 -c 32768 -fa on -ctk q8_0 -ctv q8_0 -np 1` |

Because llama.cpp support for this architecture is an **unmerged PR**, none of this works on
a stock llama.cpp: master registers only `muse-glimmer`.

## Bring-up timings (measured)

| Step | Value |
|---|---|
| GGUF download (6 shards, aria2c 8 connections) | 115 MB/s sustained, ~30 min total |
| Model load across both nodes | 10 min 48 s |
| RPC transport negotiated | RDMA / RoCEv2 (`dev=rocep1s0f0 gid=3 qpn=… mtu=4096`), not TCP fallback |

## Inference at concurrency 1 (measured, n_slots=1)

| Prompt | TTFT | Prefill | Decode |
|---|---|---|---|
| 28 tok | 1.08 s | 26.0 tok/s | **7.01 tok/s** (256 tok) |
| 160 tok | 3.21 s | 49.9 tok/s | **6.92 tok/s** (96 tok) |
| 650 tok (tool request) | 6.40 s | 101.6 tok/s | 6.88 tok/s (128 tok) |
| 9,146 tok | 34.7 s | **263.3 tok/s** | 6.76 tok/s (64 tok) |

Decode is stable at **6.8–7.0 tok/s** regardless of prompt length — it is memory-bandwidth
bound, as expected for a 42B-active MoE spread over two 273 GB/s nodes.

For scale on the same class of hardware: published two-Spark llama.cpp RPC numbers are
9.86 tok/s for Qwen3-Coder-480B (168 GB) and 13.16 tok/s for Llama-4-Maverick (143 GB).
This model is 194.6 GiB — bigger than either — so ~6.9 tok/s is consistent with the pattern.

## Memory (while serving 32K context)

| Node | Total | Available while serving |
|---|---|---|
| head (10.0.1.14) | 121.6 GB | **10.2 GB** |
| peer (10.0.1.15) | 121.6 GB | **8.8 GB** |

Roughly 97 GiB of weights per node plus KV + compute buffers. This is a near-ceiling
configuration: two Sparks are the smallest pair that runs this quant.

## Functional checks

- **Tool calling: passes.** A 650-token request with a `get_weather` schema returned a
  well-formed call: `{"city":"Portland, Oregon","unit":"C"}`.
- **Reasoning: works, and needs token budget.** With `max_tokens=64` the whole budget went
  to `reasoning_content` and `content` came back empty. `reasoning_effort` is settable via
  `chat_template_kwargs` (`low`/`medium`/`high`/`xhigh`); the chat template preserves
  reasoning across turns by default.
- **Concurrency at n_slots=1: serializes.** 3 simultaneous requests took 22.0 s wall in
  total, aggregate 6.54 tok/s — i.e. no throughput gain, they queue. Batching requires
  `-np > 1` (open item).

## Quality spot checks at IQ1_M (not a benchmark)

Five items with objectively checkable answers, `reasoning_effort=low`, `max_tokens=320`.
These catch catastrophic quant damage; they do not measure capability.

| Item | Result | Time |
|---|---|---|
| Coding (second-largest distinct in a list) | **pass** — `sorted(set(L))[-2]` | 40.4 s |
| Logic (syllogism) | **pass** — "No, because all Bloops are Razzies…" | 24.4 s |
| Instruction following ("exactly three words") | **pass** — `alpha bravo charlie` | 13.9 s |
| Knowledge (what RoCE stands for) | **pass** — "RDMA over Converged Ethernet" | 32.0 s |
| Arithmetic (7 orders, boxes of 3) | **inconclusive** — hit the 320-token cap mid-reasoning, `content` empty | 47.6 s |

No sign of the degenerate repetition that low-bit quantisation commonly causes — the
quantiser in PR #30616 explicitly keeps the latent projections and attention gate at Q8_0
because low-bit types turned this model's output into a repeating loop. Note that at
~6.9 tok/s every answer costs real wall-clock time, so reasoning budget is the main
usability constraint, not correctness.

## Open items

1. **The "2-bit on 256 GB" claim.** `UD-IQ2_XXS` is 210.1 GiB versus the 194.6 GiB that
   runs here, and the pair has only ~19 GB of headroom total. Expected outcome: it either
   fails to load or needs a much smaller context. Being verified, not assumed.
2. **Concurrency with `-np 4`** (4 slots × 8K context): whether batching lifts aggregate
   throughput now that the per-step weight read is amortised.
3. **`llama-bench` pp512/pp2048/tg128** in the community protocol, for comparability.
4. **Quality at IQ1_M** — how much the 1.75 bpw quant costs versus the same model at higher
   precision. Not measured yet; do not quote a quality delta that has not been tested.