# Phase 4 — Load Balancing

## Note on Code Structure

The Phase 4 **load balancing evaluation** (Graphs 5–9 in the paper) is implemented
in `graphs/simulation_core.py`, which runs a discrete-event simulation with
identical task streams and node populations across all algorithms (Spider, Ref[22],
Ref[37], Ref[39]).

This directory only contains `optee_bench/` — the **OP-TEE QEMU measurement data
and loader** used by both the graph simulations and the pipeline phases.  The
standalone scheduling scripts (e.g. `ours.py`, `ref_22.py`, `main.py`) were removed
because they used a different scoring model than the graph simulations, which are the
source of the paper's reported results.

### What's here

```
optee_bench/
  ├── loader.py              # Loads measured_values.json into config at runtime
  ├── measured_values.json   # OP-TEE QEMU benchmark measurements
  └── pqspider_bench/        # Source code for the OP-TEE TA benchmark
```

### Where to find the load balancing evaluation

- **Inter-node scheduling (Graphs 5, 6, 7):** `graphs/graph5.py`, `graph7.py`
  → calls `simulation_core.simulate_load_balancing()`
- **Intra-node scheduling (Graphs 8, 9):** `graphs/graph8.py`, `graph9.py`
  → calls `simulation_core.simulate_intra_node()`
- **All scoring equations (Eq 32–47):** `graphs/simulation_core.py`
