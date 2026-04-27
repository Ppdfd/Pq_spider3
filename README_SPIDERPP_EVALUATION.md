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
├── graph7_recovery_time_failure_rate.png/.pdf
├── graph8_intra_node_scheduling.png/.pdf
├── graph9_queue_state.png/.pdf
├── graph10_contention.png/.pdf
├── graph11_sensitivity.png/.pdf
├── graph12_epc_availability.png/.pdf
├── graph13_load_imbalance.png/.pdf
├── graph14_deadline.png/.pdf
├── graph15_cache_reuse.png/.pdf
├── graph16_enclave_scaling.png/.pdf
└── raw/
    └── CSV data for every graph
```

## Fairness notes

The simulator uses the same synthetic task streams and fog-node populations for every compared scheduler in each run. The model adds queue buildup, network jitter, heterogeneous CPU/TEE/REE service rates, cache locality, EPC pressure, and node failure behavior. The data are transparent in CSV files so the plotted values can be audited directly.
