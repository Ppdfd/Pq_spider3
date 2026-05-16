# PQ-SPIDER Evaluation Framework
**Post-Quantum Secure and Dynamic Load-Balanced Encryption for IIoT Data in Fog Computing (Spider)**
This repository contains the simulation and evaluation framework for the PQ-SPIDER architecture. It models a complete end-to-end IIoT data pipeline, comparing our proposed approach ("Spider") against state-of-the-art reference implementations (Ref [4], Ref [37], Ref [39]).

---
## How to Run
### Run Everything (Tests + Graphs)
Set `GENERATE_GRAPHS = True` in `config.py`, then:

```bash
python run_all_tests.py
```
This runs the full 6-phase pipeline, profiles resource usage, and automatically generates all graphs at the end.

### Run Tests Only (No Graphs)
Set `GENERATE_GRAPHS = False` in `config.py`, then:

```bash
python run_all_tests.py
```
This runs all 6 phases and prints latency and resource usage tables, but skips graph generation for a faster run.

### Run Graphs Only
```bash
python run_all_graphs.py
```
This generates all 9 graphs (Graph 1-9) using the `graphs/` scripts. Outputs are saved to `graphs/spider_full_evaluation/` as `.png` files, with raw `.csv` data in the `raw/` subdirectory.

> **Note**: Graph scripts do NOT depend on previously generated test data. They run their own internal simulations.

---

## Run a Single Phase Test

Each phase has its own `main.py` that can be run independently. Phases are sequential, so earlier phases must be run first to generate the data files that later phases consume.

```bash
# Phase 1: System Initialization (generates keys, fog nodes, device registry)
python phase1_initialization/main.py

# Phase 2: IIoT Device Encryption (requires Phase 1 output)
python phase2_iiot_encrypt/main.py

# Phase 3: Edge Gateway Validation (requires Phase 2 output)
python phase3_edge_gateway/main.py

# Phase 4: Load Balancing (requires Phase 3 output)
python phase4_load_balance/main.py

# Phase 5: Fog Node Processing (requires Phase 4 output)
python phase5_fog_node/main.py

# Phase 6: User Decryption (requires Phase 5 output)
python phase6_user_decrypt/main.py
```

Each phase compares "Ours" vs "Ref [4]" and prints a comparison table. Metrics are saved to `{phase}/results/` and intermediate data to `{phase}/output/`.

---

## Run a Single Graph

You can run individual graph scripts directly from the project root:

```bash
python -c "from utils.eval_utils import *; from graphs.graph1 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph1_setup_phase(rng)"
```

For convenience, here is the command for each graph:

| Graph | What It Measures | Command |
|-------|-----------------|---------|
| Graph 1 | CP-ABE Setup Latency vs Attributes | `python -c "from utils.eval_utils import *; from graphs.graph1 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph1_setup_phase(rng)"` |
| Graph 2 | Cache Reuse Scheduling Latency | `python -c "from utils.eval_utils import *; from graphs.graph2 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph2_cache_reuse(rng)"` |
| Graph 3 | CP-ABE Encryption Cost at Fog | `python -c "from utils.eval_utils import *; from graphs.graph3 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph3_cpabe_encryption(rng)"` |
| Graph 4 | CP-ABE Decryption Cost at User | `python -c "from utils.eval_utils import *; from graphs.graph4 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph4_cpabe_decryption(rng)"` |
| Graph 5 | Load Balancing (Homogeneous) | `python -c "from utils.eval_utils import *; from graphs.graph5 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph_load_balancing(rng, 5, False)"` |
| Graph 6 | Load Balancing (Heterogeneous) | `python -c "from utils.eval_utils import *; from graphs.graph6 import *; ensure_dirs(); configure_matplotlib(); graph6_heterogeneous_fog()"` |
| Graph 7 | Recovery Time vs Failure Rate | `python -c "from utils.eval_utils import *; from graphs.graph7 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph7_recovery(rng)"` |
| Graph 8 | Intra-Node Enclave Scheduling | `python -c "from utils.eval_utils import *; from graphs.graph8 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); graph8_intra_enclave(rng)"` |
| Graph 9 | Routing Intelligence (uses Graph 8 data) | `python -c "from utils.eval_utils import *; from graphs.graph8 import *; from graphs.graph9 import *; rng=set_global_seed(GLOBAL_SEED); ensure_dirs(); configure_matplotlib(); r,e=run_graph8_experiment(rng); graph9_queue_state(r,e)"` |

All graph outputs are saved to `graphs/spider_full_evaluation/`.

---

## Configuration (`config.py`)

All simulation parameters are controlled from `config.py`. Key sections:

| Section | What It Controls |
|---------|-----------------|
| **1. Global Topology** | Number of fog nodes (`NUM_GLOBAL_NODES`) and devices (`NUM_DEVICES`) |
| **2. Hardware Constraints** | TEE memory budget (`EPC_BUDGET_BYTES`), enclaves per node (`ENC_PER_NODE`) |
| **3. OP-TEE Measured Values** | Service rate, world-switch latency, trust score from QEMU benchmarks |
| **4. Spider Load Balancer Weights** | All `W1`-`W8`, `Z1`-`Z4` weights for the scheduling cost function |
| **5. Data Sizes & Cryptography** | Payload size, CP-ABE attribute universe, user attributes |
| **6. Graph Control** | `GENERATE_GRAPHS` flag, offered load, affinity window |
| **7. Per-Graph Parameters** | `G1_*` through `G8_*` keys that control each graph's axes and sweep ranges |

### Example: Change graph resolution

To make Graph 1 run faster with fewer data points:
```python
# In config.py
G1_ATTR_RANGE = [5, 15, 25, 35, 45]  # fewer x-axis points
G1_REPS = 3                           # fewer repetitions
```

---

## Output Structure

```
{phase}/output/     -> Intermediate data (keys, ciphertexts, schedules)
{phase}/results/    -> Latency metrics JSON files
graphs/spider_full_evaluation/     -> Generated .png graphs
graphs/spider_full_evaluation/raw/ -> Raw .csv data dumps
```
