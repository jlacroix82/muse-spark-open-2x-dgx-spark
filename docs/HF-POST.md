# Hugging Face placement for this repo

Two possible surfaces, and only one of them is automatable:

| surface | who can publish | how | needs |
|---|---|---|---|
| **Discussion on a model repo** | anyone with an HF account | `HfApi.create_discussion` (API) | HF login |
| Blog Article | personal namespace: confirmed email **and** PRO *or* Team/Enterprise membership | web UI at `huggingface.co/new-blog` | PRO subscription; no API |

Recommendation: **do the discussion.** It puts the numbers where people looking at
this GGUF already are, and it is the only one that can be scripted.

## 1. Discussion on the GGUF repo (recommended)

Target repo: `unsloth/Muse-Spark-Open-816B-A42B-GGUF`
Optional second target: `meta-models/Muse-Spark-Open-816B-A42B` (gated, so a
discussion there reaches fewer people).

```bash
# once, on this machine (paste the token into the prompt, not into chat):
hf auth login

# then post (dry run first — prints the body without sending):
scripts/publish_hf_discussion.py --dry-run
scripts/publish_hf_discussion.py
```

### Title

Two DGX Sparks run this 816B model at ~7 tok/s across two nodes

### Body

Ran `UD-IQ1_M` across two GB10 Sparks with `llama.cpp` RPC over the 200 GbE
fabric (RoCEv2 negotiated, not the TCP fallback), 32K context, q8_0 K/V:

| | |
|---|---|
| decode | **6.76–7.01 tok/s**, flat across prompt lengths |
| prefill | 26 tok/s @ 28 tok → **263 tok/s** @ 9,146 tok |
| TTFT | 1.08 s → 34.7 s as the prompt grows |
| load | 10 min 48 s |
| free while serving 32K | ~10 GB (head), ~9 GB (peer) |
| functional | tool calls parse cleanly; reasoning works and eats the token budget |

Notes that might be useful to others doing this:

- `UD-IQ1_M` at 32K is the configuration to use. `UD-IQ2_XXS` does load and
  serve — at 8K, with 1.90 GiB free on the peer. At 32K it needs roughly 1.53 GiB
  more than the peer has, so I didn't run it. Decode is ~7.0 tok/s at either
  quant, because you're bound on the 42B active parameters, so the extra bit
  costs memory and buys nothing at inference time.
- Download the GGUF **once**, on the head node. `rpc-server` takes no model
  argument — it is a pure compute endpoint — so the pair streams ~195 GB once
  rather than once per node.
- The quant's choice to keep the latent projections and attention gate at Q8_0
  is doing real work: no repetition loops at IQ1_M, which is the usual failure
  mode at these bit rates.

Scripts, raw logs and the full table (including the things I did *not* measure)
are here: https://github.com/jlacroix82/muse-spark-open-2x-dgx-spark

Thanks for publishing this quant — it is the only way this model fits on two
Sparks at all.

## 2. Blog Article (only if you have PRO)

If `hf auth whoami` shows a PRO subscription, go to
<https://huggingface.co/new-blog>, pick your personal namespace, and paste the
same body. Two notes from HF's guidelines: articles should either explain a
concept or announce an open artifact — this one qualifies as the former — and the
"Article(s) mentioning …" sidebar only links when the **article author owns the
repo being mentioned**, so linking `unsloth/...` from your own article will not
add a sidebar entry on unsloth's page. Link the GitHub repo instead.