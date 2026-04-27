# OP-TEE Benchmark — Measured Values

This folder connects the **OP-TEE QEMU benchmark TA** to the **Spider scheduler**.

## File Layout

```
optee_bench/
├── measured_values.json   ← TA writes here via VirtFS; Python reads from here
├── loader.py              ← load_measurements() patches config.py at runtime
└── README.md              ← this file
```

## How It Works

1. **Build & run** the benchmark TA on QEMU:
   ```bash
   cd ~/optee-qemu/build
   make -j$(nproc) QEMU_VIRTFS_AUTOMOUNT=y
   make QEMU_VIRTFS_AUTOMOUNT=y run
   # Inside QEMU Normal World shell:
   pqspider_bench
   ```

2. The TA automatically writes `measured_values.json` to this folder via VirtFS
   (QEMU mounts `~/optee-qemu/` at `/mnt/host/` → writes to
   `/mnt/host/pq_spider_migga/phase4_load_balance/optee_bench/measured_values.json`)

3. Phase 4 calls `load_measurements()` at startup, which patches `config.py` with
   the real values before scheduling begins.

## Values Measured

| Key | What | Used By |
|-----|------|---------|
| `service_rate` | AES-256-GCM ops/sec inside TEE | Eq 32, 42 (μ_{j,k}) |
| `world_switch_ms` | NW→SW context switch latency | Eq 36 (L_j) |
| `trust_score` | TA session open success rate | Eq 35 (U_j) |

## TA Source Location

```
~/optee-qemu/optee_examples/pqspider_bench/
├── host/main.c                      ← measures all 3 values
├── ta/pqspider_bench_ta.c           ← secure-world AES-GCM benchmark
├── ta/include/pqspider_bench_ta.h   ← UUID + command IDs
└── ta/user_ta_header_defines.h      ← 8KB stack, 64KB heap
```
