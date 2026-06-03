# PQ-SPIDER2 Evaluation Graph Audit Report
## Verification of Correctness, Bias, and Hardcoded Values

> **Auditor:** Antigravity AI  
> **Date:** 2026-06-03  
> **Scope:** All 9 evaluation graphs (`graph1.py` – `graph9.py`), supporting modules (`inter_node.py`, `intra_node.py`, `generators.py`, `failure_detection.py`, `params.py`, `config.py`, `eval_utils.py`, `models.py`)  
> **Reference Paper:** PQ_SPIDER2.pdf (Sections III–VII)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Graph-by-Graph Correctness Verification](#2-graph-by-graph-correctness-verification)
3. [Bias Analysis](#3-bias-analysis)
4. [Hardcoded Values Inventory](#4-hardcoded-values-inventory)
5. [Structural Fairness Issues](#5-structural-fairness-issues)
6. [Recommendations](#6-recommendations)

---

## 1. Executive Summary

The evaluation framework implements **9 graphs** covering cryptographic cost analysis (Graphs 1–4), inter-node load balancing (Graphs 5–6), intra-node enclave scheduling (Graph 7), and fault-tolerance recovery (Graphs 8–9). After thorough analysis:

| Category | Verdict |
|---|---|
| **Equation mapping** | ✅ Mostly correct — all major equations (Eq 1-5, 24-50, 117-125) are implemented |
| **Structural bias** | ⚠️ **Several sources of systematic bias favoring Spider** |
| **Hardcoded values** | ⚠️ **Multiple hardcoded constants and magic numbers** |
| **Fairness of baselines** | ⚠️ **Baselines are modeled at different fidelity than Spider** |
| **Reproducibility** | ✅ Good — seeded RNG, CSV export, repeatable simulations |

> [!CAUTION]
> **Critical finding:** While no single issue constitutes fabrication, the **cumulative effect of multiple subtle biases** systematically favors Spider over baselines in load-balancing and fault-tolerance evaluations (Graphs 5–9). These biases appear to stem from design choices rather than intentional manipulation, but they weaken the scientific validity of the comparative evaluation.

---

## 2. Graph-by-Graph Correctness Verification

### Graph 1: CP-ABE Setup Latency ✅ CORRECT

| Paper Reference | Implementation | Status |
|---|---|---|
| Eq 1: `ID_j = H(attr_j)` | `aa.hash_attribute(a_name)` | ✅ |
| Eq 2: `(MPK, MSK) ← Setup(1^λ, {ID_j})` | `aa.setup()` + `aa.keygen({}, attr_names)` | ✅ |
| Eq 3-4: `(M, ρ) ← PolicyTreeGen(T_ID)` | `aa.ree_build_policy(policy)` | ✅ |
| Eq 5: `SK_u ← KeyGen(MSK, {ID_j})` | `aa.keygen({}, user_attrs)` | ✅ |
| Ref[4] implementation | Ring-LWE based, matches Algorithm 1 | ✅ |

**Verdict:** Both schemes are measured using real cryptographic operations (`LatticeCPABE`, `_sample_uniform_poly`, `gen_attribute_pair`). No hardcoded results. Fair comparison.

---

### Graph 2: Cache/Reuse-Aware Scheduling ✅ MOSTLY CORRECT

| Paper Reference | Implementation | Status |
|---|---|---|
| Cache hit/miss model | `simulate_cache_latency()` with LRU policy caching | ✅ |
| Spider reuse scoring (Eq 39) | `spider_score()` with `miss_penalty = 10.5` | ⚠️ Hardcoded |
| Measured CP-ABE costs | `_measure_cpabe_costs()` runs real crypto | ✅ |
| Cache factor measurement | `_measure_cache_factor()` measures real speedup | ✅ |

**Issues Found:**
- **`miss_penalty = 10.5`** (line 220, graph2.py): This is a hardcoded magic number with no derivation or paper reference. It directly controls how much Spider benefits from cache awareness vs the baselines.
- **Zipf distribution `s = 1.05`** (line 68, graph2.py): The Zipf exponent for policy locality is hardcoded. Different values would change relative performance significantly.

---

### Graph 3: CP-ABE Encryption Cost at Fog ✅ CORRECT

| Paper Reference | Implementation | Status |
|---|---|---|
| Ref[4] stateless model | Caches cleared before each packet | ✅ |
| Spider persistent enclave | Pre-warmed caches, split TEE/REE path | ✅ |
| Fair comparison | Both use same `LatticeCPABE` implementation | ✅ |

**Verdict:** This is a genuine performance comparison. The architectural difference (stateless vs persistent enclave) is the paper's actual contribution, and the code measures it correctly. No bias detected.

---

### Graph 4: CP-ABE Decryption Cost at User ✅ CORRECT

| Paper Reference | Implementation | Status |
|---|---|---|
| Ref[4] full per-packet decrypt | `policy_eval()` + `cpabe_decrypt()` per CT | ✅ |
| Spider batch-cached decrypt | First packet: full; rest: cached `policy_eval` | ✅ |
| Same ciphertexts for both | Both decrypt identical CT list | ✅ |

**Verdict:** Fair and correct. The amortization advantage is a real architectural benefit.

---

### Graph 5: Homogeneous Fog Load Balancing ⚠️ BIAS DETECTED

| Paper Reference | Implementation | Status |
|---|---|---|
| Eq 35: T_wait | Implemented in `choose_node()` | ✅ |
| Eq 36: P_epc | `epc_pressure_penalty()` | ✅ |
| Eq 37-38: P_cap, P_trust | Implemented | ✅ |
| Eq 39: R_reuse | **Hardcoded node_id < 3 fallback** | 🔴 BIAS |
| Eq 40: SpiderScore | Fully implemented | ✅ |
| Baselines Ref[22],[37],[39] | Simplified approximations | ⚠️ |

**Critical Issues:**
1. **Cache reuse fallback** (`inter_node.py`, lines 131-132): When `policy_cached` / `kyber_cached` attributes don't exist on the FogNode (which is the default), the code falls back to `node_id < 3`. This gives the first 3 nodes a structural advantage that only Spider exploits.
2. **Spider gets lower noise** (line 144): Spider adds `rng.normal(0.0, 0.5)` noise vs `rng.normal(0.0, 1.5)` for all baselines — **3× less scheduling noise**. This gives Spider an unfair precision advantage.
3. **Outlier trimming** (line 198-199): Trimming to [2nd, 98th] percentile can hide tail-latency differences.

---

### Graph 6: Heterogeneous Fog Load Balancing ⚠️ BIAS DETECTED

Same issues as Graph 5 — this file just calls `graph_load_balancing(heterogeneous=True)`. All bias from Graph 5 carries over, and is likely **amplified** in heterogeneous settings because Spider's multi-factor scoring has more opportunities to exploit its lower noise floor.

---

### Graph 7: Intra-Node Enclave Scheduling ⚠️ MINOR BIAS

| Paper Reference | Implementation | Status |
|---|---|---|
| Eq 42: T_wait (enclave) | `_enclave_score_eq46()` | ✅ |
| Eq 43: P_epc (enclave) | Quadratic threshold model | ✅ |
| Eq 44: P_cont (contention) | Enhanced with queue-imbalance penalty | ⚠️ Modified |
| Eq 45: A_affin (affinity) | Graduated affinity (0–1 fractional) | ⚠️ Modified |
| Eq 46: EnclaveScore | Full implementation | ✅ |
| Eq 49: Admission control | `ALPHA_EPC_SAFETY = 1.15` | ✅ |

**Issues Found:**
1. **Eq 44 modification**: The paper defines `P_cont = p_{j,k}` (simple contention). The code adds `queue_penalty_ms = enc.queue_length * service_est`, which is an **enhancement not in the paper**. While reasonable, it's an undisclosed improvement.
2. **Eq 45 modification**: The paper defines affinity as binary (`A = 1 if Sim ≥ τ_sim, else 0`). The code uses graduated fractional affinity. Again, an undisclosed improvement.
3. **EPC initial state bias** (`generators.py`, lines 193-198): Enclaves always get the pattern: 90%, 65%, 40% EPC availability. The modular assignment (`i % 3`) creates a deterministic pattern that Spider can exploit but Round-Robin cannot.

---

### Graph 8: Recovery Latency vs Fog Nodes ⚠️ BIAS DETECTED

| Paper Reference | Implementation | Status |
|---|---|---|
| Eq 117-119: Group partitioning | `partition_into_groups()` | ✅ |
| Eq 120: Heartbeat | `generate_heartbeat()` | ✅ |
| Eq 121-122: Timeout check | `check_heartbeat_timeout()` | ✅ |
| Eq 123: Quorum detection | `quorum_failure_detection()` | ✅ |
| Eq 124: Delegation capsule | `DelegationCapsule.create()` | ✅ |
| Eq 125: Recovery node selection | `select_recovery_node()` | ✅ |

**Critical Issues:**
1. **Asymmetric heartbeat jitter** (`graph8.py`, lines 152-153 vs 179-183):
   - Spider-FT heartbeat jitter: `abs(rng.normal(0.0, 1.5))` — mean ~1.2ms
   - Baselines heartbeat jitter: `abs(rng.normal(0.0, 3.5)) + CENTRALIZED_EXTRA_DELAY_MS (8.0)` — mean ~10.8ms
   - Additionally, baselines get a **5% chance of 30-60ms congestion spike** (line 182) that Spider never experiences
   - **This is the single largest source of bias in the entire evaluation.** The asymmetric jitter model virtually guarantees Spider detects failures faster and produces fewer false positives.

2. **Spider gets partial restart; baselines get full restart**:
   - Spider-FT `restart_fraction = max(0.05, 1.0 - capsule.progress)` where `progress ∈ [0.1, 0.85]` → restart ~15-90% (avg ~52%)
   - Centralized HB, Round-Robin, Least-Queue: `restart_fraction = 1.0` (always 100%)
   - Full Checkpoint: `restart_fraction ≈ max(0.1, 1.0 - 0.60 ± 0.1)` → ~30-50%
   - **This is architecturally valid** (delegation capsule is Spider's contribution), but the progress distribution `[0.1, 0.85]` is a hardcoded assumption.

3. **Extra detection delay for baselines** (line 197): Baselines add `+ extra_delay` (8ms) to detection time — this is architecturally motivated (centralized processing) but the 8ms value is hardcoded.

4. **Control message counting bias** (lines 311, 328, 343, 359): Spider counts 1 message per orphan task; centralized/round-robin count `len(states)` per heartbeat round; checkpoint counts `len(states) * 3`. These are reasonable but favor Spider's metric.

---

### Graph 9: Task Completion Ratio vs Failure Rate ⚠️ BIAS DETECTED

Inherits all bias from Graph 8 since it calls `_run_scenario()` from graph8.py. The bias in heartbeat jitter directly translates to higher task completion ratios for Spider-FT.

---

## 3. Bias Analysis

### 3.1 Systematic Biases Favoring Spider

| # | Bias Source | Location | Impact | Severity |
|---|---|---|---|---|
| B1 | **Scheduling noise asymmetry** | `inter_node.py:144` vs `:67,82,86,101` | Spider gets 3× lower noise (σ=0.5 vs σ=1.5) | 🔴 HIGH |
| B2 | **Heartbeat jitter asymmetry** | `graph8.py:152` vs `:179-183` | Spider heartbeats ~9× more precise | 🔴 HIGH |
| B3 | **Congestion spike only for baselines** | `graph8.py:181-182` | 5% chance of 30-60ms delay only for baselines | 🔴 HIGH |
| B4 | **Cache fallback `node_id < 3`** | `inter_node.py:131-132` | First 3 nodes always have cache for Spider | 🟡 MEDIUM |
| B5 | **Deterministic EPC pattern** | `generators.py:193-198` | `i%3` pattern exploitable by Spider but not RR | 🟡 MEDIUM |
| B6 | **Eq 44-45 undisclosed enhancements** | `intra_node.py:81-90` | Paper equations enhanced without disclosure | 🟡 MEDIUM |
| B7 | **Baseline model fidelity gap** | `inter_node.py:64-101` | Baselines are simplified approximations | 🟡 MEDIUM |

### 3.2 Biases That Are Architecturally Valid

These are **not unfair** — they represent genuine architectural advantages:

| Feature | Why it's valid |
|---|---|
| Spider partial restart via delegation capsule | This IS the paper's contribution (Eq 124) |
| Spider persistent enclave caching (Graph 3) | This IS the split-phase design (Section III Phase V) |
| Spider batch-cached decryption (Graph 4) | This IS the batch-aware model |
| Spider multi-factor scoring | This IS the SpiderScore equation (Eq 40) |

---

## 4. Hardcoded Values Inventory

### 4.1 Magic Numbers Without Derivation

| Value | Location | Description | Concern |
|---|---|---|---|
| `miss_penalty = 10.5` | `graph2.py:220` | Cache miss penalty in Spider scoring | No derivation provided |
| `s = 1.05` | `graph2.py:68` | Zipf exponent for policy locality | Arbitrary choice |
| `0.65, 0.38, 2.2` | `models.py:34` | crypto_intensity coefficients | No derivation |
| `11.0, 7.0, 0.010` | `models.py:54` | capability score coefficients | Not from paper Eq 27 |
| `1.5` | `models.py:57` | queue_delay multiplier | No derivation |
| `8.0, 0.52, 0.30, 1.7, 0.020` | `generators.py:64` | tee_work coefficients | No derivation |
| `5.0, 0.22, 0.24, 1.15, 0.010` | `generators.py:65` | ree_work coefficients | No derivation |
| `16.0, 0.65, 0.42, 3.4` | `generators.py:69` | epc_req coefficients | No derivation |
| `7.2` | `generators.py:51` | Mean inter-arrival time | No derivation |
| `150, 400` | `generators.py:62` | Deadline range (ms) | Loosely cited as IEC 61784-2 |
| `0.70` | `config.py:147` | Offered load for intra-node | Cited but chosen for advantage |
| `56.35` | `generators.py:38` | Fallback fog latency (ms) | OK if measured data exists |
| `10.5` | `graph2.py:220` | Spider cache miss penalty | No derivation |

### 4.2 Hardcoded Simulation Parameters (With Citations)

These are acceptable as they cite literature sources:

| Value | Location | Citation |
|---|---|---|
| `epc_swap_base_ms = 12.0` | `params.py:41` | [B] Arnautov OSDI'16, [C] Weisse ISCA'17 |
| `contention_per_unit_ms = 1.13` | `params.py:50` | [A] OP-TEE QEMU measurement |
| `rate_multiplier_range = (0.5, 1.3)` | `params.py:58` | [D] Amacher DAIS'19 |
| `tee_startup_ms = 2.6` | `params.py:69` | [A] + [D] |
| `ree_startup_ms = 1.8` | `params.py:74` | Linux CFS scheduling |
| `finalization_ms = 3.6` | `params.py:79` | [A] + network ACK |

---

## 5. Structural Fairness Issues

### 5.1 Algorithm Seed Offsets Create Different Random Streams

```python
# inter_node.py:186
alg_offset = {"Ref[22]": 11, "Ref[37]": 23, "Ref[39]": 37, "Spider (Ours)": 53}

# intra_node.py:261
alg_offset = {"Round-Robin": 7, "Least-Queue": 19, "Spider (Ours)": 41}
```

While the **task stream** is generated from a shared base seed (fair), each algorithm's **execution randomness** (noise, jitter) uses different RNG offsets. This is correct design (prevents correlated noise), but the offsets are hardcoded constants.

### 5.2 Percentile Trimming Hides Tail Behavior

```python
# inter_node.py:198-199
lo, hi = np.percentile(arr, [2, 98])
return float(arr[(arr >= lo) & (arr <= hi)].mean())
```

Both `simulate_load_balancing()` and `simulate_intra_node()` trim the 2nd and 98th percentiles before averaging. This removes tail latencies that are often the most informative for evaluating scheduler quality. In IIoT systems, tail latency is critical (deadline-miss rate).

### 5.3 Baseline Implementations Are Not Verified Against Original Papers

The implementations of Ref[22], Ref[37], and Ref[39] are simplified approximations of the original algorithms:

- **Ref[22]** is reduced to a simple min-latency selection
- **Ref[37]** uses a simplified binary offloading decision
- **Ref[39]** uses a reward heuristic instead of actual Q-learning

While simplification is sometimes necessary, it means baselines may perform **worse** than they would in faithful implementations, biasing results toward Spider.

### 5.4 Eq 50-51 (Score Smoothing) Intentionally Omitted

The paper defines exponential score smoothing (Eq 50) and threshold-based update suppression (Eq 51). These are omitted from the simulation with the justification that "the discrete-event model processes tasks sequentially." However, this omission could also mask scheduling instability that would occur in real deployments.

---

## 6. Recommendations

### 6.1 Critical Fixes (Required for Scientific Validity)

> [!IMPORTANT]
> These issues should be addressed before paper submission.

1. **Equalize scheduling noise** (`inter_node.py`): All algorithms should use the same noise magnitude. Change Spider's `rng.normal(0.0, 0.5)` to `rng.normal(0.0, 1.5)` or vice versa.

2. **Equalize heartbeat jitter model** (`graph8.py`): Use the same base jitter distribution for Spider-FT and centralized baselines. The architectural difference (group-based vs centralized) should emerge from the **quorum logic**, not from an asymmetric noise model.

3. **Remove congestion spike bias** (`graph8.py:181-182`): Either apply the same congestion model to all strategies or remove it entirely. A 5% chance of 30-60ms delay only for baselines is not justified.

4. **Fix cache reuse fallback** (`inter_node.py:131-132`): Replace the `node_id < 3` fallback with a proper cache simulation model, or set `has_policy = has_kyber = False` when attributes are missing.

### 6.2 Recommended Improvements

5. **Document all magic numbers**: Every coefficient in `generators.py` (task work models) and `models.py` (capability/crypto intensity) should have a derivation or measurement reference.

6. **Report tail latency**: Add p99 latency as an evaluation metric alongside mean latency. The percentile trimming masks important scheduler behavior.

7. **Verify baseline implementations**: Compare Ref[22], [37], [39] implementations against the original papers' algorithms and document any simplifications.

8. **Disclose equation modifications**: The enhancements to Eq 44 (queue-imbalance penalty) and Eq 45 (graduated affinity) should be explicitly described in the paper.

### 6.3 Minor Issues

9. **`summarize_runs` uses median** (`eval_utils.py:190`): Docstring says "Use median to be robust" but this deviates from the standard scientific convention of reporting mean ± std. Should be consistent.

10. **CHANGELOG reference**: The file `graph6.py` contains an "AUDIT FIX NOTE" mentioning previous hardcoded numpy arrays — this suggests earlier versions had even more severe bias issues. The audit trail should be preserved.

---

## Appendix: File-by-File Reference

| File | Lines | Role | Issues Found |
|---|---|---|---|
| `graph1.py` | 101 | CP-ABE setup latency | None |
| `graph2.py` | 295 | Cache/reuse scheduling | Hardcoded `miss_penalty`, `s=1.05` |
| `graph3.py` | 115 | CP-ABE encryption fog | None |
| `graph4.py` | 107 | CP-ABE decryption user | None |
| `graph5.py` | 68 | Homogeneous load balancing | Inherits `inter_node.py` bias |
| `graph6.py` | 27 | Heterogeneous load balancing | Same as Graph 5 |
| `graph7.py` | 218 | Intra-node enclave scheduling | Deterministic EPC pattern |
| `graph8.py` | 503 | Recovery latency | Heartbeat jitter asymmetry, congestion spike bias |
| `graph9.py` | 64 | Task completion ratio | Inherits Graph 8 bias |
| `inter_node.py` | 200 | Level 1 scheduler | **3× noise asymmetry**, cache fallback |
| `intra_node.py` | 282 | Level 2 scheduler | Eq 44-45 undisclosed modifications |
| `generators.py` | 227 | Task/node generation | Many undocumented coefficients |
| `failure_detection.py` | 339 | Failure detection (Eq 117-125) | Correctly implements equations |
| `params.py` | 81 | Simulation parameters | Well-cited, acceptable |
| `config.py` | 209 | Global configuration | Spider weights tuned but documented |
| `models.py` | 96 | Data models | Hardcoded capability coefficients |
| `eval_utils.py` | 289 | Plotting/CSV utilities | Minor: median vs mean |
