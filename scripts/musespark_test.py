#!/usr/bin/env python3
"""Benchmark Muse Spark Open served by llama.cpp across 2 Sparks (RPC).
Tests: long-prompt prefill, tool calling, and a multi-turn reasoning pass.
Run on the head node (where llama-server listens on :8080).
"""
import json
import time
import urllib.request

URL = "http://127.0.0.1:8080/v1/chat/completions"


def call(payload, timeout=1200):
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d, time.time() - t0


def show(tag, d, wall):
    t = d.get("timings", {}) or {}
    ch = (d.get("choices") or [{}])[0]
    msg = ch.get("message", {}) or {}
    print(f"--- {tag} ---")
    print(f"  wall={wall:.1f}s  prefill={t.get('prompt_per_second', 0):.1f} tok/s "
          f"({t.get('prompt_n', 0)} tok in {t.get('prompt_ms', 0)/1000:.2f}s)  "
          f"decode={t.get('predicted_per_second', 0):.2f} tok/s ({t.get('predicted_n', 0)} tok)")
    print(f"  ttft={t.get('prompt_ms', 0):.0f}ms  total_tokens={d.get('usage', {}).get('total_tokens')}")
    txt = (msg.get("content") or "").replace("\n", " ")[:160]
    print(f"  content: {txt}")
    if msg.get("tool_calls"):
        print(f"  TOOL_CALLS: {json.dumps(msg['tool_calls'])[:300]}")
    return t


# --- Test 1: long-prompt prefill (~4k tokens) ---
filler = ("The DGX Spark is a GB10 Grace Blackwell system with 128 GB of unified LPDDR5x "
          "memory and a 200 GbE ConnectX-7 fabric port. ") * 260
long_prompt = ("Read the following reference text and then answer the question at the end.\n\n"
               + filler + "\n\nQUESTION: In one sentence, how much unified memory does the "
               "machine described above have, and what fabric does it use?")
print(f"long prompt chars={len(long_prompt)}")
d, w = call({"messages": [{"role": "user", "content": long_prompt}],
             "max_tokens": 64, "temperature": 1.0, "top_p": 1.0,
             "chat_template_kwargs": {"reasoning_effort": "low"}})
show("long-prompt prefill (~4k tok)", d, w)

# --- Test 2: tool calling ---
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["C", "F"]}},
            "required": ["city"],
        },
    },
}]
d, w = call({"messages": [{"role": "user", "content": "What's the weather in Portland, Oregon in Celsius?"}],
             "tools": tools, "max_tokens": 128, "temperature": 1.0, "top_p": 1.0,
             "chat_template_kwargs": {"reasoning_effort": "low"}})
show("tool calling", d, w)

# --- Test 3: multi-turn with reasoning preserved ---
msgs = [{"role": "user", "content": "Name the two nodes' roles in a pipeline parallel split."},
        {"role": "assistant", "content": "One node holds the earlier layers and the other holds the later layers."},
        {"role": "user", "content": "Which one produces the final logits?"}]
d, w = call({"messages": msgs, "max_tokens": 64, "temperature": 1.0, "top_p": 1.0,
             "chat_template_kwargs": {"reasoning_effort": "low"}})
show("multi-turn", d, w)