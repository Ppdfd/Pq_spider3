# Spider++ Evaluation Update

Added complete paper-style evaluation graph generation.

## Added files

- `evaluation/spiderpp_full_evaluation.py`
- `evaluation/__init__.py`
- `run_spiderpp_evaluation.py`
- `README_SPIDERPP_EVALUATION.md`

## Integrated behavior

- `config.py` now includes `GENERATE_SPIDERPP_FULL_EVALUATION = True`.
- `run_all_tests.py` automatically invokes the new graph generator when graph generation is enabled.
- Generated graphs and raw CSV data are included under:
  - `graphs/spiderpp_full_evaluation/`

## Graphs generated

- Graph 1: Initialization / Setup Phase
- Graph 2: Cache / Reuse-Aware Scheduling
- Graph 3: CP-ABE Encryption Cost at Fog
- Graph 4: CP-ABE Decryption Cost at User
- Graph 5: Homogeneous Fog Nodes
- Graph 6: Heterogeneous Fog Nodes
- Graph 7: Recovery Time vs Failure Rate
- Graph 8: Intra-node Scheduling under Enclave Heterogeneity
- Graph 9: Routing Intelligence — Task Distribution
- Graph 10: Heterogeneity Sensitivity
- Graph 11: Parameter Sensitivity Analysis
- Graph 12: Cumulative EPC Swap Events
- Graph 13: Latency CDF
- Graph 14: Deadline Compliance Rate
- Graph 15: Cache Affinity
- Graph 16: Enclave Scaling Analysis
