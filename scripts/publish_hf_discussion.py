#!/usr/bin/env python3
"""Post the Muse Spark on-2-Sparks summary as a discussion on a Hugging Face repo.

Why a discussion and not an article: HF Blog Articles require a PRO subscription
(or Team/Enterprise org membership) and can only be created through the web UI,
whereas repo discussions are API-publishable. A discussion on the GGUF repo also
lands in front of the people actually running this model.

Auth: `hf auth login` first (token goes in the prompt, never in chat). The script
refuses to run logged out rather than failing with an opaque 401.

Usage:
  scripts/publish_hf_discussion.py --dry-run     # print what would be sent
  scripts/publish_hf_discussion.py               # post it
  scripts/publish_hf_discussion.py --repo meta-models/Muse-Spark-Open-816B-A42B
"""
import argparse
import sys

REPO_DEFAULT = "unsloth/Muse-Spark-Open-816B-A42B-GGUF"

TITLE = "Two DGX Sparks run this 816B model at ~7 tok/s across two nodes"

BODY = """Ran `UD-IQ1_M` across two GB10 Sparks with `llama.cpp` RPC over the 200 GbE fabric \
(RoCEv2 negotiated, not the TCP fallback), 32K context, q8_0 K/V:

| | |
|---|---|
| decode | **6.76-7.01 tok/s**, flat across prompt lengths |
| prefill | 26 tok/s @ 28 tok -> **263 tok/s** @ 9,146 tok |
| TTFT | 1.08 s -> 34.7 s as the prompt grows |
| load | 10 min 48 s |
| free while serving 32K | ~10 GB (head), ~9 GB (peer) |
| functional | tool calls parse cleanly; reasoning works and eats the token budget |

Notes that might be useful to others doing this:

- `UD-IQ1_M` at 32K is the configuration to use. `UD-IQ2_XXS` does load and serve
  at 8K, with 1.90 GiB free on the peer; at 32K it needs roughly 1.53 GiB more
  than the peer has, so I did not run it. Decode is ~7.0 tok/s at either quant,
  because you are bound on the 42B active parameters, so the extra bit costs
  memory and buys nothing at inference time.
- Download the GGUF **once**, on the head node. `rpc-server` takes no model
  argument - it is a pure compute endpoint - so the pair streams ~195 GB once
  rather than once per node.
- The quant's choice to keep the latent projections and attention gate at Q8_0 is
  doing real work: no repetition loops at IQ1_M, which is the usual failure mode
  at these bit rates.

Scripts, raw logs and the full table (including the things I did *not* measure)
are here: https://github.com/jlacroix82/muse-spark-open-2x-dgx-spark

Thanks for publishing this quant - it is the only way this model fits on two
Sparks at all."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO_DEFAULT)
    ap.add_argument("--title", default=TITLE)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.dry_run:
        print(f"would post to: {a.repo}\ntitle: {a.title}\n\n{BODY}")
        return 0

    try:
        from huggingface_hub import HfApi, whoami
    except ImportError:
        print("huggingface_hub not importable. Use a python that has it, e.g.\n"
              "  ~/dev/realtime-voice/venv/bin/python scripts/publish_hf_discussion.py",
              file=sys.stderr)
        return 4
    try:
        user = whoami()["name"]
    except Exception as exc:
        print(f"Not logged in ({exc}). Run `hf auth login` first "
              f"(paste the token into the prompt, not into chat).", file=sys.stderr)
        return 3

    api = HfApi()
    # Don't spam: if a discussion with this title already exists, stop.
    try:
        for d in api.get_repo_discussions(repo_id=a.repo):
            if d.title.strip().lower() == a.title.strip().lower():
                print(f"already present: {a.repo} discussion #{d.num} "
                      f"({d.status}) - nothing to do")
                return 0
    except Exception as exc:
        print(f"could not list existing discussions ({exc}); continuing to post")

    url = api.create_discussion(repo_id=a.repo, title=a.title, description=BODY)
    print(f"posted as {user}: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())