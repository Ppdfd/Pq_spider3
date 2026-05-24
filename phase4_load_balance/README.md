# Phase 4 — Load Balancing

## Module Structure

This directory contains the **load balancing simulation engine** used by
Graphs 5–9 in the paper, plus the **OP-TEE QEMU measurement data** used
by both the graph simulations and the pipeline phases.

### Simulation Engine

The simulation engine implements a custom discrete-event simulator with
TEE-specific resource modelling (EPC memory, enclave contention, world-switch
overhead) — features not available in existing fog simulators (iFogSim,
YAFS, CloudSim).

```
phase4_load_balance/
├── params.py           # SIMULATION_PARAMS — cited constants with derivations
├── models.py           # WorkloadTask, FogNode, Enclave dataclasses
├── generators.py       # Task/node/enclave population generators
├── inter_node.py       # Level 1: inter-node scheduling (Spider, Ref[22/37/39])
├── intra_node.py       # Level 2: intra-node enclave scheduling (Spider, RR, LQ)
├── __init__.py         # Re-exports all public symbols
│
└── optee_bench/
    ├── loader.py              # Loads measured_values.json into config at runtime
    ├── measured_values.json   # OP-TEE QEMU benchmark measurements
    └── pqspider_bench/        # Source code for the OP-TEE TA benchmark
```

### Graph Scripts

The graph **plotting scripts** remain in `graphs/`:
- **Inter-node scheduling (Graphs 5, 6, 7):** `graphs/graph5.py`, `graph6.py`, `graph7.py`
  → calls `phase4_load_balance.inter_node.simulate_load_balancing()`
- **Intra-node scheduling (Graphs 8, 9):** `graphs/graph8.py`, `graph9.py`
  → calls `phase4_load_balance.intra_node.simulate_intra_node()`
- **All scoring equations (Eq 32–47):** `phase4_load_balance/inter_node.py` and `intra_node.py`

### Backward Compatibility

`graphs/simulation_core.py` remains as a **backward-compatibility shim** that
re-exports all symbols from `phase4_load_balance.*`. Existing code that imports
from `graphs.simulation_core` will continue to work.
