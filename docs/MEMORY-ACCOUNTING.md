# Where the 128 GB actually goes on DGX Spark (GB10)

Measured on 8 × Lenovo ThinkStation PGX (GB10), 2026-10-15. Every number here came off the
hardware; sources for the vendor-documented parts are listed at the bottom.

## The 30-second version

`128 GB` is decimal. Linux reports GiB. **128 GB = 119.2 GiB before anything else happens** —
that alone is 8.8 GiB of the apparent gap. The rest is a ~2 GiB firmware display reservation,
~4–5 GiB of kernel/driver/OS baseline, and page cache that is reclaimable but competes directly
with CUDA allocations on unified memory.

| Effect | Size | Real loss? |
|---|---|---|
| GB vs GiB conversion | 8.8 GiB | **no** — nothing is missing |
| Display/firmware scanout reserve | ~2 GiB (2,046 MiB documented) | yes, unless reclaimed |
| Kernel + driver + OS baseline | ~4–5 GiB | yes |
| Page cache (idle, on a node with no model) | ~8.7 GiB | no — reclaimable |
| 64 KiB-kernel UVM page tables | up to 3.25 GiB | **not applicable to us** — 4 KiB pages |

## Measured per-node memory

| Node | Hostname | BIOS | BIOS date | EC fw | MemTotal |
|---|---|---|---|---|---|
| x214 | thinkstationpgx-e7e9 | S0QKT0EA | 2026-07-13 | 2.78.24 | 124,546 MiB (121.63 GiB) |
| x215 | thinkstationpgx-e80f | S0QKT0EA | 2026-07-13 | — | 124,546 MiB |
| **x216** | **thinkstationpgx-3d30** | **S0QKT09A** | **2025-10-14** | **0.0.1** | **122,502 MiB (119.63 GiB)** |
| x217 | thinkstationpgx-2f5b | S0QKT0CA | 2026-03-13 | — | 124,546 MiB |
| x218 | thinkstationpgx-ff39 | S0QKT0EA | 2026-07-13 | — | 124,610 MiB |
| x219 | thinkstationpgx-f4bf | S0QKT0CA | 2026-03-13 | — | 124,610 MiB |
| x220 | thinkstationpgx-0212 | S0QKT0CA | 2026-03-13 | — | 124,610 MiB |
| x221 | thinkstationpgx-0368 | S0QKT0EA | 2026-07-13 | — | 124,610 MiB |

Driver is **identical everywhere** (580.173.02, open kernel module) and the kernel is identical
(6.17.0-1031-nvidia, `init_on_alloc=0 iommu.passthrough=0`). See "The x216 anomaly" below.

## Idle accounting, in full (x216, nothing loaded)

| Bucket | GiB | Notes |
|---|---|---|
| MemTotal | 119.63 | = 125.44 GB decimal; advertised 128 GB → **2.56 GB firmware carve-out** |
| MemAvailable | 107.25 | what a new allocation can actually get |
| Cached (page cache) | 8.71 | reclaimable in principle; kernel credits only ~1.4 GiB of it |
| Slab | 0.62 | 0.19 reclaimable, 0.43 unreclaimable |
| All userland anon RAM, 519 processes | 0.34 | the entire desktop + docker + cluster stack |
| Kernel stacks + page tables | 0.04 | |
| **Residual /proc/meminfo won't attribute** | **3.92** | kernel + NVIDIA driver reserve/pin |

The last row is honest-to-goodness unexplained *by the counters we can read*: `/proc/iomem` is
redacted, `debugfs` isn't mounted for a normal user, and there's no passwordless sudo on these
nodes, so the firmware reservation table can't be read directly.

## When serving, the model is invisible

This is the trap worth internalising. On x214 while holding the 816B model:

| Measure | Value |
|---|---|
| `free` reports used | **118.48 GiB** |
| MemAvailable | 10.09 GiB |
| Sum of ALL process RSS (528 procs) | **4.30 GiB** |
| llama-server's own VmRSS | **2.11 GiB** (RssAnon 1.10, RssFile 0.11, RssShmem 0.91) |
| In no /proc/meminfo bucket and no process | **101.43 GiB** |

Those 101 GiB are CUDA unified-memory device allocations — 97.3 GiB of weights (208.9 GB ÷ 2)
plus KV and compute buffers. On GB10 the weights are **not process memory**, so `top`, RSS and
`free`'s per-process column will never show you where the model went. GPU-visible numbers are
also unavailable: `nvidia-smi` is documented to print `Memory-Usage: Not Supported` on iGPUs
because there is no dedicated framebuffer, and our query returned `N/A` for FB memory.

NVIDIA's own guidance for UMA applications is to size against `/proc/meminfo`'s `MemAvailable`
+ `SwapFree` (accounting for hugetlbfs), because `cudaMemGetInfo` under-reports: it doesn't
count DRAM that the CPU could reclaim by swapping pages out.

## Page cache is a real competitor on UMA, not just cosmetic

On a unified-memory box there is one pool, so page cache competes *directly* with CUDA
allocations. NVIDIA's FAQ answer to "my application hits memory problems even though I'm within
capacity" is to check `buff/cache` in `free -h` and flush it:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

Community discussion adds `vm.vfs_cache_pressure=200` as a durable tuning so the kernel prefers
reclaiming page cache over anonymous memory. We have not tested either lever on this fleet
(no passwordless sudo), so treat them as documented-not-measured here.

## The x216 anomaly

Every other node in the fleet exposes ~2 GiB more RAM to Linux than x216, and the deficit
(**2,044 MiB**) matches the documented GB10 display-scanout reservation (**2,046 MiB**) almost
exactly.

What differs is firmware, not software: x216 is the only unit on BIOS **S0QKT09A (2025-10-14)**
while the rest run S0QKT0CA (2026-03-13) or S0QKT0EA (2026-07-13); its **Embedded Controller
reports 0.0.1** against 2.78.24 on a sibling, and its UEFI device firmware is 2.0.9 vs 2.0.14.
`fwupdmgr get-updates` on x216 lists pending EC (→3.5.8), TPM (→7.2.4.1) and UEFI device
firmware (→2.0.14). No fwupd "System Firmware" device is exposed on these Lenovo units, so the
BIOS itself may need a vendor update path.

**Leading explanation (correlation, well-supported, not proven):** the older firmware still
carves the ~2 GiB display reserve out of Linux's pool, while newer firmware exposes it. Action
for whoever owns the fleet: update x216's firmware. Until then x216 has ~2 GiB less headroom
than its siblings — it is the node that will OOM first in a near-ceiling configuration such as
two-node serving of a 194.6 GiB quant.

## What does *not* apply to us

- **The 64 KiB-kernel UVM page-table bloat (3.25 GiB/node).** `DGX Spark Memory Saver` patches
  UVM so page tables pack 16-per-page instead of one CPU page per 256-byte GPU leaf table,
  recovering 1.78–1.86 GiB/node *versus a stock 4 KiB system*. Our fleet runs 4 KiB pages
  (`getconf PAGESIZE` = 4096), so we already have that benefit and the patch is a no-op here.
  It becomes relevant only if we move to a `-64k` kernel (which some long-context recipes want).
- **Driver regression**: 590.48.01 fails to release UMA memory after a CUDA process exits;
  rollback to 580.x fixes it. We're on 580.173.02 — unaffected.
- **"Max allocatable GPU memory is 96 GB"** — a Reddit claim; NVIDIA's forum answer is
  "Not true, there's no such limit anywhere". Our 97.3 GiB/node weight allocation confirms it.

## Reclaiming the display reserve (documented, experimental)

`jontaylor/gb10-ram-reclaim` reclaims ~2,046 MiB/machine into ordinary Linux RAM using a
patched NVIDIA driver plus kernel helpers to block the display-allocation paths and release
the pages. Manually activated, nothing at boot, reboot restores stock, long-term stability
unproven, validated only on the exact firmware/kernel/driver combo documented there. Note from
the thread: the reclaimed region runs at **~70% the speed of the main pool**, so put cold
weights there (one user moved `lm_head`/`embed_tokens` into it; another doubled KV capacity
128k → 256k). We have not applied it.

## Practical checklist for this pair

1. Size against `MemAvailable`, never `cudaMemGetInfo` or `nvidia-smi`.
2. Budget ~116 GiB usable per node after the kernel/driver baseline; 97.3 GiB of that is
   weights for the IQ1_M quant.
3. If a load fails at the margin, flush page cache first, then reduce context — in that order.
4. Prefer the 7 nodes with the newer BIOS as head/peer for near-ceiling work; leave x216 for
   jobs with slack, until its firmware is updated.
5. Expect `top`/RSS to show nothing about where the model lives. Watch `free -m`, or the DGX
   Dashboard at `http://localhost:11000`.

## Sources

- NVIDIA, DGX Spark User Guide → Known Issues → *Guidance for reporting memory resources with
  unified memory architecture* — `cudaMemGetInfo` under-reports on UMA; use MemAvailable +
  SwapFree; `nvidia-smi` "Memory-Usage: Not Supported" is expected on iGPU.
- NVIDIA, DGX Spark GB10 FAQ (forum topic 347344) — the "20 GB doing nothing" case is cache;
  official fix is `drop_caches`.
- NVIDIA forum 384621, *Reclaim 2GiB of ram on headless sparks* — 2,046 MiB display reserve,
  patched-driver reclamation, ~70% speed of main pool.
- NVIDIA forum 384884, *Introducing DGX Spark Memory Saver* — 64 KiB UVM page tables 3.25 GiB →
  0.218 GiB; 1.78–1.86 GiB/node recovery vs stock 4 KiB.
- NVIDIA forum 350359, *The DGX system itself takes up 20GB memory?* — cache, plus the
  multiuser-mode suggestion to drop the GUI.
- NVIDIA forum 349545, *Maximum allocatable GPU memory on DGX Spark* — no 96 GB cap.
- NVIDIA forum 363178, *How to automatically free shared system memory* — page cache on UMA
  competes with CUDA; `vm.vfs_cache_pressure`; the 590.48.01 UMA-release regression.