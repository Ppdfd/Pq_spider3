# Spider Full Evaluation Graphs

This module provides the complete simulation-based evaluation for:

**Post-Quantum Secure and Dynamic Load-Balanced Encryption for IIoT Data in Fog Computing (Spider)**

## How to Run

To generate all 15 performance evaluation graphs (Graphs 1-15), run the master graph generator from the project root:

to generate graph
-python run_all_graphs.py
to generate test and graph
-set config.py -> GENERATE_GRAPHS = True
```bash
python run_all_tests.py
```

## qemu is write in folder phase4/optee_bench
host is ree
ta is tee

This script automatically seeds the random number generators, initializes the directories, and runs all necessary simulation sweeps across the system phases.

## Generated output

Once complete, the generated graphs will be saved to:

```text
graphs/spider_full_evaluation/
├── graph1_setup_phase.png/.pdf
├── graph2_cache_reuse_scheduling.png/.pdf
├── graph3_cpabe_encryption_fog.png/.pdf
├── graph4_cpabe_decryption_user.png/.pdf
├── graph5_homogeneous_fog_nodes.png/.pdf
├── graph6_heterogeneous_fog_nodes.png/.pdf
├── graph7_recovery_time_failure_rate.png/.pdf
├── graph8_intra_node_scheduling.png/.pdf
├── graph9_queue_state.png/.pdf
├── graph10_sensitivity.png/.pdf
├── graph11_epc_availability.png/.pdf
├── graph12_load_imbalance.png/.pdf
├── graph13_deadline.png/.pdf
├── graph14_cache_reuse.png/.pdf
├── graph15_enclave_scaling.png/.pdf
└── raw/
    └── CSV data for every graph
```

## Fairness notes

The simulator uses the same synthetic task streams and fog-node populations for every compared scheduler in each run. The model adds queue buildup, network jitter, heterogeneous CPU/TEE/REE service rates, cache locality, EPC pressure, and node failure behavior. The data are transparent in CSV files so the plotted values can be audited directly.
