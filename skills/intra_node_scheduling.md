---
name: simulate-intra-node-scheduling
description: >-
  Use when the user asks to modify, test, or simulate the local intra-node scheduling (Phase 3 Edge Gateway or Phase 5 Fog Node).
  Includes context for TEE/EPC resource management and local queue processing.
---

# Instructions

1. **Identify the Component**: Determine whether you are working on the Edge Gateway (`phase3_edge_gateway`) or the Fog Node (`phase5_fog_node`) local execution.
2. **Simulate Local Queues**: Use the corresponding simulation files (e.g., `simulate_intra_node()` for local processing limits).
3. **Resource Constraints**:
   - Ensure you account for Enclave Page Cache (EPC) limitations. TEE execution is bottlenecked by EPC memory limits.
   - When processing tasks, subtract the cryptographic overhead (e.g., Dilithium verify time) from the available compute budget.
4. **Execution**: If asked to test the logic, run the specific module using `python -m` from the root directory.

## Constraints
- **Never** assume infinite EPC memory. All TEE simulations must enforce a strict memory or concurrency threshold (defined in `config.py`).
- **Never** modify the execution times of the cryptographic primitives (they are calibrated to actual hardware benchmarks from the paper).

## References
- See `config.py` for `TEE_MAX_CONCURRENCY` and standard cryptographic latencies.
