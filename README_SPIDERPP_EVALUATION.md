# Spider++ Full Evaluation Graphs

This update adds a complete simulation-based evaluation module for:

**Post-Quantum Secure and Dynamic Load-Balanced Encryption for IIoT Data in Fog Computing (Spider++)**

## Run

From the project root:

```bash
python3 run_spiderpp_evaluation.py
```

or through the full pipeline:

```bash
python3 run_all_tests.py
```

`run_all_tests.py` now calls the Spider++ full graph generator when:

```python
GENERATE_GRAPHS = True
GENERATE_SPIDERPP_FULL_EVALUATION = True
```

## Generated output

```text
graphs/spiderpp_full_evaluation/
├── graph1_setup_phase.png/.pdf
├── graph2_cache_reuse_scheduling.png/.pdf
├── graph3_cpabe_encryption_fog.png/.pdf
├── graph4_cpabe_decryption_user.png/.pdf
├── graph5_homogeneous_fog_nodes.png/.pdf
├── graph6_heterogeneous_fog_nodes.png/.pdf
├── graph8_recovery_time_failure_rate.png/.pdf
└── raw/
    └── CSV data for every graph
```

Graph 7 is intentionally skipped because the requested experiment excludes intra-node multi-enclave scheduling.

## Fairness notes

The simulator uses the same synthetic task streams and fog-node populations for every compared scheduler in each run. The model adds queue buildup, network jitter, heterogeneous CPU/TEE/REE service rates, cache locality, EPC pressure, and node failure behavior. The data are transparent in CSV files so the plotted values can be audited directly.
