# PQ-SPIDER Project Skill File

## Project Overview

**PQ-SPIDER** (Post-Quantum Secure and Dynamic Load-Balanced Encryption for IIoT Data in Fog Computing) is a simulation and evaluation framework for a post-quantum fog-assisted security architecture targeting Industrial IoT (IIoT) environments. It models an end-to-end IIoT data pipeline and benchmarks the proposed "Spider" approach against state-of-the-art reference implementations (Ref [4], Ref [22], Ref [37], Ref [39]).

The framework accompanies an academic paper authored at Sirindhorn International Institute of Technology, Thammasat University.

---

## Tech Stack
- **Component**: linux(mainly on oracle virtualbox) it is the main os that run the program,optee(qemu v8 (ARM Cortex-A72 emulation)), window
- **Language**: Python 3 (no framework — pure scripts)
- **Key Libraries**: `numpy`, `matplotlib`, `psutil`, `hashlib`, `json`, `csv`
- **Plotting**: IEEE-style plots via `matplotlib` (serif fonts, 350 DPI, no top/right spines)
- **Randomness**: All simulations seeded via `numpy.random.Generator` with `GLOBAL_SEED = 20260424` for reproducibility
- **TEE Platform**: OP-TEE on QEMU v8 (ARM Cortex-A72 emulation), NOT Intel SGX
- **Cryptographic Primitives**: Custom Python implementations (NOT production crypto)
  - `crypto_primitives/kyber.py` — CRYSTALS-Kyber (post-quantum KEM)
  - `crypto_primitives/dilithium.py` — CRYSTALS-Dilithium (post-quantum signatures)
  - `crypto_primitives/cp_abe.py` — Lattice-based Ciphertext-Policy ABE
  - `crypto_primitives/aes_gcm.py` — AES-256-GCM
  - `crypto_primitives/chacha20.py` — ChaCha20-Poly1305
  - `crypto_primitives/puf.py` — Physical Unclonable Function simulation
---

## Directory Structure

```
Pq_spider_new/
├── config.py                    # All simulation parameters (topology, weights, graph params)
├── run_all_tests.py             # Full 6-phase pipeline runner + resource profiling
├── run_all_graphs.py            # Generates all 9 evaluation graphs
├── citation_defense.md          # Reviewer Q&A: citations for every numeric parameter
├── README.md                    # User-facing usage guide
│
├── crypto_primitives/           # Post-quantum crypto implementations
│   ├── kyber.py                 # CRYSTALS-Kyber KEM
│   ├── dilithium.py             # CRYSTALS-Dilithium signatures
│   ├── cp_abe.py                # Lattice-based CP-ABE (largest, ~25KB)
│   ├── aes_gcm.py               # AES-256-GCM wrapper
│   ├── chacha20.py              # ChaCha20-Poly1305 wrapper
│   └── puf.py                   # PUF simulation with fuzzy extractor
│
├── phase1_initialization/       # Phase 1: System init (key gen, fog nodes, device registry)
│   ├── main.py                  # Standalone phase runner
│   ├── ours.py                  # PQ-SPIDER implementation
│   └── ref_4.py                 # Reference [4] (Poomekum) implementation
│
├── phase2_iiot_encrypt/         # Phase 2: IIoT device encryption
│   ├── main.py
│   ├── ours.py
│   ├── ref_4.py
│   └── input_data.json          # Configurable IIoT sensor data input
│
├── phase3_edge_gateway/         # Phase 3: Edge gateway validation & micro-batch formation
│   ├── main.py
│   └── ours.py                  # Only "Ours" has a gateway phase (refs skip it)
│
├── phase4_load_balance/         # Phase 4: Load balancing simulation engine
│   ├── params.py                # SIMULATION_PARAMS — cited constants with derivations
│   ├── models.py                # WorkloadTask, FogNode, Enclave dataclasses
│   ├── generators.py            # Task/node/enclave population generators
│   ├── inter_node.py            # Level 1: inter-node scheduling (Spider, Ref[22/37/39])
│   ├── intra_node.py            # Level 2: intra-node enclave scheduling (Spider, RR, LQ)
│   ├── __init__.py              # Re-exports all public symbols
│   └── optee_bench/             # OP-TEE QEMU measurement data
│       └── loader.py            # Loads measured_values.json
│
├── phase5_fog_node/             # Phase 5: Fog node CP-ABE processing
│   ├── main.py
│   ├── ours.py
│   └── ref_4.py
│
├── phase6_user_decrypt/         # Phase 6: Authorized user decryption
│   ├── main.py
│   ├── ours.py
│   └── ref_4.py
│
├── graphs/                      # Graph plotting scripts (Graphs 1–9)
│   ├── simulation_core.py       # Backward-compat shim (re-exports from phase4_load_balance)
│   ├── graph1.py – graph9.py    # Individual graph generators
│   ├── generateTask.py          # Task generation utility
│   └── spider_full_evaluation/  # Output: .png graphs + raw/ CSV data
│
├── utils/
│   ├── eval_utils.py            # Shared: seeding, plotting, CSV export, IEEE plot helpers
│   ├── dataset_loader.py        # JSON metrics file loader
│   ├── resource_profiler.py     # CPU/memory profiling via psutil
│   └── system_profiler.py       # System hardware detection
│
└── papers/
    └── PQ_SPIDER2_readable.txt  # Full paper text (equations, algorithms, threat model)
```

---

## Architecture & Data Flow

### Pipeline Phases (Sequential)

```
Phase 1 (Init) → Phase 2 (Device Encrypt) → Phase 3 (Gateway) → Phase 5 (Fog) → Phase 6 (User Decrypt)
```

- **Phase 4** is NOT a pipeline phase — it's a discrete-event simulation in `phase4_load_balance/` for load-balancing evaluation (Graphs 5–9).
- Each phase writes intermediate data to `{phase}/output/` and latency metrics to `{phase}/results/`.
- Metrics files: `ours_metrics.json` and `ref4_metrics.json`.

### Comparison Schemes

| Scheme Label        | Scope                              |
|---------------------|------------------------------------|
| `Ours` (PQ-SPIDER)  | Full pipeline: Phases 1→2→3→5→6    |
| `Ref[4] Poomekum`   | Core pipeline: Phases 1→2→5→6      |
| `Ref[22]`           | Load balancing only (Graphs 5–7)   |
| `Ref[37]`           | Load balancing only (Graphs 5–7)   |
| `Ref[39]`           | Load balancing only (Graphs 5–7)   |
| `Round-Robin`       | Intra-node scheduling (Graphs 8–9) |
| `Least-Queue`       | Intra-node scheduling (Graphs 8–9) |

### Key Fairness Principle

> All algorithms in a comparison receive the **same task stream** and **same initial node/enclave state** via shared RNG seeds. Algorithm-specific RNG offsets prevent cross-contamination of scheduling noise.

---

## Configuration System (`config.py`)

All simulation parameters are centralized in `config.py`. Sections:

1. **Global Topology**: `NUM_GLOBAL_NODES`, `NUM_DEVICES`
2. **Hardware Constraints**: `EPC_BUDGET_BYTES` (29.5 MB OP-TEE TZDRAM), `ENC_PER_NODE`, `PACKET_EPC_BYTES`
3. **OP-TEE Measured Values**: `MEASURED_SERVICE_RATE`, `MEASURED_WORLD_SWITCH_MS`, `MEASURED_BASE_TRUST`
4. **Spider Load Balancer Weights**: `W1`–`W8` (inter-node), `Z1`–`Z4` (intra-node), `THETA1`/`THETA2` (reuse), `BETA1`–`BETA3` (batch profiling)
5. **Cryptography**: `PAYLOAD_SIZE_BYTES`, `CP_ABE_UNIVERSE`, `USER_ATTRIBUTES`
6. **Graph Control**: `GENERATE_GRAPHS`, `INTRA_NODE_OFFERED_LOAD` (0.70), `ENCLAVE_AFFINITY_WINDOW`
7. **Per-Graph Parameters**: `G1_*` through `G8_*`

---

## Simulation Engine (`phase4_load_balance/`)

The discrete-event simulator is split across 5 focused modules:

### `params.py` — Simulation Parameters
- `SIMULATION_PARAMS` dict with all cited constants (EPC swap cost, contention penalty, rate heterogeneity, startup overheads)

### `models.py` — Data Classes
- `WorkloadTask` — synthetic IIoT security micro-batch (arrival time, records, attrs, policy depth, TEE/REE work split, EPC requirement, deadline)
- `FogNode` — fog node with TEE/REE queues, rates, EPC, trust, energy factor
- `Enclave` — single TEE enclave within a fog node (queue, service rate, EPC state, affinity counter, explicit finish-time tracking)
- `clone_nodes()`, `clone_enclaves()` — deep-copy helpers for fair algorithm comparison

### `generators.py` — Population Generators
- `generate_tasks()` — creates synthetic IIoT workload streams
- `generate_nodes()` — creates homogeneous or heterogeneous fog node populations
- `generate_enclaves()` — creates heterogeneous enclave pools from OP-TEE measurements
- `_load_phase5_service_ms()` — loads measured service time from Phase 5 results

### `inter_node.py` — Level 1: Inter-Node Scheduling
- `choose_node()` implements 4 algorithms: `Ref[22]`, `Ref[37]`, `Ref[39]`, `Spider (Ours)`
- Spider models the exact TEE→REE critical path with EPC pressure, capability, and trust penalties
- `execute_task()` — inter-node task execution with TEE→REE sequential pipeline
- `simulate_load_balancing()` — runs one complete inter-node experiment

### `intra_node.py` — Level 2: Intra-Node Scheduling
- `choose_enclave()` implements 3 algorithms: `Round-Robin`, `Least-Queue`, `Spider (Ours)`
- Spider uses `_enclave_score_eq46()` (Eq 46 from the paper) with queue wait, EPC pressure, contention penalty, and affinity bonus
- `execute_on_enclave()` — intra-node execution with stochastic variance (lognormal service time, EPC swap, contention, OS jitter)
- `_drain_queues()` — reclaims EPC memory from completed tasks using explicit finish-time tracking
- `simulate_intra_node()` — runs one complete intra-node experiment

### Important Design: Scheduler–Execution Decoupling
The scheduler uses **deterministic estimates** while execution adds **stochastic factors** (±30% contention variance, ±20% EPC swap variance, exponential OS jitter). This ensures Spider makes good but imperfect predictions, like a real scheduler operating on stale telemetry.

### Backward Compatibility
`graphs/simulation_core.py` remains as a thin shim that re-exports all symbols from `phase4_load_balance.*`. Existing imports from `graphs.simulation_core` continue to work.

---

## Graph Outputs (9 Graphs)

| Graph | Title                          | X-axis              | Evaluates        |
|-------|-------------------------------|----------------------|------------------|
| 1     | CP-ABE Setup Latency          | Number of attributes | Phase 1          |
| 2     | Cache Reuse at Edge Gateway   | Number of tasks      | Phase 3          |
| 3     | CP-ABE Encryption at Fog      | Number of attributes | Phase 5          |
| 4     | User Decryption Latency       | Number of attributes | Phase 6          |
| 5     | Load Balancing (Homogeneous)  | Number of fog nodes  | Phase 4 (sim)    |
| 6     | Load Balancing (Heterogeneous)| Number of fog nodes  | Phase 4 (sim)    |
| 7     | Recovery Latency              | Failure rate (%)     | Phase 5 (recovery)|
| 8     | Intra-Node Enclave Scheduling | Spread factor        | Phase 4 (sim)    |
| 9     | Queue State Diagnosis         | Task distribution    | Phase 4 (sim)    |

Output location: `graphs/spider_full_evaluation/*.png` with raw CSV data in `raw/`.

---

## Coding Conventions

### File Organization Per Phase
Each phase directory follows the same pattern:
```
phaseN_xxx/
├── main.py          # Standalone runner (compares ours vs ref and prints table)
├── ours.py          # PQ-SPIDER implementation (run_phaseN_simulation())
├── ref_4.py         # Reference [4] implementation (run_phaseN_ref4())
├── output/          # Intermediate data files (keys, ciphertexts, etc.)
└── results/         # Latency metrics JSON (ours_metrics.json, ref4_metrics.json)
```

### Metric Files Format
JSON files in `results/` with keys like:
- `total_init`, `total_device_latency`, `total_gateway_latency`, `total_fog_latency`, `total_user_latency`
- May contain lists (per-task latencies) or scalar values

### Naming Conventions
- Functions: `run_phaseN_simulation()`, `run_phaseN_ref4()`
- Graph functions: `graph1_setup_phase(rng)`, `graph2_cache_reuse(rng)`, etc.
- Config params: `UPPER_SNAKE_CASE`
- Equations referenced as comments: `# Eq 46`, `# Eq 33`, etc. (refer to paper)

### AUDIT FIX Pattern
Several files contain `[AUDIT FIX]` comments documenting corrections to the original implementation. These cover:
- Fairness fixes (e.g., separating "core total" from "ours-full total")
- Parameter calibration (e.g., realistic heterogeneity ranges)
- Bug fixes (e.g., queue drain logic)

---

## Running the Project

```bash
# Full pipeline + graphs
python run_all_tests.py          # Set GENERATE_GRAPHS = True in config.py

# Tests only (faster)
python run_all_tests.py          # Set GENERATE_GRAPHS = False in config.py

# Graphs only
python run_all_graphs.py

# Single phase
python phase1_initialization/main.py
python phase2_iiot_encrypt/main.py
# ... etc (phases are sequential — run in order)
```

### Dependencies
- `numpy`, `matplotlib`, `psutil` (for resource profiling)
- Virtual environment in `venv/`
- No external crypto libraries required (all primitives are custom implementations)

---

## Evaluation Methodology (IEEE Journal Quality)

The evaluation framework follows a two-tiered, hybrid approach designed to meet the rigorous reproducibility and validation standards of IEEE journals.

### 1. Hybrid Simulation Architecture (Real vs. Simulated)
- **Real (Empirically Grounded):** Base performance constants (e.g., TEE world switch latency `MEASURED_WORLD_SWITCH_MS`, service rates) are derived from real benchmark executions of OP-TEE on QEMU v8 (see `optee_bench/`). Resource profiling (`psutil`) captures live CPU/RAM metrics from the host machine during execution.
- **Simulated:** Cryptographic primitives (`crypto_primitives/`) and network traversal are simulated in Python. The Spider load-balancing math is executed natively in a discrete-event simulator without requiring a physical deployment of dozens of TrustZone-enabled edge servers, which is the industry standard for large-scale distributed systems research.

### 2. Dual Evaluation Layers (Phases vs. Graphs)
- **Pipeline Phases (`phaseN_/`):** Validates end-to-end system integration. These scripts run a single, fully-configured scenario (e.g., 10 nodes, 10 devices) to generate holistic total-latency summary tables.
- **Microbenchmark Graphs (`graphs/`):** Isolates specific operations (e.g., *only* CP-ABE setup) to evaluate scaling behavior (e.g., latency vs. number of attributes). This ensures plot trend lines are precise and free from systemic noise.

---

## Key Domain Concepts

- **TEE (Trusted Execution Environment)**: Hardware-isolated secure enclave (OP-TEE/ARM TrustZone in this project, NOT Intel SGX)
- **REE (Rich Execution Environment)**: Normal-world Linux execution outside the TEE
- **EPC (Enclave Page Cache)**: Limited secure memory within TEE; exceeding it triggers expensive page swapping (~12ms per swap)
- **CP-ABE**: Ciphertext-Policy Attribute-Based Encryption — enables fine-grained access control where decryption requires attributes satisfying a policy
- **Spider**: The proposed hierarchical scheduler with two levels:
  - **Level 1 (Inter-Node)**: Routes tasks across fog nodes using SpiderScore (Eq 40) with urgency, deadline, and reuse bonuses
  - **Level 2 (Intra-Node)**: Routes tasks across enclaves within a node using EnclaveScore (Eq 46) with EPC admission control (Eq 49)
- **PUF**: Physical Unclonable Function — hardware-based device identity
- **Kyber/Dilithium**: NIST-standardized post-quantum key encapsulation and digital signature algorithms
- **MFN (Master Fog Node)**: Coordinator elected via `mfn_election.py` (Eq 112-116)
- **Root_k**: Aggregation commitment hash binding all enclave-parallel chunk outputs (Eq 81)
- **D_k (Chunk Manifest)**: Per-chunk metadata (SubID, length, AAD, IV) enabling deterministic decryption (Eq 94)
- **Offered Load**: Ratio of incoming traffic rate to system capacity (0.70 = 70% utilization, the "balanced" operating point)

---

## Common Pitfalls & Important Notes

1. **Phase 4 is NOT a pipeline phase** — Load balancing is evaluated purely through discrete-event simulation in `phase4_load_balance/` (split across `inter_node.py` and `intra_node.py`). The `phase4_load_balance/optee_bench/` subdirectory contains OP-TEE benchmark data. New modules `mfn_election.py` and `failure_detection.py` implement Section IV and V of the paper.

2. **Phase 3 (Gateway) is asymmetric** — Only "Ours" has a gateway phase. Reference schemes skip it. The `run_all_tests.py` grand summary correctly separates "Core total (1+2+5+6)" from "Ours-full (1+2+3+5+6)" to avoid unfair comparisons.

3. **All crypto is simulated** — The primitives in `crypto_primitives/` are Python implementations for latency measurement, NOT production-grade crypto. Do not use for real security.

4. **Reproducibility** — All simulations use `GLOBAL_SEED = 20260424`. Changing the seed will produce different graphs. Algorithm-specific RNG offsets ensure fairness.

5. **Citation defense** — `citation_defense.md` contains peer-reviewed justifications for every simulation parameter. Consult it before changing any numeric constants in `phase4_load_balance/params.py`.

6. **Graph 9 reuses Graph 8 data** — There is intentionally no `raw/graph9` directory because Graph 9 is generated from Graph 8's experiment results.

7. **OP-TEE, not SGX** — Despite some SGX terminology in citations (EPC, enclave), this project targets OP-TEE on ARM. The `EPC_BUDGET_BYTES` is 29.5 MB (TZDRAM), not SGX's 93 MB.

8. **Resource profiling** — `utils/resource_profiler.py` wraps `psutil` to measure CPU time, wall time, peak RSS, and memory delta per phase.

9. **Phase V outputs multi-chunk Ω** — Phase V now produces enclave-parallel sub-batches with per-chunk keys (`K_chunk`), a chunk manifest (`D_k`), and an aggregation commitment (`Root_k`). Phase VI must parse the manifest and verify `Root_k` before decrypting. Legacy single-chunk Ω is supported for backward compatibility.

10. **Graph 7 has 6 baselines** — Graph 7 now compares: No Fault-Tolerance, Centralized Heartbeat, Full Checkpoint, Round-Robin Recovery, Least-Queue Recovery, and Spider (Ours). The old 3-method names ("No Delegation", "Simple Retry") are deprecated.
