# Forum reply — Muse Spark Open on two DGX Sparks

**Everything between the rules is the post, exactly as it should be pasted.
The notes at the bottom are not part of it.**

**Title:** Muse Spark Open 816B on two DGX Sparks: 6.8-7.0 tok/s and 32K context, measured

---

The launch material is all GB300 NVL72, which is what it was trained on. But the
question anyone with a Spark on the desk actually has is whether an 816B model
runs at all, so I measured it instead of guessing. Short answer: yes, on **two**
Sparks, and it's fine for batch work rather than conversation.

What it took:

- Two GB10 nodes, ~121 GB unified memory each, tied together with llama.cpp RPC
  over the 200 GbE fabric (RoCEv2 negotiated, not the TCP fallback)
- `UD-IQ1_M` from the public unsloth GGUF, 194.6 GiB across 6 shards
- 32K context, q8_0 K/V, flash attention on

Two nodes is the right count. One can't hold the weights; a third buys you
context and nothing else. And since `rpc-server` takes no model argument, the
pair downloads the 195 GB once, not once per node.

Numbers, single request:

| prompt | TTFT | prefill | decode |
|---|---|---|---|
| 28 tok | 1.08 s | 26 tok/s | 7.01 tok/s |
| 160 tok | 3.21 s | 50 tok/s | 6.92 tok/s |
| 650 tok | 6.40 s | 102 tok/s | 6.88 tok/s |
| 9,146 tok | 34.7 s | 263 tok/s | 6.76 tok/s |

Decode sits at 6.8-7.0 tok/s no matter how long the prompt is, which is what you
expect when you're bandwidth-bound on the 42B active parameters across two
273 GB/s nodes. For scale, published two-Spark RPC runs get 9.86 tok/s on
Qwen3-Coder-480B (168 GB) and 13.16 on Maverick (143 GB) — this model is larger
than either, so the number falls where it should.

Load takes 10 min 48 s (the whole GGUF streams across to the peer). While serving
32K, each node is down to roughly 9-10 GB free. This is a near-ceiling setup, not
a comfortable one. Worth knowing before you plan around "128 GB": GB10 documents
a 2,046 MiB display-scanout reservation, which stops being trivia when you're
1.9 GiB from the edge.

What works, and where it hurts:

- **Tool calling is intact.** A 650-token request with a `get_weather` schema
  returned `{"city":"Portland, Oregon","unit":"C"}`.
- **Reasoning will eat your token budget.** At `max_tokens=64` the entire budget
  went to `reasoning_content` and `content` came back empty. `reasoning_effort`
  is settable through `chat_template_kwargs`; leave it low unless you have
  wall-clock to spare.
- **4 of 5 objective spot checks passed** (coding, logic, instruction following,
  knowledge). The arithmetic one hit the token cap mid-reasoning, so I'm calling
  it inconclusive, not a pass. This is not a benchmark — it's a check for
  catastrophic quant damage, which low-bit quants of this model are known to
  cause; the quantiser keeps the latent projections and attention gate at Q8_0
  for exactly that reason, and I saw no repetition loops at IQ1_M.

Where it stops: `UD-IQ2_XXS` (225.6 GB) does load and serve — at 8K context, with
**1.90 GiB left on the peer node**. At 32K it needs about 1.53 GiB more than that
node has, so I didn't run it. So: IQ1_M at 32K with ~10 GB/node spare, or IQ2_XXS
at 8K. Decode is ~7.0 tok/s either way, because you're bound on active
parameters, so the extra bit costs memory and buys nothing at inference time.

Support landed upstream: llama.cpp merged Muse Spark Open on Oct 15 (ships as
`b11671`, merge commit `ba3c05f71da8`), vision and audio towers included. I
measured on the pre-merge PR tree (`335916ad3`) and pinned it in my notes so the
numbers stay reproducible; a plain master build at or after the merge is the
supported path now. Weights are the public unsloth GGUF rather than Meta's gated
repo, and the Muse Model License applies to derivatives.

Build flags, both launch lines, the raw logs and the full measurement table —
including the items I did *not* measure — are here:

https://github.com/jlacroix82/muse-spark-open-2x-dgx-spark

I'm also curious whether a third node gets anyone a materially larger context at
2-bit, since that's the only reason I can see to add one.

---

## Posting notes (not part of the post)

- **POSTED 2026-10-16** as a new topic in **DGX Spark / GB10** (category 721) by
  `jameslacroix`:
  https://forums.developer.nvidia.com/t/muse-spark-open-816b-on-two-dgx-sparks-6-8-7-0-tok-s-and-32k-context-measured/386058
- Category note: the URL given as the destination,
  `/c/accelerated-computing/dgx-spark-gb10/719`, resolves through category **719
  "DGX Spark / GB10 User Forum"** — that is a read-only *container* (no topics of
  its own), and topic creation there is refused. The writable discussion
  categories underneath are **721 "DGX Spark / GB10"** (2,214 topics — where this
  went) and 723 "DGX Spark / GB10 Projects" (419).
- Verified as an anonymous visitor after posting: category 721, 1 post, author
  jameslacroix, the results table and 13 code spans rendered, the repo link
  intact, no internal identifiers.
- Optional follow-up not done: a short cross-link reply on NVIDIA's Muse Spark
  Open launch thread, https://forums.developer.nvidia.com/t/385980 (1 post,
  60 views at the time; the only Muse Spark topic on the forum outside this one).
- No internal hostnames, node labels, fabric addresses or file paths appear in the
  post; nodes are referred to as "head" and "peer".
- The 2,046 MiB display reservation is attributed to NVIDIA's GB10 documentation,
  not to our own measurement.
