---
name: evaluate-fault-tolerance
description: >-
  Use when the user asks to simulate, test, or modify the fault tolerance and failure detection mechanisms.
  Includes context for how the group-based heartbeat and SpiderScore recovery work.
---

# Instructions

1. **Understand the Request**: Identify which metric the user is interested in (e.g., detection time, false positive rate, completion ratio).
2. **Execute the Simulation**: Use `simulate_failure_detection()` from `phase4_load_balance.failure_detection`.
   - Provide the exact parameters: `n_nodes`, `failure_rate`, and `seed`.
3. **Verify the Output**: Ensure that the simulation returns the correct metrics dictionary (true_positive_rate, false_positive_rate, detection_time_ms, etc.).
4. **Modify Groups (If requested)**: 
   - Group size constraints (3 <= s <= 7) and heartbeat timeouts (`HEARTBEAT_TIMEOUT_MS`) are located in `config.py`.

## Constraints
- **Never** modify the quorum confirmation logic (Eq 123) directly unless there's a mathematical error in the paper's representation.
- **Never** use hardcoded recovery metrics in graphs; always derive them from the simulation engine or mathematical models representing the specific method.

## References
- See [failure_detection.py](../phase4_load_balance/failure_detection.py) for the core heartbeat and detection logic.
- See [graph10.py](../graphs/graph10.py) for how to correctly model the various fault tolerance baselines in comparison to Spider.
