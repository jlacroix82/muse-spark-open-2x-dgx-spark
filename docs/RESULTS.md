# Muse Spark Open 816B-A42B on two DGX Sparks — measured results

All numbers below were measured on this hardware, not estimated. Anything not measured
is explicitly marked as open.

## Pinned configuration

| Component | Identity |
|---|---|
| Hardware | 2 × NVIDIA DGX Spark (GB10), 121.6 GB unified memory each |
| Fabric | ConnectX-7 200 GbE, `enp1s0f0np0` = head-fabric-ip / peer-fabric-ip, RoCEv2 |
| Engine | llama.cpp PR #30616, fork `ServeurpersoCom/llama.cpp`, branch `muse-spark-open`, commit `335916ad3f0cab876a7a3cf16faaaaea28bf9a96` |
| Build | CUDA 13.0.88, driver 580.173.02, `-DGGML_CUDA=ON -DGGML_RPC=ON -DCMAKE_CUDA_ARCHITECTURES=121a`, build 11678 |
| Model | `unsloth/Muse-Spark-Open-816B-A42B-GGUF` → `UD-IQ1_M`, 6 shards, 208.9 GB on disk (194.6 GiB) |
| Serving | `llama-server --rpc peer-fabric-ip:50052,127.0.0.1:50052 -ngl 99 -c 32768 -fa on -ctk q8_0 -ctv q8_0 -np 1` |

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
| head (head-fabric-ip) | 121.6 GB | **10.2 GB** |
| peer (peer-fabric-ip) | 121.6 GB | **8.8 GB** |

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

## The "2-bit on 256 GB" claim — tested

`UD-IQ2_XXS` (210.1 GiB / 225.6 GB, all 6 shards byte-verified against the HF manifest)
**does load and serve on two Sparks — at 8K context.** Load took 11 min 52 s, slightly longer
than IQ1_M's 10 min 48 s because there are 8% more bytes to stream.

| Prompt | TTFT | Prefill | Decode |
|---|---|---|---|
| 155 tok | 2.49 s | 62.4 tok/s | **7.02 tok/s** (128 tok) |
| 372 tok | 2.74 s | 135.6 tok/s | **6.98 tok/s** (128 tok) |

Tool calling at 2-bit is intact — `{"city":"Portland, Oregon","unit":"C"}` — and `content` is
populated ("I'll fetch the Portland weather in Celsius for you.").

Decode is **the same ~7.0 tok/s as IQ1_M**. That is the expected result and a useful one: the
model is bandwidth-bound on the *active* parameters (42B), so going from 1.75 bpw to 2.0 bpw
costs nothing at inference time — you pay only in memory.

Memory headroom while serving at 8K, measured:

| Node | Free |
|---|---|
| head (IQ2_XXS shards) | 4.90 GiB |
| peer | **1.90 GiB** |

The peer is the binding constraint. KV here is 126,976 elements/token (62 layers × 16 KV heads
× 64 head_dim × K and V), i.e. 0.129 MiB/token at q8_0:

| Context | KV/node | Fits? |
|---|---|---|
| 8K | 0.53 GiB | **yes — measured** |
| 32K | 2.06 GiB | no: needs +1.53 GiB on a peer that has 1.90 GiB free (projected, not yet run) |

So the honest headline: **2-bit fits, but not at a large context** — pick `UD-IQ2_XXS` at 8K,
or `UD-IQ1_M` at 32K with ~10 GiB/node to spare. Neither is a comfortable configuration;
both are near the ceiling.

## Throughput scaling with `-np 4` (IQ1_M, 32K total context = 8K/slot)

This is the number that matters for agentic/batch use. Same server, `max_tokens=128`, requests
fired simultaneously:

| Concurrent | Per-request decode | Aggregate | vs c=1 |
|---|---|---|---|
| 1 | 7.02 tok/s | 6.08 tok/s | — |
| 2 | 5.93 / 6.08 | 10.68 tok/s | 1.76× |
| 3 | 4.91 / 4.92 | 14.30 tok/s | 2.35× |
| 4 (all slots) | 4.01–4.32 | **14.05 tok/s** | 2.31× |
| 8 (two waves) | 4.11 / 4.24 | **15.88 tok/s** | 2.61× |

**Batching is worth it.** At `n_slots=1` concurrency bought nothing (3 simultaneous requests →
6.54 tok/s aggregate, pure queueing). With `-np 4` the aggregate roughly **2.3–2.6×** the
single-stream rate and saturates at ~14–16 tok/s around 3–4 in-flight requests. The trade is
per-request latency: each stream slows from 7.0 to ~4.1 tok/s.

Interpretation: at c=1 the 42B active weights are read once per token and the GPU idles waiting
on memory; batching amortises that read across sequences, so aggregate throughput rises almost
linearly until the memory system saturates at ~16 tok/s.

## Open items

1. ~~The "2-bit on 256 GB" claim.~~ **Answered** — fits at 8K; 32K is out of reach on measured
   headroom.
2. ~~Concurrency with `-np 4`.~~ **Answered above** — 2.3–2.6× aggregate, saturating ~3–4 slots.
3. **`llama-bench` pp512/pp2048/tg128** in the community protocol, for comparability. Not run:
   each `llama-bench` invocation reloads the model (~11 min).
4. **Quality at IQ1_M vs IQ2_XXS** — whether the extra 0.25 bpw buys measurable quality. Not
   measured; do not quote a delta that has not been tested.