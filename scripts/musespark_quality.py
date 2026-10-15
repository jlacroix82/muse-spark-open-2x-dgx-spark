#!/usr/bin/env python3
"""Spot checks against the live Muse Spark Open server (IQ1_M, 2-node RPC).

These are SPOT CHECKS, not a benchmark: a handful of items with objectively
checkable answers, run to catch catastrophic quant damage. Report them as such.
"""
import json
import re
import time
import urllib.request

URL = "http://127.0.0.1:8080/v1/chat/completions"

ITEMS = [
    ("arithmetic", "A batch of 7 orders ships in boxes of 3. How many boxes are needed, "
                   "and how many slots are left in the last box? Answer as 'N boxes, M slots'.", "3 boxes, 2 slots"),
    ("coding", "Write a Python one-liner that returns the second largest distinct value in a "
               "list L. Code only, no explanation.", "sorted(set(L))"),
    ("logic", "If all Bloops are Razzies and no Razzies are Ziffs, can a Bloop be a Ziff? "
              "Answer yes or no, then one sentence why.", "no"),
    ("instruction", "Reply with exactly the three words: alpha bravo charlie. Nothing else.",
                    "alpha bravo charlie"),
    ("knowledge", "What does the acronym RoCE stand for in networking? One line.",
                  "RDMA over Converged Ethernet"),
]


def ask(prompt, max_tokens=320):
    payload = {"messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 1.0, "top_p": 1.0,
               "chat_template_kwargs": {"reasoning_effort": "low"}}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1200) as r:
        d = json.loads(r.read())
    return d, time.time() - t0


for name, prompt, expect in ITEMS:
    d, w = ask(prompt)
    msg = d["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    reasoning = (msg.get("reasoning_content") or "")
    t = d.get("timings", {})
    hit = expect.lower() in content.lower()
    print(f"--- {name}  {'PASS' if hit else 'CHECK'}  ({w:.1f}s, "
          f"{t.get('predicted_per_second', 0):.2f} tok/s, {t.get('predicted_n', 0)} tok) ---")
    print(f"  expect: {expect}")
    print(f"  got   : {content[:220].replace(chr(10), ' ')}")
    if not content:
        print(f"  (empty content; reasoning len={len(reasoning)}) {reasoning[:160]}")
    print()