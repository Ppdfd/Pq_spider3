---
name: generate-pq-spider-graphs
description: >-
  Use when the user asks to generate, update, or plot the evaluation graphs for PQ-SPIDER2 (graphs 1 through 10).
  This skill handles running the python scripts, checking the output, and formatting the results.
---

# Instructions

1. **Understand the Request**: Identify which graph(s) the user wants to generate (e.g., Graph 10 for fault-tolerance, Graph 6 for heterogeneous load-balancing).
2. **Execute the Script**: Run the graph generation script as a module from the root directory.
   - Example: `python -m graphs.graph10`
   - *Constraint*: Do not use `python graphs/graph10.py` directly as it will cause `ModuleNotFoundError` for internal imports.
3. **Verify the Output**: Check the `graphs/spider_full_evaluation/` directory for the generated `.png` files and the `raw/` subdirectory for the corresponding `.csv` files.
4. **Report Results**: Inform the user that the graphs have been generated and provide the path to the output directory.

## Constraints
- **Never** modify the hardcoded baseline weights in `config.py` unless explicitly asked by the user, as this breaks fairness.
- **Never** use hardcoded data arrays in graph scripts; always call the corresponding simulation logic.

## References
- See [PQ_SPIDER2_readable.txt](./papers/PQ_SPIDER2_readable.txt) for the original paper definitions and evaluation metrics.
- See `utils/eval_utils.py` for the shared plotting and data handling logic.
