# Benchmark TA vs Paper Equations — Verification

## TA Measurement 1: `SERVICE_RATE` (μ_{j,k}) → Paper Eq 32, 42

### Paper says:
> **μ_{j,k}** = service rate of enclave E_{j,k} — tasks per second the TEE can process

### Code does:
```c
// TA (pqspider_bench_ta.c:107-121):
for (uint32_t i = 0; i < iterations; i++) {
    TEE_AEInit(op, iv, sizeof(iv), 128, 0, sizeof(in_buf));
    TEE_AEEncryptFinal(op, in_buf, sizeof(in_buf), out_buf, &out_len, tag, &tag_len);
    TEE_ResetOperation(op);
    TEE_SetOperationKey(op, key);
}

// Host (main.c:69-70):
service_rate = iters_done * 1000.0f / elapsed_ms;  // → 1265.82 tasks/sec
```

### ✅ Correct for:
- Runs **inside the TEE** (Secure World) — measures real OP-TEE crypto throughput
- Uses **AES-256-GCM** which matches Phase 5's actual encrypt operation
- Uses **256-byte** input buffer matching `config.PAYLOAD_SIZE_BYTES = 256`
- Returns **tasks/sec** which is exactly what μ_{j,k} represents

### ⚠️ Issue: Incomplete workload model
The paper's Phase 5 workload is: AES-GCM encrypt **+ Dilithium sign + CP-ABE re-encrypt**. The TA only measures AES-GCM. This means the service rate is **overestimated** (~1265/sec) vs what Phase 5 actually does.

**Impact**: For load balancing decisions, overestimating μ means the scheduler thinks enclaves can handle more work than they actually can. However, since ALL nodes use the same μ, relative rankings are unaffected — only absolute queue wait estimates shift.

**Recommendation**: Acceptable for now. The measured AES-GCM rate represents the **TEE crypto primitive throughput**, which is the right abstraction level for the scheduler. Full Phase 5 workload would need Dilithium + CP-ABE inside the TA, which is significantly more complex.

---

## TA Measurement 2: `NW_SW_LATENCY_MS` (L_j) → Paper Eq 36

### Paper says:
> **L_j** = network latency to fog node F_j — communication delay for batch routing

### Code does:
```c
// Host (main.c:80-90):
for (int i = 0; i < LATENCY_ROUNDS; i++) {
    clock_gettime(CLOCK_MONOTONIC, &t0);
    TEEC_InvokeCommand(&sess, CMD_NOP, &op, &err_origin);  // empty command
    clock_gettime(CLOCK_MONOTONIC, &t1);
    total_lat_ms += (t1 - t0) in ms;
}
avg_latency = total_lat_ms / LATENCY_ROUNDS;  // → 1.1565 ms
```

### ✅ Correct for:
- Measures **real NW→SW context switch** time on OP-TEE
- Uses `CMD_NOP` (empty command) to isolate the pure switching overhead
- Uses `CLOCK_MONOTONIC` (not wall clock) — correct for latency measurement
- Averages over 50 rounds to reduce noise

### ✅ Correctly maps to paper:
In OP-TEE, "network latency" to a fog node IS the NW→SW world switch. There's no actual network hop — the TEE is on the same chip. The context switch is the real communication cost.

---

## TA Measurement 3: `TRUST_SCORE` (U_j) → Paper Eq 35

### Paper says:
> **U_j** = trust score of fog node F_j — derived from TEE attestation success

### Code does:
```c
// Host (main.c:100-111):
int success = 0;
for (int i = 0; i < TRUST_ROUNDS; i++) {
    res = TEEC_OpenSession(&ctx, &test_sess, &uuid, ...);
    if (res == TEEC_SUCCESS) {
        success++;
        TEEC_CloseSession(&test_sess);
    }
}
trust_score = (float)success / (float)TRUST_ROUNDS;  // → 1.0 (20/20)
```

### ✅ Correct for:
- Tests **actual TA session establishment** — the real-world trust operation
- `TEEC_OpenSession` involves OP-TEE verifying the TA's signature/integrity
- Success rate directly maps to U_j ∈ [0, 1]

### ⚠️ Note:
On a healthy QEMU, this will always be 1.0. A real deployment with compromised TAs or resource exhaustion would show lower values. This is honest — on this hardware, trust IS 1.0.

---

## Phase 4 Code: How Measurements Flow Into Equations

### Eq 32: T_wait — Uses `service_rate` ✅
```python
# ours.py:64-70
total_q = sum(e["queue_length"] for e in enclaves)
avg_rate = max(1, sum(e["service_rate"] for e in enclaves) / len(enclaves))
return (total_q + 1) ** 2 / avg_rate
#       ↑ service_rate = 1265.82 from OP-TEE
```

### Eq 33: P_epc — Uses `PACKET_EPC_BYTES` and `EPC_BUDGET_BYTES` ✅
```python
# ours.py:73-81
# EPC_BUDGET_BYTES = 29.5 MB (OP-TEE TZDRAM)
# PACKET_EPC_BYTES = 34 KB (TA_DATA + TA_STACK)
```

### Eq 34: P_cap — Uses `capability_score` ⚠️
```python
# ours.py:84-87
C_j = fog_node.get("capability_score", 100)
# Currently derived from QEMU build config (config.QEMU_CAPABILITY_BASE)
# NOT from psutil — this is a formula, not a measurement
```

### Eq 35: P_trust — Uses `trust_score` ✅
```python
# ours.py:90-93
U_j = fog_node.get("trust_score", 0.9)
# Base = 1.0 from OP-TEE measurement
# Variation = config.TRUST_DEGRADATION[i] (hardcoded, NOT measured)
```

### Eq 36: SpiderScore — Uses `network_latency` ⚠️
```python
# ours.py:109
L_j = fog_node.get("network_latency", 1.0)
# Base = 1.1565 ms (measured), but + i*0.3 (synthetic ramp)
```

### ⚠️ BUG: `norm_rate` cap at 200 is wrong
```python
# ours.py:119
norm_rate = min(1.0, raw_rate / 200.0)  # cap at 200 = max expected
```
With the measured rate of **1265.82**, `raw_rate / 200 = 6.3`, which gets clamped to 1.0. This means ALL nodes have `norm_rate = 1.0` — the deadline bonus term `w7 · δ_k · norm_rate` cannot discriminate between nodes with different service rates.

**Fix**: Change to `norm_rate = min(1.0, raw_rate / 1500.0)` to let the measured rate scale properly.

---

## TA Memory Config vs config.py

| Setting | TA (`user_ta_header_defines.h`) | `config.py` | Match? |
|---------|--------------------------------|-------------|--------|
| Stack | `TA_STACK_SIZE = 8 KB` | Part of `PACKET_EPC_BYTES = 34 KB` | ❌ Mismatch |
| Heap | `TA_DATA_SIZE = 64 KB` | Part of `PACKET_EPC_BYTES = 34 KB` | ❌ Mismatch |
| Total per TA | **72 KB** | **34 KB** | ❌ |

The TA uses 8 KB stack + 64 KB heap = **72 KB** per session, but `config.py` assumes 2 KB + 32 KB = **34 KB**. The config should either:
- Match the TA: `PACKET_EPC_BYTES = 72 * 1024` (72 KB), OR
- The TA should use the default 2KB+32KB if that's what the paper assumes

> [!WARNING]
> This means the EPC pressure calculation (Eq 33) uses an underestimated memory footprint. Each TA session actually costs ~2x more TZDRAM than the scheduler thinks.

---

## Summary

| Measurement | Paper Eq | Code Correct? | Notes |
|-------------|----------|---------------|-------|
| `service_rate` (μ) | 32, 42 | ✅ Yes | AES-GCM inside TEE, 256B, matches paper |
| `NW_SW latency` (L_j) | 36 | ✅ Yes | Real NW→SW switch via CMD_NOP |
| `trust_score` (U_j) | 35 | ✅ Yes | Real session success rate |
| `norm_rate` cap | 36 | ❌ **Bug** | Capped at 200, actual is 1265 — fix the divisor |
| `PACKET_EPC_BYTES` | 33, 43 | ❌ **Mismatch** | Config says 34KB, TA uses 72KB |
| Workload completeness | — | ⚠️ Partial | Only AES-GCM, missing Dilithium+CP-ABE |
