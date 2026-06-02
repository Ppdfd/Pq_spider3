---
name: generate-pq-spider-graphs
description: >-
  Use when the user asks to generate, update, or plot the evaluation graphs for PQ-SPIDER2.
  This skill handles writing the python graph scripts, calling simulation logic, and saving the generated output plots and raw data.
---

# Instructions

1. **Understand the Request**: Identify the metric, variables, and simulation logic the user wants to plot for the evaluation graph.
2. **Create the Graph Script**: Write or update a Python script (e.g., `graphs/graph11.py`) to run the necessary simulations and generate the plot.
   - Import necessary plotting and data handling utilities from `utils.eval_utils` (e.g., `OUT_DIR`, `RAW_DIR`, `plot_lines`, `save_csv`).
   - Run the relevant simulation functions to gather data.
   - write a configuration in config.py file.
   - logic in graph must be correctly derive from pq_spider references.
3. **Format and Output Data**:
   - Generate the plot using `matplotlib.pyplot` or `utils.eval_utils.plot_lines`.
   - Save the generated `.png` plot to `OUT_DIR` (e.g., `OUT_DIR / "graph11.png"`).
   - Save the raw underlying data as `.csv` to `RAW_DIR` using `save_csv` (e.g., `RAW_DIR / "graph11.csv"`).
4. **Execute and Verify**: Run the script as a module from the root directory (e.g., `python -m graphs.graph11`).
   - *Constraint*: Do not run it directly as `python graphs/graph11.py` to avoid `ModuleNotFoundError` for internal imports.
   - Verify the `.png` and `.csv` files are successfully created in their respective directories.
5. **Report Results**: inform user and write what you did and limitations of graph write the report in md file with name of that graph

## Constraints
- **Never** bias around our model to get better result than other algorithm
- **Never** modify the hardcoded baseline weights in `config.py` unless explicitly asked by the user, as this breaks fairness.
- **Never** use hardcoded data arrays in graph scripts; always call the corresponding simulation logic.
- **Never** assume the runtime eg. chacha.encrypt is 1.75 ms. the code must run logic to get the runtime.
- **Never** import graphs from others graph

## References
- See [PQ_SPIDER2_readable.txt](./papers/PQ_SPIDER2_readable.txt) for the original paper definitions and evaluation metrics.
- See `utils/eval_utils.py` for the shared plotting and data handling logic.
