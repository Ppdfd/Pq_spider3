# PQ-SPIDER Evaluation Framework
**Post-Quantum Secure and Dynamic Load-Balanced Encryption for IIoT Data in Fog Computing (Spider)**
This repository contains the simulation and evaluation framework for the PQ-SPIDER architecture. It models a complete end-to-end IIoT data pipeline, comparing our proposed approach ("Spider") against state-of-the-art reference implementations (Ref[4], Ref[37], Ref[39]).

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

# Phase 5: Fog Node Processing (requires Phase 3 output)
python phase5_fog_node/main.py

# Phase 6: User Decryption (requires Phase 5 output)
python phase6_user_decrypt/main.py
```
Each phase compares "Ours" vs "Ref [4]" and prints a comparison table. Metrics are saved to `{phase}/results/` and intermediate data to `{phase}/output/`.

> **Note on Phase 4**: The load balancing evaluation (Graphs 5–9) is implemented as a discrete-event simulation in `phase4_load_balance/` (split across `inter_node.py` and `intra_node.py`), not as a standalone pipeline phase. The `phase4_load_balance/optee_bench/` subdirectory contains OP-TEE QEMU measurement data used by the graph simulations. See `phase4_load_balance/README.md` for details.

---

## Run a Single Graph
you can comment in run_all_graphs.py graph you don't want to generated
## Run a generate Task function 
in graphs/generateTask.py
```bash
python graphs/generateTask.py
```

## Configuration (`config.py`)
All simulation parameters are controlled from `config.py`. Key sections:

For IIoT data input, you can modify `input_data.json` in `phase2_iiot_encrypt/`.

|               Section               |                               What It Controls                              |
|-------------------------------------|-----------------------------------------------------------------------------|
| **1. Global Topology**              | Number of fog nodes (`NUM_GLOBAL_NODES`) and devices (`NUM_DEVICES`)        |  
| **2. Hardware Constraints**         | TEE memory budget (`EPC_BUDGET_BYTES`), enclaves per node (`ENC_PER_NODE`)  |
| **3. OP-TEE Measured Values**       | Service rate, world-switch latency, trust score from QEMU benchmarks        |
| **4. Spider Load Balancer Weights** | All `W1`-`W8`, `Z1`-`Z4` weights for the scheduling cost function           |
| **5. Data Sizes & Cryptography**    | Payload size, CP-ABE attribute universe, user attributes                    |
| **6. Graph Control**                | `GENERATE_GRAPHS` flag, offered load, affinity window                       |
| **7. Per-Graph Parameters**         | `G1_*` through `G8_*` keys that control each graph's axes and sweep ranges  |

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
{phase}/output/     -> Intermediate data (keys, ciphertexts)
{phase}/results/    -> Latency metrics JSON files
graphs/spider_full_evaluation/     -> Generated .png graphs
graphs/spider_full_evaluation/raw/ -> Raw .csv data dumps
```
Noted: there is no raw/graph9 because it generated from graph8 data
