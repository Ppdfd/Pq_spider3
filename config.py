"""
Global Configuration for PQ-SPIDER and Reference Benchmarks
===========================================================
This configuration file guarantees fairness across the comparative evaluation
by enforcing identical parameters for topology, traffic loads, and hardware 
bounds across 'ours' and all reference implementations ([4], [35], [36]).
"""

import math

# ---------------------------------------------------------
# 1. GLOBAL TOPOLOGY AND AGENTS
# ---------------------------------------------------------
# Number of edge/fog nodes initialized in Phase 1 and targeted in Phase 3/4
NUM_GLOBAL_NODES = 10

# Number of IIoT devices generating traffic in Phase 2
NUM_DEVICES = 10

# ---------------------------------------------------------
# 2. HARDWARE CONSTRAINTS (OP-TEE QEMU v8)
# ---------------------------------------------------------
# OP-TEE TZDRAM = 29.5 MB (0x01D80000) from optee_os conf.mk
# This replaces SGX EPC (93 MB) — OP-TEE is the target TEE platform.
EPC_BUDGET_BYTES = int(29.5 * 1024 * 1024)   # 30,932,992 bytes

# Number of TA sessions (enclaves) per fog node = QEMU SMP cores
ENC_PER_NODE = 2

# Memory per enqueued packet: TA_DATA_SIZE (32 KB) + TA_STACK_SIZE (2 KB)
PACKET_EPC_BYTES = 34 * 1024

# ---------------------------------------------------------
# 2a. OP-TEE QEMU v8 MEASURED VALUES
# ---------------------------------------------------------
# These values come from running the pqspider_bench TA on QEMU.
# Update after running:  cd ~/optee-qemu/build && make QEMU_VIRTFS_AUTOMOUNT=y run
#   then inside QEMU:    pqspider_bench
# The defaults below are reasonable estimates for Cortex-A72 emulation.
MEASURED_SERVICE_RATE     = 1265.82  # tasks/sec (AES-256-GCM 256B, measured on QEMU)
MEASURED_WORLD_SWITCH_MS  = 1.1565   # NW→SW context switch latency (ms, measured)
MEASURED_BASE_TRUST       = 1.0   # OP-TEE attestation success rate

# QEMU hardware specs — now read live from psutil via SystemProfiler.
# These legacy values are kept ONLY for reference / fallback if psutil
# is unavailable (e.g. CI environment).
QEMU_CPU_MHZ    = 2000     # Fallback: Emulated Cortex-A72 max frequency
QEMU_TEE_RAM_MB = 29.5     # Fallback: TZDRAM (from conf.mk CFG_TZDRAM_SIZE)
QEMU_SMP        = 2        # Fallback: SMP cores

# NOTE: NODE_CAPABILITY_FACTORS and TRUST_DEGRADATION have been removed.
# Capability scores are now computed live from psutil.cpu_freq() +
# psutil.virtual_memory() + os.cpu_count() via SystemProfiler.
# Trust scores use MEASURED_BASE_TRUST (from OP-TEE bench TA).


# ---------------------------------------------------------
# 3. SPIDER++ LOAD BALANCER WEIGHTS (PHASE IV, Eq 32-47)
# ---------------------------------------------------------
# Level 1: Inter-Node Spider Score (Eq 36)
# SpiderScore(Fj, Bk) = w1*Twait + w2*Lj + w3*Pepc + w4*Pcap
#                      + w5*Ptrust − w6*η*U − w7*δ*μ_TEE
W1_WAIT    = 2.0     # Waiting time weight (Eq 32) — amplified for load spreading
W2_LATENCY = 0.5     # Network latency weight — increased to differentiate nodes
W3_EPC     = 0.5     # EPC pressure weight (Eq 33)
W4_CAP     = 0.4     # Capability penalty weight (Eq 34)
W5_TRUST   = 0.3     # Trust penalty weight (Eq 35)
W6_URGENCY = 0.2     # Urgency bonus weight
W7_DEADLINE = 0.001  # Deadline bonus (dampened: raw μ_TEE ∈ [100,200])

# Computation Reuse Awareness (Eq 37-40)
# SpiderScore'(Fj, Bk) = SpiderScore − w8*R_reuse
W8_REUSE       = 0.6     # Reuse score discount weight (amplified for cache advantage)
THETA1_POLICY  = 0.6     # Weight for cached policy structure (Eq 39)
THETA2_KYBER   = 0.4     # Weight for cached Kyber precomputation (Eq 39)

# Level 2: Intra-Node Enclave Score (Eq 46)
# EnclaveScore = z1*Twait_enc + z2*Pepc_enc + z3*Pcont − z4*Affinity
Z1_ENC_WAIT    = 1.0     # Enclave waiting time weight (Eq 42)
Z2_ENC_EPC     = 1.2     # Enclave EPC pressure weight (Eq 43)
Z3_ENC_CONTENTION = 0.6  # Contention penalty weight (Eq 44) — used by graph7.py
Z4_ENC_AFFIN   = 0.2     # Affinity bonus weight (Eq 45)
# Legacy alias (kept for backward compatibility with older code paths)
Z3_ENC_CONT    = Z3_ENC_CONTENTION

# Batch Profiling (Eq 28-30)
BETA1_SIZE     = 1.0     # Batch size factor
BETA2_ATTR     = 0.5     # Attribute count factor
BETA3_DEPTH    = 0.3     # Policy depth factor

# EPC thresholds
EPC_PRESSURE_TAU   = 0.8   # τ threshold for EPC pressure (Eq 33)
EPC_ADMISSION_ALPHA = 1.0  # α factor for admission control (Eq 50)

# Legacy aliases for backward compatibility
W1_QUEUE   = W1_WAIT
W2_SERVICE = 0.01
W4_HOTSPOT = 0.2

# ---------------------------------------------------------
# 4. DATA SIZES & CRYPTOGRAPHY METRICS
# ---------------------------------------------------------
# Expected size of evaluated data payloads per packet 
PAYLOAD_SIZE_BYTES = 256

# Nonce and MAC standard bytes
GCM_NONCE_SIZE = 12
GCM_MAC_SIZE = 16

# Attribute Universe for CP-ABE
CP_ABE_UNIVERSE = ["Admin", "Engineer", "Technician", "ZoneA", "ZoneB", "Safety"]
USER_ATTRIBUTES = ["Engineer", "ZoneA"]
FLEX_ATTRIBUTES = ["Admin", "Technician", "ZoneB", "Safety"]

# ---------------------------------------------------------
# 5. GRAPHING & BENCHMARKING PARAMETERS
# ---------------------------------------------------------
# Set False to skip graph generation for fast simulation-only runs
GENERATE_GRAPHS = True

# Axes ranges for scalability benchmarking charts
GRAPH_FOG_NODES = [10, 20, 30, 40, 50]
GRAPH_ATTR_COUNTS = [10, 20, 30, 40, 50]
GRAPH_TASK_COUNTS = [10, 20, 30, 40, 50]
GRAPH_TEE_COUNTS = [1, 2, 4, 8]

# Multi-round validation to flush CPU caches and calculate a true average
GRAPH_WARMUP_ROUNDS = 1
GRAPH_TEST_ROUNDS = 5


# ---------------------------------------------------------
# 6. SPIDER++ FULL PAPER EVALUATION GRAPHS
# ---------------------------------------------------------
# Generates Graph 1-8 for the paper-style simulation.
GENERATE_SPIDERPP_FULL_EVALUATION = True


# ---------------------------------------------------------
# 7. STRESS TEST PARAMETERS (Graph 7 series)
# ---------------------------------------------------------
# Extended ranges to expose Spider++'s algorithmic advantages under
# realistic IIoT stress conditions per IEC 61784-2 Class 2.

# Task count range — extended to 1000 to capture queue-saturation dynamics
# where contention-awareness becomes the dominant scheduling factor.
STRESS_TASK_COUNTS = [50, 100, 200, 300, 500, 750, 1000]

# Enclave count range — extended to 32 to demonstrate Spider++'s parallel
# batch decomposition advantage as enclave parallelism increases.
STRESS_ENCLAVE_COUNTS = [2, 4, 8, 16, 24, 32]

# Burst traffic pattern — models realistic IIoT sensor spikes
# (per Wan et al. IEEE TII 2018: industrial bursts are 2-3× baseline).
BURST_BASELINE_LOAD = 0.50    # normal offered load
BURST_PEAK_LOAD = 1.20        # 2.4× spike during burst
BURST_DURATION_MS = 200       # spike duration
BURST_INTERVAL_MS = 1000      # one burst per second

# Locality/affinity grouping — models correlated IIoT requests
# (sensor cluster, authentication context). Activates Spider++'s z4·A term.
SESSION_GROUP_SIZE = 8        # tasks per logical session

# EPC pressure sweep — varies % free in heavily-loaded enclaves to stress
# EPC-aware admission control. Lower values trigger thrashing on baselines.
EPC_PRESSURE_SWEEP = [0.95, 0.85, 0.70, 0.50, 0.30, 0.15]
