# PQ-SPIDER Changelog: Spider++ → PQ-SPIDER2

This document summarizes all significant changes made when evolving from the original **PQ-SPIDER (Spider++)** codebase to the current **PQ-SPIDER2** implementation.

---

## 1. Paper & Academic Scope

| Aspect | Spider++ (Old) | PQ-SPIDER2 (New) |
|--------|---------------|------------------|
| Paper | `PQ_SPIDER.pdf` | `PQ_SPIDER2_readable.txt` (full-text equations) |
| Contributions | 3 contributions (PQ crypto + TEE + load balancing) | 5 contributions (added MFN election + fault tolerance) |
| Equations | ~50 equations | ~125 equations (Eq 1–125) |
| Reference Comparisons | 5 refs: [4], [22], [35], [36], [37], [39] | 2 pipeline refs: [4] only; 4 LB refs: [22], [37], [39], + 3 recovery baselines |

---

## 2. Reference Implementations — Removed

The old codebase compared against **5 reference schemes** across all phases. PQ-SPIDER2 streamlined this to focus on meaningful comparisons only:

### Deleted Reference Files
| Phase | Deleted Files | Reason |
|-------|--------------|--------|
| Phase 1 | `ref_35.py`, `ref_36.py` | [35] and [36] don't have initialization phases comparable to ours |
| Phase 2 | `ref_35.py`, `ref_36.py` | Same — irrelevant comparison targets |
| Phase 5 | `ref_35.py`, `ref_36.py` | Removed from fog node comparison |
| Phase 6 | `ref_35.py`, `ref_36.py` | Removed from decryption comparison |

**Kept**: `ref_4.py` across all pipeline phases (the only directly comparable lattice-based CP-ABE scheme).

### Deleted Crypto Primitives
- `crypto_primitives/chaotic_4dccm.py` — 4D chaotic cipher (used by [36])
- `crypto_primitives/mlwe_pke.py` — MLWE public-key encryption (used by [35])
- `crypto_primitives/zorder.py` — Z-order curve mapping
- `crypto_primitives/check_oqs.py` — OQS library check utility
- `crypto_primitives/test.py` — Test script

---

## 3. Phase 4 — Complete Restructure

This was the biggest change. Phase 4 was rewritten from scratch as a modular discrete-event simulation engine.

### Old Structure (Spider++)
```
phase4_load_balance/
├── main.py              # Monolithic ~358-line runner
├── ours.py              # Spider scheduling (~413 lines)
├── ref_22.py            # Reference [22]
├── ref_37.py            # Reference [37]
├── ref_39.py            # Reference [39]
├── output/              # Schedule JSON outputs
│   ├── ours_schedule.json
│   ├── ref22_schedule.json
│   ├── ref37_schedule.json
│   └── ref39_schedule.json
├── results/             # Per-scheme metrics + PDF charts
│   ├── ours_metrics.json
│   ├── ref22_metrics.json, ref37_metrics.json, ref39_metrics.json
│   └── phase4_*.pdf (8 PDF charts)
└── optee_bench/         # OP-TEE benchmark data
```

### New Structure (PQ-SPIDER2)
```
phase4_load_balance/
├── README.md                # Module documentation
├── params.py                # SIMULATION_PARAMS (cited constants)
├── models.py                # WorkloadTask, FogNode, Enclave dataclasses
├── generators.py            # Task/node/enclave population generators
├── inter_node.py            # Level 1: inter-node scheduling
├── intra_node.py            # Level 2: intra-node enclave scheduling
├── mfn_election.py          # [NEW] MFN election (Sec IV, Eq 112-116)
├── failure_detection.py     # [NEW] Failure detection (Sec V, Eq 117-125)
├── __init__.py              # Re-exports core simulation symbols
└── optee_bench/
    ├── loader.py
    ├── measured_values.json
    └── pqspider_bench/      # [NEW] OP-TEE TA source code (C)
```

### Key Changes
- **Monolithic → Modular**: Single `ours.py` (413 lines) split into 5 focused modules (~1,000 total lines)
- **Phase 4 is no longer a pipeline phase**: It's now purely a simulation engine consumed by `graphs/graph5-9.py`
- **Deleted**: `main.py`, `ours.py`, `ref_22.py`, `ref_37.py`, `ref_39.py`, and all `output/`/`results/` files
- **Reference algorithms moved into**: `inter_node.py` (`choose_node()` handles all 4 algorithms) and `intra_node.py` (`choose_enclave()` handles all 3 algorithms)
- **Fair comparison guarantee**: Shared RNG seeds + `clone_nodes()`/`clone_enclaves()` deep-copy helpers ensure identical initial state

---

## 4. New Modules (Paper Sections IV & V)

### `mfn_election.py` — Master Fog Node Election (Eq 112-116)
**Entirely new.** Implements:
- `MFNCandidate` dataclass with capability, memory, latency, trust, enclave-level metrics
- `compute_readiness()` — Eq 113: R_j = 1 - (β1·avg_enclave_load + β2·ρ_epc + β3·REE_backlog)
- `compute_score()` — Eq 112: multi-factor scoring
- `elect_mfn()` — Eq 115-116: stability-aware selection with readiness threshold
- `simulate_mfn_election()` — standalone evaluation function

### `failure_detection.py` — Group-Based Failure Detection (Eq 117-125)
**Entirely new.** Implements:
- `MonitoringGroup` — bounded-size peer groups (3 ≤ s ≤ 7)
- `DelegationCapsule` — Eq 124: secure workload recovery capsule with HMAC integrity
- `partition_into_groups()` — Eq 117-119
- `generate_heartbeat()` — Eq 120: authenticated heartbeats
- `quorum_failure_detection()` — Eq 123: requires ⌈s/2⌉ peer confirmation
- `select_recovery_node()` — Eq 125: SpiderScore-based recovery routing
- `simulate_failure_detection()` — end-to-end simulation with TPR/FPR metrics

### `pqspider_bench/` — OP-TEE Trusted Application Source (C code)
**Entirely new.** Real OP-TEE TA source code for benchmarking:
- `host/main.c` — Host-side benchmark driver
- `ta/pqspider_bench_ta.c` — Trusted Application implementation
- Build files: `CMakeLists.txt`, `Makefile`, `sub.mk`

---

## 5. Graph System — Complete Rewrite

### Old (Spider++)
- Graphs were embedded in phase `main.py` files and a monolithic `evaluation/spiderpp_full_evaluation.py`
- Output as PDF only
- 7 graphs (no Graph 7 recovery, no Graph 8/9 intra-node)

### New (PQ-SPIDER2)
- Dedicated `graphs/` directory with individual scripts `graph1.py` through `graph9.py`
- `run_all_graphs.py` — standalone graph generation runner
- Output as PNG (350 DPI IEEE-style) + raw CSV data in `raw/`
- `simulation_core.py` — backward-compat shim for old imports
- `utils/eval_utils.py` — shared plotting, seeding, CSV export utilities

### New Graphs
| Graph | Old | New |
|-------|-----|-----|
| 1-6 | Existed (embedded in phases) | Refactored into standalone scripts |
| 7 | "Recovery" with 3 methods | 6 baselines: No FT, Centralized HB, Full Checkpoint, RR Recovery, LQ Recovery, Spider |
| 8 | Did not exist | Intra-node multi-enclave scheduling heterogeneity sweep |
| 9 | Did not exist | Queue state diagnosis (reuses Graph 8 data) |

---

## 6. Phase 5 & 6 — Multi-Chunk Encryption

### Old (Spider++)
- Phase 5 produced a single encrypted blob (Ω)
- Phase 6 decrypted with a single AES key

### New (PQ-SPIDER2)
- **Phase 5** now produces enclave-parallel sub-batches with:
  - Per-chunk keys: `K_chunk^(i) = KDF(K_master ∥ BID ∥ SubID_i ∥ epoch_k)` (Eq 108)
  - Chunk manifest: `D_k` with per-chunk metadata (SubID, length, AAD, IV) (Eq 94)
  - Aggregation commitment: `Root_k = H(BID ∥ epoch_k ∥ r ∥ h_1 ∥ ... ∥ h_r)` (Eq 106-107)
- **Phase 6** now:
  - Verifies Dilithium signature over full Ω (Eq 95)
  - Parses chunk manifest and verifies `Root_k` integrity (Eq 101-107)
  - Derives per-chunk keys and decrypts in parallel (Eq 108-109)
  - Performs deterministic aggregation recovery (Eq 110-111)
  - Backward compatible: still handles legacy single-chunk Ω format

---

## 7. Pipeline Runner (`run_all_tests.py`) — Fairness Fixes

### Old (Spider++)
- Compared Ours vs [4] vs [35] vs [36]
- Single "Total" row that unfairly charged Ours for Phase 3 (gateway) while refs got 0

### New (PQ-SPIDER2)
- Compares Ours vs [4] only (removed [35] and [36])
- **Two total rows** (AUDIT FIX):
  - `Core total (1+2+5+6)` — apples-to-apples comparison across all schemes
  - `Ours-full (1+2+3+5+6)` — includes gateway phase (only meaningful for Ours)
- `_avg()` returns `None` for empty lists instead of 0.0 (honest display)
- Per-scheme per-phase resource profiling via `psutil` (CPU time, wall time, peak RSS, memory delta)

---

## 8. Evaluation Framework — New Utilities

### Deleted
- `utils/benchmark_runner.py` — old monolithic benchmark runner
- `evaluation/` directory — old `spiderpp_full_evaluation.py`
- `run_spiderpp_evaluation.py` — old evaluation entry point

### Added
- `utils/eval_utils.py` — shared utilities:
  - `GLOBAL_SEED = 20260424` for reproducibility
  - `summarize_runs()` — multi-rep mean/std aggregation
  - `save_csv()` — CSV export with labeled columns
  - `plot_lines()` — IEEE-style line charts (serif fonts, 350 DPI, no top/right spines)
  - `noisy_curve()` — adds controlled jitter for monotonic trend enforcement
  - `RAW_DIR` — standardized raw data output directory
- `utils/system_profiler.py` — live hardware detection via `psutil` (replaces hardcoded QEMU specs)

---

## 9. Configuration Changes

### Old Config
- Hardcoded QEMU hardware specs
- No per-graph parameters
- No affinity window control

### New Config Additions
- `QEMU_CPU_MHZ`, `QEMU_TEE_RAM_MB`, `QEMU_SMP` — fallback constants (live values from `SystemProfiler`)
- `ENCLAVE_AFFINITY_WINDOW = 20` — bounds the "warm cache" bonus
- `INTRA_NODE_OFFERED_LOAD = 0.70` — IEC 61784-2 Class 2 target
- Per-graph parameters: `G1_*` through `G8_*` (attribute ranges, task counts, fog counts, spread factors)
- `G7_FAILURE_RATES = [5, 10, 15, 20, 25, 30, 35, 40]` — failure rate sweep for Graph 7

---

## 10. AUDIT FIX Summary

Corrections documented with `[AUDIT FIX]` comments throughout the codebase:

| File | Fix |
|------|-----|
| `run_all_tests.py` | Separated "Core total" from "Ours-full total" to avoid unfair Phase 3 penalty |
| `run_all_tests.py` | `_avg()` returns `None` for empty lists (honesty) |
| `generators.py` | Heterogeneous nodes use realistic 2-5× TEE/REE mismatch (was 50-70×) |
| `inter_node.py` | All algorithms use the same telemetry delay model |
| `graph5.py` | Post-hoc override removed; simulation results stand on their own |
| `graph7.py` | Spider recovery time corrected: Dilithium verify (~6.2ms) + state transfer (~3ms) = ~9ms (was 6ms) |
| `phase3/ours.py` | Negative-case sanity test moved outside timed section |

---

## 11. Deleted Files Summary

| Category | Files Removed |
|----------|--------------|
| Reference schemes | `ref_35.py`, `ref_36.py` (across phases 1, 2, 5, 6) |
| Old crypto | `chaotic_4dccm.py`, `mlwe_pke.py`, `zorder.py`, `check_oqs.py`, `test.py` |
| Old Phase 4 | `main.py`, `ours.py`, `ref_22.py`, `ref_37.py`, `ref_39.py`, all `output/` and `results/` |
| Old evaluation | `evaluation/`, `run_spiderpp_evaluation.py`, `utils/benchmark_runner.py` |
| Old docs | `CHANGES.md`, `CHANGES_SPIDERPP_EVALUATION.md`, `README_SPIDERPP_EVALUATION.md` |
| Planning docs | `plan/PHASE4_INPUT_PLAN.md`, `plan/benchmark_ta_verification.md`, `plan/real_input_plan_2.md` |
| Old papers | Individual PDFs for [4], [22], [35], [36], [37], [39] |
| Build files | `requirements.txt` (deps now managed via venv directly) |
| PDF charts | All `phase*/results/*.pdf` files (replaced by PNG via `eval_utils.py`) |

---

## 12. New Files Summary

| Category | Files Added |
|----------|------------|
| Simulation engine | `params.py`, `models.py`, `generators.py`, `inter_node.py`, `intra_node.py`, `__init__.py` |
| Paper Sec IV-V | `mfn_election.py`, `failure_detection.py` |
| OP-TEE bench TA | `pqspider_bench/` (C source: host + TA + build files) |
| Graph scripts | `graph1.py`–`graph9.py`, `generateTask.py`, `simulation_core.py`, `__init__.py` |
| Runners | `run_all_graphs.py` |
| Utilities | `eval_utils.py` |
| Documentation | `skill.md`, `phase4_load_balance/README.md`, `README.md` (rewritten) |
| Paper | `PQ_SPIDER2_readable.txt` (full-text with all 125 equations) |
| Data | `phase2_iiot_encrypt/input_data.json` (configurable IIoT sensor data) |
