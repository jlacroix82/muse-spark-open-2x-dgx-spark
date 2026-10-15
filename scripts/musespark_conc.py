#!/usr/bin/env python3
"""Concurrency probe against a running llama-server.

Env: N (parallel requests, default 3), MAXTOK (default 48), URL_LABEL (for output).
Fires N requests at once and reports per-request and aggregate timing.
With n_slots=1 they serialize; with n_slots>=N they batch.
"""
import json
import os
import threading
import time
import urllib.request

URL = "http://127.0.0.1:8080/v1/chat/completions"
N = int(os.environ.get("N", "3"))
PROMPT = "Explain what tensor parallelism does in one short paragraph."
MAXTOK = int(os.environ.get("MAXTOK", "48"))

results = []


def one(i):
    payload = {"messages": [{"role": "user", "content": f"{PROMPT} (request {i})"}],
               "max_tokens": MAXTOK, "temperature": 1.0, "top_p": 1.0,
               "chat_template_kwargs": {"reasoning_effort": "low"}}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=1200) as r:
            d = json.loads(r.read())
        t = d.get("timings", {}) or {}
        results.append({"i": i, "wall": time.time() - t0,
                        "prefill_tps": t.get("prompt_per_second", 0),
                        "decode_tps": t.get("predicted_per_second", 0),
                        "pred": t.get("predicted_n", 0)})
    except Exception as e:  # noqa: BLE001
        results.append({"i": i, "wall": time.time() - t0, "error": f"{type(e).__name__}: {e}"})


t_start = time.time()
threads = [threading.Thread(target=one, args=(i,)) for i in range(N)]
for th in threads:
    th.start()
for th in threads:
    th.join()
total = time.time() - t_start

print(f"=== {N} concurrent requests, server n_slots=1, max_tokens={MAXTOK} ===")
print(f"wall for all {N}: {total:.1f}s")
for r in sorted(results, key=lambda x: x["i"]):
    if "error" in r:
        print(f"  req{r['i']}: ERROR {r['error']}")
    else:
        print(f"  req{r['i']}: wall={r['wall']:.1f}s prefill={r['prefill_tps']:.1f} tok/s "
              f"decode={r['decode_tps']:.2f} tok/s ({r['pred']} tok)")
ok = [r for r in results if "error" not in r]
if ok:
    print(f"aggregate throughput: {sum(r['pred'] for r in ok)/total:.2f} tok/s across {N} requests")