---
name: simulate-load-balancing
description: >-
  Use when the user asks to run, test, or modify the inter-node load balancing (Phase 4) simulation.
  Includes context for how SpiderScore is calculated and how baselines are modeled.
---

# Instructions

1. **Understand the Request**: Identify if the user wants to simulate homogeneous or heterogeneous fog nodes, and which algorithm to focus on (Spider, Ref[22], Ref[37], Ref[39]).
2. **Execute the Simulation**: Use `simulate_load_balancing()` from `phase4_load_balance.inter_node`.
   - Provide the exact parameters: `node_count`, `algorithm`, `heterogeneous` flag, and `seed`.
3. **Verify the Output**: Ensure that the simulation returns a valid latency float.
4. **Modify Weights (If requested)**: 
   - All SpiderScore weights (W1-W8) and simulation constants are defined in `config.py`.
   - Modify `config.py` directly to tune the scheduler's behavior. DO NOT hardcode weights in `inter_node.py`.

## Constraints
- **Never** modify the baseline algorithms (Ref[22], Ref[37], Ref[39]) to make them artificially worse. They must share the same telemetry delay and network models as Spider.
- **Never** bypass the `simulate_load_balancing` function when generating load balancing data.

## References
- See [inter_node.py](../phase4_load_balance/inter_node.py) for the core SpiderScore calculation (Eq 40).
- See [config.py](../config.py) for all tunable weights.
