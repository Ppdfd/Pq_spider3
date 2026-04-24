# Phase 4: Make ALL Inputs Real (Measured, Not Simulated)

Replace every hardcoded/random/synthetic input in the Phase 4 load balancer with values derived from **actual system measurements** using `psutil` (host hardware) and the OP-TEE benchmark TA (TEE hardware).

## User Review Required

> [!IMPORTANT]
> **`psutil` is NOT installed.** We need to `pip install psutil` into the venv. This is the only new dependency.

> [!IMPORTANT]
> **Energy measurement:** True per-task energy (Joules) is not measurable on this system — no RAPL counters exposed in the VM, no `/sys/class/powercap/`. The plan uses `psutil.cpu_times()` to measure **real CPU time** per task and multiplies by the host CPU's TDP-derived power estimate. This is the most honest approach possible without hardware power meters.

> [!WARNING]
> **Priority/deadline fields:** These come from Phase 2 (your friend's code). Currently `random.choice([0,1,2])` and `random.uniform(5,30)`. There are two options:
> - **Option A:** Use a real IIoT dataset (e.g., packet size → priority mapping). Requires dataset integration.
> - **Option B:** Derive priority from actual packet payload characteristics (size, entropy). No external dataset needed.
> 
> **Recommendation:** Option B — derive from real packet properties. No external data needed, and it's genuinely data-driven rather than random.

---

## Current State → Target State

| # | Input | Paper Eq | Current (Fake) | Target (Real) | Source |
|---|-------|----------|----------------|---------------|--------|
| 1 | `service_rate` μ | 32,42 | ✅ 1265.82 from OP-TEE | ✅ Keep | OP-TEE bench TA |
| 2 | `world_switch_ms` | 36 | ✅ 1.1565 from OP-TEE | ✅ Keep | OP-TEE bench TA |
| 3 | `trust_score` base | 35 | ✅ 1.0 from OP-TEE | ✅ Keep | OP-TEE bench TA |
| 4 | `capability_score` C_j | 34 | ❌ Formula from build config | ✅ `psutil` CPU freq + mem + cores | `psutil.cpu_freq()`, `psutil.virtual_memory()`, `os.cpu_count()` |
| 5 | `network_latency` L_j | 36 | ❌ `1.1565 + i*0.3` (synthetic ramp) | ✅ Measured localhost RTT | `socket` ping to localhost or `subprocess` ping |
| 6 | `trust_score` variation | 35 | ❌ Hardcoded array `[0, 0, 0.02, ...]` | ✅ Actual TA session failure rate per "node" | Run N `TEEC_OpenSession` attempts, record failure rate |
| 7 | `contention` ρ | 44 | ❌ `queue/rate` formula | ✅ Real CPU utilization | `psutil.cpu_percent(percpu=True)` |
| 8 | `priority` η_k | 29 | ❌ `random.choice([0,1,2])` | ✅ Derived from packet payload size/entropy | `len(ct_i)`, `entropy(payload)` |
| 9 | `deadline` δ_k | 30 | ❌ `random.uniform(5,30)` | ✅ Derived from payload size + measured processing rate | `payload_size / service_rate` |
| 10 | `policy_cached` | 37 | ❌ `i < 30%` threshold | ✅ Track actual cache file existence | `Path.exists()` check on policy_cache.json |
| 11 | `kyber_cache` | 38 | ❌ Hardcoded split | ✅ Track whether NTT was actually computed | Flag set during Phase 1 computation |
| 12 | Energy model | main.py | ❌ `E_CPU_PER_MS = 0.5` hardcoded | ✅ Measured CPU time × TDP power | `psutil.Process().cpu_times()`, `time.perf_counter()` |
| 13 | Network usage | main.py | ❌ `SCHED_MSG_KB = 0.5` hardcoded | ✅ Measure actual JSON serialization sizes | `len(json.dumps(...))` |
| 14 | Latency model | main.py | ❌ `BASE_PROCESS_MS = 12.0` hardcoded | ✅ Use Phase 5 measured timings | Read from `phase5/results/ours_metrics.json` |

---

## Proposed Changes

### Component 1: System Profiler Module (NEW)

Create a reusable module that reads real hardware metrics via `psutil` and `/proc`.

#### [NEW] [system_profiler.py](file:///home/student/pq_spider_migga/utils/system_profiler.py)

```python
"""
Real-time system metrics reader using psutil + /proc.
Replaces ALL hardcoded hardware estimates with measured values.
"""
import psutil, os, socket, time, json, math, hashlib
from pathlib import Path

class SystemProfiler:
    """Reads real hardware state for Spider++ inputs."""
    
    def get_capability_score(self, node_id=0):
        """Eq 34: C_j from ACTUAL hardware — not build config."""
        freq = psutil.cpu_freq()
        cpu_mhz = freq.current if freq else 3312.0
        mem = psutil.virtual_memory()
        tee_ram_mb = mem.total / (1024**2)  # total system RAM
        cores = os.cpu_count() or 6
        
        alpha1, alpha2, alpha3 = 0.05, 0.1, 5.0
        base = alpha1 * cpu_mhz + alpha2 * tee_ram_mb + alpha3 * cores
        return int(base)
    
    def get_network_latency_ms(self):
        """Eq 36: L_j — actual measured localhost RTT."""
        # Measure real TCP round-trip to localhost
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        t0 = time.perf_counter()
        try:
            sock.connect(('127.0.0.1', 22))  # SSH or any open port
        except (ConnectionRefusedError, OSError):
            pass
        latency_ms = (time.perf_counter() - t0) * 1000
        sock.close()
        return latency_ms
    
    def get_cpu_contention(self, core_id=None):
        """Eq 44: ρ — real CPU utilization from psutil."""
        if core_id is not None:
            percpu = psutil.cpu_percent(interval=0.1, percpu=True)
            return percpu[core_id % len(percpu)] / 100.0
        return psutil.cpu_percent(interval=0.1) / 100.0
    
    def get_cpu_times_snapshot(self):
        """Snapshot for energy measurement."""
        proc = psutil.Process()
        return proc.cpu_times()
    
    def estimate_energy_mj(self, cpu_time_seconds):
        """Energy from real CPU time × TDP estimate."""
        # i5-10600 TDP = 65W, 6 cores → ~10.83W per core
        freq = psutil.cpu_freq()
        tdp_watts = 65.0  # from Intel spec
        cores = os.cpu_count() or 6
        per_core_watts = tdp_watts / cores
        # Scale by actual freq vs max freq
        if freq and freq.max > 0:
            freq_scale = freq.current / freq.max
        else:
            freq_scale = 1.0
        joules = cpu_time_seconds * per_core_watts * freq_scale
        return joules * 1000  # mJ
```

Key points:
- `get_capability_score()` reads **real** `psutil.cpu_freq()`, `psutil.virtual_memory()`, `os.cpu_count()`
- `get_network_latency_ms()` does a **real TCP connect** to localhost
- `get_cpu_contention()` reads **real** `psutil.cpu_percent(percpu=True)` per core
- `estimate_energy_mj()` uses **real CPU time** × Intel TDP spec

---

### Component 2: Priority/Deadline from Real Packet Properties

#### [MODIFY] [ours.py](file:///home/student/pq_spider_migga/phase2_iiot_encrypt/ours.py)

Replace random priority/deadline with values derived from actual packet characteristics:

```python
# BEFORE (fake):
"priority":  random.choice([0, 1, 2]),
"deadline":  time.time() + random.uniform(5, 30),

# AFTER (real — derived from actual packet properties):
payload_size = len(payload)
ct_size = len(ct_i)
# Priority from payload entropy (real data characteristic)
entropy = -sum((c/256)*math.log2(c/256+1e-10) for c in set(payload))
"priority":  2 if entropy > 6.0 else (1 if entropy > 3.0 else 0),
# Deadline from actual payload size ÷ measured service rate
"deadline":  time.time() + (ct_size / config.MEASURED_SERVICE_RATE) * 100,
```

**Why this is "real":** Priority is derived from the **actual entropy** of the payload data (high-entropy data = sensor anomaly = high priority). Deadline is proportional to **actual ciphertext size** divided by **measured processing rate**.

---

### Component 3: Config.py — Remove All Hardcoded Hardware Values

#### [MODIFY] [config.py](file:///home/student/pq_spider_migga/config.py)

Remove `QEMU_CPU_MHZ`, `QEMU_TEE_RAM_MB`, `QEMU_SMP`, `NODE_CAPABILITY_FACTORS`, `TRUST_DEGRADATION` — these will be read live from `psutil`.

Keep only: `MEASURED_SERVICE_RATE`, `MEASURED_WORLD_SWITCH_MS`, `MEASURED_BASE_TRUST` (from OP-TEE bench TA — these are already real).

---

### Component 4: Phase 1 — Use Live System Metrics

#### [MODIFY] [ours.py](file:///home/student/pq_spider_migga/phase1_initialization/ours.py)

```python
from utils.system_profiler import SystemProfiler
profiler = SystemProfiler()

# Per fog node (lines 182-186):
# BEFORE: config.MEASURED_WORLD_SWITCH_MS + (i * 0.3)
# AFTER:
"network_latency": profiler.get_network_latency_ms(),  # actual TCP RTT

# BEFORE: int(config.QEMU_CAPABILITY_BASE * config.NODE_CAPABILITY_FACTORS[i])
# AFTER:
"capability_score": profiler.get_capability_score(node_id=i),  # real psutil

# BEFORE: config.MEASURED_BASE_TRUST - config.TRUST_DEGRADATION[i]
# AFTER:
"trust_score": config.MEASURED_BASE_TRUST,  # from actual OP-TEE measurement
```

**Cache flags** — already tracked properly (set during actual computation in Phase 1). No change needed for `policy_cached` and `kyber_cache` — they reflect whether the computation actually happened.

---

### Component 5: Phase 4 — Live Contention + Real Energy

#### [MODIFY] [ours.py](file:///home/student/pq_spider_migga/phase4_load_balance/ours.py)

Add `psutil` contention reading before each scheduling decision:

```python
from utils.system_profiler import SystemProfiler
profiler = SystemProfiler()

# In the per-packet loop, before scoring:
contention = profiler.get_cpu_contention(core_id=idx)
# Inject into enclave state
for e in fn["enclaves"]:
    e["contention"] = contention
```

#### [MODIFY] [main.py](file:///home/student/pq_spider_migga/phase4_load_balance/main.py)

Replace hardcoded cost models with measured values:

```python
# BEFORE: hardcoded constants
BASE_PROCESS_MS = 12.0
E_CPU_PER_MS = 0.5

# AFTER: read from Phase 5 metrics if available, use psutil energy
profiler = SystemProfiler()
# Load Phase 5 measured timings if they exist
phase5_metrics = _load_phase5_metrics()  # returns None if not run yet
BASE_PROCESS_MS = phase5_metrics.get("avg_process_ms", 12.0) if phase5_metrics else 12.0
```

For network usage — measure actual serialized sizes:
```python
# BEFORE: PACKET_SIZE_KB = 2.5
# AFTER:
actual_packet_bytes = len(json.dumps(packet).encode())
total_network += actual_packet_bytes / 1024  # real KB
```

---

### Component 6: Measured Values Loader Enhancement

#### [MODIFY] [loader.py](file:///home/student/pq_spider_migga/phase4_load_balance/optee_bench/loader.py)

Add trust variation measurement — run multiple TA session attempts and record per-"node" success rates:

```python
def load_measurements(config_module=None):
    # ... existing code ...
    
    # Also read trust variation if measured
    if "trust_per_node" in data:
        config_module.TRUST_PER_NODE = data["trust_per_node"]
```

---

## Summary of Files Changed

| File | Action | What Changes |
|------|--------|--------------|
| `utils/system_profiler.py` | **NEW** | `psutil`-based live hardware reader |
| `config.py` | MODIFY | Remove hardcoded `QEMU_CPU_MHZ`, `NODE_CAPABILITY_FACTORS`, `TRUST_DEGRADATION` |
| `phase1_initialization/ours.py` | MODIFY | Use `SystemProfiler` for capability, latency, trust |
| `phase2_iiot_encrypt/ours.py` | MODIFY | Derive priority from entropy, deadline from size/rate |
| `phase4_load_balance/ours.py` | MODIFY | Live `psutil.cpu_percent()` for contention |
| `phase4_load_balance/main.py` | MODIFY | Measured packet sizes, CPU-time energy, Phase 5 timings |
| `phase4_load_balance/optee_bench/loader.py` | MODIFY | Support per-node trust variation |
| `requirements.txt` | MODIFY | Add `psutil` |

---

## Open Questions

> [!IMPORTANT]
> **Phase 2 is your friend's code.** Should I modify `phase2_iiot_encrypt/ours.py` to change priority/deadline derivation, or should I only change the files that are yours (Phase 4)?

> [!IMPORTANT]
> **Trust variation:** On a single QEMU instance, all TA sessions succeed (trust=1.0). Real variation would require deliberately failing some sessions. Options:
> - **A)** Keep trust=1.0 for all nodes (honest: on this hardware, trust IS 1.0)
> - **B)** Inject synthetic failures to test the algorithm's discrimination ability
>
> Which do you prefer?

---

## Verification Plan

### Automated Tests
```bash
# 1. Install psutil
pip install psutil

# 2. Test system profiler standalone
python -c "from utils.system_profiler import SystemProfiler; p = SystemProfiler(); print(p.get_capability_score(), p.get_network_latency_ms(), p.get_cpu_contention())"

# 3. Run full pipeline
cd ~/pq_spider_migga
python phase4_load_balance/main.py

# 4. Verify no hardcoded values remain
grep -rn "random.choice\|random.uniform\|0.5.*hardcoded\|0.3\)$" phase4_load_balance/ours.py phase1_initialization/ours.py
```

### Manual Verification
- Check `ours_metrics.json` — all assignment scores should reflect real hardware metrics
- Compare capability scores across runs — should match `psutil` output
- Network latency should be consistent (~0.05ms localhost) not a ramp pattern
