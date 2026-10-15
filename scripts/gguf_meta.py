#!/usr/bin/env python3
"""Print notable GGUF metadata (metadata-only read; loads no tensors)."""
import struct
import sys

path = sys.argv[1]
f = open(path, "rb")
assert f.read(4) == b"GGUF", "not a gguf"
ver = struct.unpack("<I", f.read(4))[0]
ntensors = struct.unpack("<Q", f.read(8))[0]
nkv = struct.unpack("<Q", f.read(8))[0]


def rs():
    n = struct.unpack("<Q", f.read(8))[0]
    return f.read(n).decode("utf-8", "replace")


def rv(t):
    fmt = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f",
           7: "<B", 10: "<Q", 11: "<q", 12: "<d"}
    if t == 8:
        return rs()
    if t == 9:
        et = struct.unpack("<I", f.read(4))[0]
        n = struct.unpack("<Q", f.read(8))[0]
        if et == 8:
            return [rs() for _ in range(n)]
        sz = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 10: 8, 11: 8, 12: 8}[et]
        f.read(sz * n)
        return f"<array len={n}>"
    return struct.unpack(fmt[t], f.read(struct.calcsize(fmt[t])))[0]


want = ("architecture", "block_count", "head_count", "key_length", "value_length",
        "embedding_length", "context_length", "expert_count", "expert_used_count",
        "feed_forward_length", "vocab_size", "file_type", "name")

print(f"version={ver} tensors_in_this_shard={ntensors} kv_pairs={nkv}")
for _ in range(nkv):
    k = rs()
    t = struct.unpack("<I", f.read(4))[0]
    v = rv(t)
    if any(w in k for w in want):
        print(f"{k} = {v}")