# PQ-SPIDER Evaluation Framework

**Post-Quantum Secure and Dynamic Load-Balanced Encryption for IIoT Data in Fog Computing (Spider)**

This repository contains the simulation and evaluation framework for the PQ-SPIDER architecture. It models a complete end-to-end IIoT data pipeline, comparing our proposed approach ("Spider") against state-of-the-art reference implementations (Ref [4], Ref [37], Ref [39]).

The simulation correctly models queue buildup, cryptographic service times, cache locality, network jitter, TEE/REE split execution overheads, and EPC (Enclave Page Cache) pressure to provide accurate performance metrics.

---

## 🏗️ Architecture & Phases

The pipeline is divided into 6 discrete phases that simulate the journey of data from IIoT sensors to the end user:

1. **Phase 1: Initialization** (`phase1_initialization/`)
   - Generates cryptographic keys for IIoT devices, edge gateways, fog nodes, and users.
   - Bootstraps the CP-ABE (Ciphertext-Policy Attribute-Based Encryption) universe and TEE environments.
2. **Phase 2: IIoT Encrypt** (`phase2_iiot_encrypt/`)
   - Sensors encrypt telemetry using Post-Quantum symmetric/asymmetric primitives (e.g., Kyber, ChaCha20) and sign payloads.
3. **Phase 3: Edge Gateway** (`phase3_edge_gateway/`)
   - Validates signatures and aggregates data from multiple sensors.
4. **Phase 4: Load Balance** (`phase4_load_balance/`)
   - Our proposed dynamic load balancer. Distributes work across heterogeneous fog nodes.
   - Factors in queue wait times, CPU contention, hardware capabilities, cache affinity, and TEE EPC memory limits.
5. **Phase 5: Fog Node Processing** (`phase5_fog_node/`)
   - Fog nodes decrypt the IIoT payload inside the TEE and re-encrypt the data using CP-ABE for fine-grained access control before storing/forwarding.
6. **Phase 6: User Decrypt** (`phase6_user_decrypt/`)
   - The end user fetches the data and decrypts it using their CP-ABE secret keys.

---

## 🚀 How to Run

You can run the framework in two primary modes: **Testing (Profiling)** and **Graph Generation**.

### 1. Run the Full Pipeline (Tests & Profiling)

To execute all 6 phases sequentially, generate data, and profile resource usage (CPU time, Peak RSS Memory, Wall time):

```bash
python run_all_tests.py
```

**What happens?**
- The script runs `main.py` inside each phase directory.
- It tests "Ours" against all relevant reference implementations.
- Intermediate simulation data (keys, ciphertexts) are stored in `{phase_dir}/output/`.
- Latency and resource metrics are stored in `{phase_dir}/results/`.
- A consolidated resource usage table is printed at the end.

### 2. Generate Evaluation Graphs

To generate the IEEE-formatted publication-ready graphs:

```bash
python run_all_graphs.py
```

**What happens?**
- This orchestrates the scripts located in the `graphs/` directory.
- Graphs evaluate scalability, node heterogeneity, cache-reuse, scheduling, queue lengths, and EPC pressure.
- Outputs are saved to: `graphs/spider_full_evaluation/` (as `.png` files) along with raw `.csv` data dumps in the `raw/` subdirectory for auditing.

*Note: You can control whether `run_all_tests.py` also generates graphs by toggling the `GENERATE_GRAPHS` flag in `config.py`.*

---

## ⚙️ Configuration (`config.py`)

The `config.py` file acts as the single source of truth for the simulation's mathematical model and experimental parameters.

### Key Sections:

- **1. LATENCY & SYSTEM CONSTANTS**: 
  - Network latencies (`L_ij`, `L_jk`, `L_ku`), packet routing times, and baseline OP-TEE context switch overheads (`MEASURED_WORLD_SWITCH_MS`).
- **2. TEE & EPC METRICS**:
  - Constants for Enclave Page Cache penalties (`EPC_BASE_PENALTY_MS`), memory ceilings (`EPC_MAX_MEMORY_MB`), and the threshold for triggering admission control (`EPC_PRESSURE_TAU`).
- **3. LOAD BALANCER WEIGHTS**:
  - `W1_WAIT`: Weight for queue wait time in scheduling.
  - `Z2_ENC_EPC`: EPC penalty weight.
  - `Z3_ENC_CONTENTION`: Secondary contention factor.
  - `Z4_ENC_AFFIN`: Cache warmth/affinity bonus.
- **4. DATA SIZES & CRYPTO**:
  - Defines the simulated payload sizes (`PAYLOAD_SIZE_BYTES = 256`), GCM tag sizes, and the CP-ABE attribute universe.
- **6. GRAPH GENERATION**:
  - Defines the boolean flag `GENERATE_SPIDER_FULL_EVALUATION` to enable the heavy simulation loops for graph plotting.

If you wish to change the size of the simulated IIoT batches or alter the behavior of the load balancer's cost function (e.g., to see how ignoring cache affinity impacts latency), modify the respective variables in `config.py`.

---

## 📊 Outputs & Data Persistence

The project is designed to be modular. A phase cannot run unless the preceding phase has completed, as they rely on the artifacts written to disk via the `DataLoader` utility.

- **`{phase}/output/*.json`**: Contains the raw, deterministic "mock" payloads, keys, and batch configurations passed between phases.
- **`{phase}/results/*_metrics.json`**: Contains the profiled timings (latency breakdowns) for that specific phase, which the graphing scripts consume to plot comparative baselines.
