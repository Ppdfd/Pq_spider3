# Phase 4 — Spider Hierarchical Load Balancing Simulation

Discrete-event simulation engine for Spider's hierarchical enclave-oriented scheduling in heterogeneous fog-assisted IIoT environments. This module evaluates **inter-node** load balancing across fog nodes and **intra-node** scheduling across TEE enclaves, along with **Master Fog Node election** and **group-based fault tolerance**.

> **Note:** Unlike Phases 1–3 and 5–6, Phase 4 is not a standalone pipeline phase. It is a discrete-event simulation that produces evaluation data for **Graphs 5–9** and the fault-tolerance evaluation.

---

## Features

- **Inter-node scheduling (Level 1):** SpiderScore-based fog node selection (Eq 40) with TEE/REE dual-queue modeling, EPC pressure penalty, capability-aware routing, trust scoring, and computation-reuse bonus
- **Intra-node scheduling (Level 2):** EnclaveScore-based enclave selection (Eq 46) with EPC-aware admission control, workload affinity tracking, and queue-drain simulation
- **Baseline comparisons:** Fair evaluation against Ref[22] (OLB), Ref[37] (SDN-GH), and Ref[39] (DIST) for inter-node; Round-Robin and Least-Queue for intra-node
- **MFN election:** Enclave-aware and stability-aware Master Fog Node selection (Eq 112–116)
- **Fault tolerance:** Group-based heartbeat monitoring, quorum-based failure confirmation, secure delegation capsules, and SpiderScore-based recovery (Eq 117–125)
- **OP-TEE grounding:** Simulation parameters derived from real QEMU OP-TEE measurements (`optee_bench/measured_values.json`)

---

## Prerequisites

- Python 3.10+
- NumPy
- Project root `config.py` (contains all tunable weights `W1`–`W8`, `Z1`–`Z4`, and topology parameters)
- Phase 5 results at `phase5_fog_node/results/ours_metrics.json` (optional — falls back to 56.35ms default if missing)

---

## Module Structure

```
phase4_load_balance/
├── __init__.py              # Public API re-exports
├── params.py                # Cited simulation constants (EPC swap, contention, TEE startup)
├── models.py                # WorkloadTask, FogNode, Enclave dataclasses
├── generators.py            # Task stream, fog node, and enclave population generators
├── inter_node.py            # Level 1: inter-node scheduling (Spider + 3 baselines)
├── intra_node.py            # Level 2: intra-node enclave scheduling (Spider + 2 baselines)
├── mfn_election.py          # Master Fog Node election (Section IV)
├── failure_detection.py     # Group-based failure detection & recovery (Section V)
└── optee_bench/
    ├── measured_values.json  # OP-TEE QEMU benchmark results (service rate, world-switch, trust)
    ├── loader.py             # Patches config.py with measured values at runtime
    ├── pqspider_bench/       # OP-TEE TA source (C, built separately in QEMU)
    └── README.md             # OP-TEE setup instructions
```

---

## Usage

### Run via Graph Scripts (Recommended)

Phase 4 simulations are invoked by the graph scripts. Run from the **project root**:

```bash
# Graph 5: Homogeneous fog-node load balancing
python -m graphs.graph5

# Graph 6: Heterogeneous fog-node load balancing
python -m graphs.graph6

# Graph 7: Recovery latency under node failure
python -m graphs.graph7

# Graphs 8–9: Intra-node scheduling under OP-TEE heterogeneity
python -m graphs.graph8
python -m graphs.graph9
```

> **Important:** Always run as `python -m graphs.graphN` from the project root. Running `python graphs/graphN.py` directly will cause `ModuleNotFoundError`.

### Run All Graphs

```bash
python run_all_graphs.py
```

### Use the Simulation API Directly

```python
from phase4_load_balance import simulate_load_balancing, simulate_intra_node

# Inter-node: compare Spider vs baselines on 8 heterogeneous fog nodes
for alg in ["Spider (Ours)", "Ref[22]", "Ref[37]", "Ref[39]"]:
    latency = simulate_load_balancing(
        node_count=8,
        algorithm=alg,
        heterogeneous=True,
        seed=42,
    )
    print(f"{alg}: {latency:.2f} ms")

# Intra-node: compare enclave scheduling strategies
from phase4_load_balance import generate_enclaves
import numpy as np

enclaves = generate_enclaves(4, np.random.default_rng(42))
for alg in ["Spider (Ours)", "Round-Robin", "Least-Queue"]:
    latency = simulate_intra_node(
        n_tasks=500,
        algorithm=alg,
        base_enclaves=enclaves,
        seed=42,
    )
    print(f"{alg}: {latency:.2f} ms")
```

### MFN Election and Failure Detection

```python
from phase4_load_balance.mfn_election import simulate_mfn_election
from phase4_load_balance.failure_detection import simulate_failure_detection

# Run MFN election
result = simulate_mfn_election(n_nodes=10, seed=42)
print(f"Elected MFN: Node {result['elected_node_id']}")

# Run failure detection scenario
result = simulate_failure_detection(n_nodes=20, failure_rate=0.15, seed=42)
print(f"Detected: {result['n_detected']}/{result['n_injected_failures']} failures")
print(f"TPR: {result['true_positive_rate']:.2%}, FPR: {result['false_positive_rate']:.2%}")
```

---

## Configuration

All simulation parameters are controlled from `config.py` at the project root. Key settings:

### SpiderScore Weights (Inter-Node, Eq 40)

| Weight | Config Key | Controls |
|--------|-----------|----------|
| w₁ | `W1_WAIT` | Queue waiting time |
| w₂ | `W2_LATENCY` | Network latency |
| w₃ | `W3_EPC` | EPC pressure penalty |
| w₄ | `W4_CAP` | Capability mismatch |
| w₅ | `W5_TRUST` | Trust penalty |
| w₆ | `W6_URGENCY` | Urgency × trust bonus |
| w₇ | `W7_DEADLINE` | Deadline × service rate bonus |
| w₈ | `W8_REUSE` | Computation reuse bonus |

### EnclaveScore Weights (Intra-Node, Eq 46)

| Weight | Config Key | Controls |
|--------|-----------|----------|
| z₁ | `Z1_ENC_WAIT` | Enclave queue wait |
| z₂ | `Z2_ENC_EPC` | Enclave EPC pressure |
| z₃ | `Z3_ENC_CONTENTION` | World-switch contention |
| z₄ | `Z4_ENC_AFFIN` | Workload affinity bonus |

### Other Key Parameters

| Config Key | What It Controls |
|-----------|-----------------|
| `NUM_GLOBAL_NODES` | Default fog node count |
| `EPC_BUDGET_BYTES` | TEE memory budget |
| `ENC_PER_NODE` | Enclaves per fog node |
| `ALPHA_EPC_SAFETY` | EPC admission safety margin (Eq 49, α > 1) |
| `ENCLAVE_AFFINITY_WINDOW` | Sliding window for cache-warm tracking |
| `HEARTBEAT_TIMEOUT_MS` | Heartbeat timeout threshold τₕ (Eq 122) |
| `DEFAULT_GROUP_SIZE` | Monitoring group size s (Eq 118, 3 ≤ s ≤ 7) |

> **Constraint:** Never modify the baseline algorithm weights to make them artificially worse. All algorithms must share the same telemetry delay model and node populations for fair comparison.

---

## Simulation Parameters (`params.py`)

All simulation constants in `params.py` are derived from published literature and OP-TEE QEMU measurements. Key citations:

| Parameter | Value | Source |
|-----------|-------|--------|
| EPC swap base | 12.0 ms | SGX page-fault cycle counts [C], TLB shootdown [F] |
| EPC swap range | 8–18 ms | VAULT ASPLOS'18 realistic workloads [G] |
| Contention per unit | 1.13 ms | OP-TEE QEMU measured world-switch [A] |
| TEE startup | 2.6 ms | World-switch + TA session setup [A, D] |
| REE startup | 1.8 ms | Linux CFS scheduling quantum [D] |
| Finalization | 3.6 ms | Return world-switch + serialization [A] |

---

## Fairness Guarantees

The simulation enforces several fairness constraints to ensure unbiased evaluation:

1. **Shared task streams:** All algorithms receive the same task sequence generated from the same seed
2. **Shared node populations:** `clone_nodes()` / `clone_enclaves()` deep-copy initial state per algorithm
3. **Uniform telemetry delay:** All schedulers receive the same stochastic telemetry delay model
4. **No hardcoded results:** All evaluation data is derived from the simulation engine — never from hardcoded arrays

---

## Paper References

| Section | Equations | Module |
|---------|-----------|--------|
| Phase IV — Spider Scheduling | Eq 24–53 | `inter_node.py`, `intra_node.py` |
| Section IV — MFN Election | Eq 112–116 | `mfn_election.py` |
| Section V — Fault Tolerance | Eq 117–125 | `failure_detection.py` |
| Section VII — Evaluation | Graphs 5–9 | `graphs/graph5.py` – `graphs/graph9.py` |

Full paper: [`papers/PQ_SPIDER2_readable.txt`](../papers/PQ_SPIDER2_readable.txt)
