#!/usr/bin/env python3
"""Compact probe: TTFT / prefill / decode at fixed depths + one tool call.

Usage: ms_probe.py [label]   (server must be on 127.0.0.1:8080)
"""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8080/v1/chat/completions"
label = sys.argv[1] if len(sys.argv) > 1 else "probe"
FILLER = ("The quick brown fox jumps over the lazy dog. " * 900)


def post(payload, timeout=900):
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()), time.time() - t0


# decode rate at three prompt depths (prefill reported too)
for depth, prompt in [("short ~30tok", "Explain what a MoE layer does in one sentence."),
                      ("mid ~450tok", FILLER[:1600] + "\nSummarise the above in one sentence."),
                      ("long ~9k tok", FILLER + "\nSummarise the above in one sentence.")]:
    d, w = post({"messages": [{"role": "user", "content": prompt}],
                 "max_tokens": 128, "temperature": 1.0, "top_p": 1.0,
                 "chat_template_kwargs": {"reasoning_effort": "low"}})
    t = d.get("timings", {})
    print(f"[{label}] {depth:14s} prompt={t.get('prompt_n')} tok  "
          f"prefill={t.get('prompt_per_second', 0):7.1f} tok/s  "
          f"TTFT={t.get('prompt_ms', 0)/1000:5.2f}s  "
          f"decode={t.get('predicted_per_second', 0):5.2f} tok/s "
          f"({t.get('predicted_n')} tok, {w:.1f}s wall)")

# tool call
tools = [{"type": "function", "function": {
    "name": "get_weather", "description": "Get current weather for a city",
    "parameters": {"type": "object", "properties": {
        "city": {"type": "string"}, "unit": {"type": "string", "enum": ["C", "F"]}},
        "required": ["city"]}}}]
d, w = post({"messages": [{"role": "user", "content": "What's the weather in Portland, Oregon in Celsius?"}],
             "tools": tools, "max_tokens": 256, "temperature": 1.0,
             "chat_template_kwargs": {"reasoning_effort": "low"}})
m = d["choices"][0]["message"]
print(f"[{label}] tool_call: {json.dumps(m.get('tool_calls'))[:200]}")
print(f"[{label}] content  : {(m.get('content') or '')[:120]!r}")