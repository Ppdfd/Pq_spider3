"""
Global Configuration for PQ-SPIDER and Reference Benchmarks
===========================================================
This configuration file guarantees fairness across the comparative evaluation
by enforcing identical parameters for topology, traffic loads, and hardware
bounds across 'ours' and all reference implementations ([4], [37], [39]).
"""
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
# 3. OP-TEE QEMU v8 MEASURED VALUES
# ---------------------------------------------------------
# These values come from running the pqspider_bench TA on QEMU.
# Update after running:  cd ~/optee-qemu/build && make QEMU_VIRTFS_AUTOMOUNT=y run
#   then inside QEMU:    pqspider_bench
# The defaults below are reasonable estimates for Cortex-A72 emulation.
MEASURED_SERVICE_RATE     = 1265.82  # tasks/sec (AES-256-GCM 256B, measured on QEMU)
MEASURED_WORLD_SWITCH_MS  = 1.1565   # NW->SW context switch latency (ms, measured)
MEASURED_BASE_TRUST       = 1.0      # OP-TEE attestation success rate
# QEMU hardware specs -- now read live from psutil via SystemProfiler.
# These legacy values are kept ONLY for reference / fallback if psutil
# is unavailable (e.g. CI environment).
QEMU_CPU_MHZ    = 2000     # Fallback: Emulated Cortex-A72 max frequency
QEMU_TEE_RAM_MB = 29.5     # Fallback: TZDRAM (from conf.mk CFG_TZDRAM_SIZE)
QEMU_SMP        = 2        # Fallback: SMP cores

# ---------------------------------------------------------
# 4. SPIDER++ LOAD BALANCER WEIGHTS (PHASE IV, Eq 32-47)
# ---------------------------------------------------------
# Level 1: Inter-Node Spider Score (Eq 36)
# SpiderScore(Fj, Bk) = w1*Twait + w2*Lj + w3*Pepc + w4*Pcap
#                      + w5*Ptrust - w6*eta*U - w7*delta*mu_TEE
W1_WAIT    = 2.0     # Waiting time weight (Eq 32)
W2_LATENCY = 0.5     # Network latency weight
W3_EPC     = 0.5     # EPC pressure weight (Eq 33)
W4_CAP     = 0.4     # Capability penalty weight (Eq 34)
W5_TRUST   = 0.3     # Trust penalty weight (Eq 35)
W6_URGENCY = 0.2     # Urgency bonus weight
W7_DEADLINE = 0.001  # Deadline bonus (dampened: raw mu_TEE in [100,200])
# Computation Reuse Awareness (Eq 37-40)
# SpiderScore'(Fj, Bk) = SpiderScore - w8*R_reuse
W8_REUSE       = 0.6     # Reuse score discount weight
THETA1_POLICY  = 0.6     # Weight for cached policy structure (Eq 39)
THETA2_KYBER   = 0.4     # Weight for cached Kyber precomputation (Eq 39)

# Level 2: Intra-Node Enclave Score (Eq 46)
# EnclaveScore = z1*Twait_enc + z2*Pepc_enc + z3*Pcont - z4*Affinity
#
# CALIBRATION RATIONALE (verified empirically at offered_load=0.70):
# At 70% utilization, the dominant cost component is queue wait time,
# not EPC pressure. Empirical measurements show:
#   - Queue wait:       ~700ms average  <- DOMINANT cost
#   - Queue penalty:    ~50ms x queue_length (load-balancing term)
#   - Contention base:  ~2ms (world-switch overhead)
#   - EPC swap:         ~12ms (when triggered, rare at 70% load)
#
# Weights are calibrated to match these magnitudes. P_cont was redesigned
# to include explicit queue-imbalance penalty (q x service_est) so that
# Spider behaves like Join-Shortest-Queue (JSQ, optimal under M/M/n)
# when EPC and rate signals don't dominate.
Z1_ENC_WAIT       = 1.0     # baseline weight (queue wait dominates at 70% load)
Z2_ENC_EPC        = 0.05    # EPC penalty (12ms) is ~1/58 of queue wait
Z3_ENC_CONTENTION = 0.50    # queue-balancing term
Z4_ENC_AFFIN      = 5.0     # cache warmth bonus
# Legacy alias (kept for backward compatibility)
Z3_ENC_CONT       = Z3_ENC_CONTENTION

# Batch Profiling (Eq 28-30)
BETA1_SIZE     = 1.0     # Batch size factor
BETA2_ATTR     = 0.5     # Attribute count factor
BETA3_DEPTH    = 0.3     # Policy depth factor
# EPC thresholds
EPC_PRESSURE_TAU = 0.8   # tau threshold for EPC pressure (Eq 29)
EPC_KAPPA = 10.0         # κ: sigmoid overload sensitivity (Eq 29)
# EPC admission control (Eq 49): M_free >= ALPHA_EPC_SAFETY * M_req
ALPHA_EPC_SAFETY = 1.15  # safety margin for enclave EPC admission

# Baseline rate: normalized service rate from OP-TEE QEMU measurements.
# Used by intra-node scheduler and executor to scale enclave service times.
MEASURED_BASELINE_RATE = MEASURED_SERVICE_RATE / 1000.0  # 1265.82/1000 = 1.26582

# ---------------------------------------------------------
# 4b. FAILURE DETECTION & RECOVERY (SECTION V, Eq 117-125)
# ---------------------------------------------------------
# Monitoring group bounds (Eq 117-118)
GROUP_SIZE_MIN     = 3       # minimum peers per monitoring group
GROUP_SIZE_MAX     = 7       # maximum peers per monitoring group
DEFAULT_GROUP_SIZE = 5       # preferred group size s
# Heartbeat timeout (Eq 121-122)
HEARTBEAT_TIMEOUT_MS = 50.0  # tau_h: ms before a peer is flagged suspicious
# Quorum fraction (Eq 123): failure confirmed if >= ceil(s * QUORUM_FRACTION)
QUORUM_FRACTION    = 0.5

# ---------------------------------------------------------
# 4c. MFN ELECTION (SECTION IV, Eq 112-116)
# ---------------------------------------------------------
# Scoring weights (Eq 112)
ALPHA1_CAPABILITY = 0.30
ALPHA2_MEMORY     = 0.20
ALPHA3_NETWORK    = 0.15
ALPHA4_READINESS  = 0.25
ALPHA5_TRUST      = 0.10
# Readiness weights (Eq 113)
MFN_BETA1_ENCLAVE_QUEUE = 0.40
MFN_BETA2_EPC_PRESSURE  = 0.35
MFN_BETA3_REE_BACKLOG   = 0.25
# Stability penalty (Eq 115)
GAMMA_STABILITY   = 0.20
# Readiness threshold (Eq 116)
TAU_READINESS     = 0.30

# ---------------------------------------------------------
# 5. DATA SIZES & CRYPTOGRAPHY
# ---------------------------------------------------------
# Expected size of evaluated data payloads per packet
PAYLOAD_SIZE_BYTES = 256
# Attribute Universe for CP-ABE
CP_ABE_UNIVERSE = ["Admin", "Engineer", "Technician", "ZoneA", "ZoneB", "Safety"]
USER_ATTRIBUTES = ["Engineer", "ZoneA", "Safety"]
# (reference [4])
FLEX_ATTRIBUTES = ["Admin", "Technician", "ZoneB", "Safety"]

# ---------------------------------------------------------
# 6. GRAPH CONTROL
# ---------------------------------------------------------
# Set False to skip graph generation for fast simulation-only runs
GENERATE_GRAPHS = True
# Offered load for intra-node experiments (graphs 8/9).
# 0.70 matches IEC 61784-2 Class 2 industrial network targets.
INTRA_NODE_OFFERED_LOAD = 0.70
# Affinity decay window -- how many recent tasks count toward the
# "warm cache" bonus. Without this cap, recent_count grows unbounded
# and every enclave appears equally warm, neutralizing the affinity term.
ENCLAVE_AFFINITY_WINDOW = 20

# ---------------------------------------------------------
# 7. PER-GRAPH PARAMETERS
# ---------------------------------------------------------
# Graph 1: CP-ABE Setup Latency vs Number of Attributes
G1_ATTR_RANGE = list(range(5, 55, 5))
G1_REPS = 15

# Graph 2: Cache Reuse at Edge Gateway (Sweeps tasks)
G2_NUM_TASKS = list(range(100, 2100, 100))
G2_NUM_FOGS = 5

# Graph 3: CP-ABE Encryption Latency at Fog Node
G3_NUM_TASKS = 20
G3_ATTR_RANGE = list(range(5, 55, 5))
G3_REPS = 3

# Graph 4: User Decryption Latency
G4_NUM_TASKS = 20
G4_ATTR_RANGE = list(range(5, 55, 5))
G4_REPS = 3

# Graph 5: Load Balancing Latency (Sweeps Number of Fog Nodes)
G5_NUM_TASKS = 500
G5_NUM_FOGS = [2, 4, 6, 8, 10, 12]

# Graph 6: Heterogeneous Fog Nodes Load Balancing
G6_NUM_TASKS = 500
G6_NUM_FOGS = [2, 4, 6, 8, 10, 12]


# Graph 7: Intra-Node Scheduling & Queue State Diagnosis
G7_NUM_TASKS = 500
G7_NUM_TEES = 4
G7_SPREAD_FACTORS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]

# Graph 8: Recovery Latency vs Number of Fog Nodes
G8_FOG_COUNTS = [10, 20, 30, 40, 50]
G8_FAILURE_RATE = 0.15
G8_REPS = 5

# Graph 9: Task Completion Ratio vs Failure Rate
G9_NUM_FOGS = 30
G9_FAILURE_RATES = [0.05, 0.10, 0.15, 0.20, 0.25]
G9_REPS = 5

# Fault-Tolerance Baselines (Section VII-C)
CHECKPOINT_INTERVAL_MS = 100.0
CHECKPOINT_SYNC_OVERHEAD_MS = 15.0
CENTRALIZED_EXTRA_DELAY_MS = 8.0

# Recovery simulation parameters (Graph 8-9)
G8_N_TASKS = 200                     # Number of tasks to simulate per scenario
G8_CHECKPOINT_PROGRESS = 0.60        # Average checkpoint covers 60% of work
G8_SPIDER_SUBBATCH_PROGRESS = 0.75   # Average sub-batch completion at failure time


