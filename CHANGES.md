# PQ-SPIDER Audit Fixes — CHANGES.md

This bundle fixes every Critical and High severity issue from the hostile audit, plus the most impactful Medium items. Drop these files into your existing `Pq_spider_new-miggaaa/` tree, overwriting the originals. New files are listed separately.

## How to apply

```bash
# From the root of your existing repo:
cp -r PQ_Spider_Fixed/* Pq_spider_new-miggaaa/
rm -f Pq_spider_new-miggaaa/utils/enclave_monitor.py
rm -f Pq_spider_new-miggaaa/utils/plot_graphs.py
rm -rf Pq_spider_new-miggaaa/PQ_Spider_Evaluation/

# Then install dependencies and smoke test:
pip install -r Pq_spider_new-miggaaa/requirements.txt
cd Pq_spider_new-miggaaa && python run_all_pipeline.py
```

---

## File-by-file changes

### Modified files

#### `phase1_initialization/ours.py`
- **[Critical]** `LatticeCPABE(n=32, q=3329)` → `LatticeCPABE(n=256, q=3329)`. Matches Ref [4]'s ring dimension of 256. The 8× mismatch was undisclosed and helped Ours on every CP-ABE-touching graph.
- **[Critical]** Added fog Dilithium keygen inside the Phase-1 timer. Keys are persisted in `ours_key.json`'s `pk_sig` / `sk_sig` fields. Previously, Dilithium keygen ran in Phase 5 outside the timer, so it was excluded from every accounting. Refs [4] and [35] both charge this to Phase 1 — now Ours does too.

#### `phase2_iiot_encrypt/ours.py`
- **[High]** Pre-decode all per-device secrets (`r_secret`, `cg_kem`, `kg_kem`) before `start_device = perf_counter()`. Removes ~1-2 µs/device hex-decode asymmetry vs Ref [4] (which already pre-decoded).

#### `phase2_iiot_encrypt/ref_36.py`
- **[Critical]** `ref36_packets.json` now persists the real ciphertext `ct_u` and `ct_v`, not just `u_len` / `v_len`. Downstream phases can finally operate on real data.
- **[Critical]** Persist matching secret key `ref36_sk.json` so Phase 6 can decrypt with the key that was used to encrypt.
- **[High]** 4DCCM chaos state is initialised and warmed up (800 iterations) **once** before the device loop. Previously, every device re-warmed 800 iterations inside the timer — inflating Ref [36]'s device latency ~800×. Only the per-packet perturbation (Eq. 13) remains inside the timer.

#### `phase3_edge_gateway/ours.py`
- **[High]** The negative-case sanity test (tampered packet → expect `auth_ok=False`) now runs **after** `metrics["total_gateway_latency"]` is computed. Previously it ran inside the timer, charging every Phase 3 number an extra Kyber decap + HMAC for no functional reason.

#### `phase5_fog_node/ours.py`
- **[Critical]** Removed the fake TEE parallelism. The old code computed `parallel_tee_latency = sum(sequential)/num_tees + 0.01*num_tees` and subtracted the difference from `total_fog_latency` — but `total_fog_latency` was immediately overwritten by wall-clock on the next line, so the subtraction was dead arithmetic and the TEE-count graph was plotting noise. New code measures the sequential enclave decryption honestly.
- **[Critical]** Dilithium keygen removed from Phase 5. The signing key is now loaded from Phase 1's `ours_key.json`. Matches Refs [4] and [35].
- **[Low]** Moved `ree_build_policy` inside the `ree_policy_expand` timer so sub-metrics sum to the CP-ABE total.

#### `phase5_fog_node/ref_36.py`
- **[High]** The passthrough hash now operates on the **real** serialised ciphertext from Phase 2, not on `os.urandom(u_len*8 + v_len*8)`. Removes entropy-syscall overhead from inside the timer.
- The serialisation of `ct_u` / `ct_v` into bytes happens **outside** the timer — only SHA-256 is timed.

#### `phase6_user_decrypt/ref_4.py`
- **[Medium]** All per-packet `bytes.fromhex` and `np.array(...)` constructions are now done **once** before `start_total`. The old code rebuilt `u`, `C_ep`, `C_r`, `C_attrs` arrays inside every timed block, charging ~5 decodes × N packets for serialisation work that is not decryption.

#### `phase6_user_decrypt/ref_35.py`
- **[Medium]** Pre-decode `c_kem`, `c_data`, `nonce` before `start_total`. Same rationale as `ref_4.py`.

#### `phase6_user_decrypt/ref_36.py`
- **[Critical]** The loop now decrypts each packet's **real** ciphertext (different `(ct_u, ct_v)` per packet), not a single `ct_sample` reused N times. Removes the cache-warm artefact from the old code.
- **[Critical]** Loads the matching secret key from `ref36_sk.json`. Old code generated a fresh mismatched keypair.

#### `graphs/plot_phase1_attr.py`
- **[High]** Added on-graph caption disclosing that Refs [35] and [36] are omitted (neither uses attribute-based access control).
- **[Medium]** Config mutations now wrapped in try/finally.

#### `graphs/plot_phase2_attr.py`
- **[Critical]** Removed the `"Ours (O(1))"` / `"Ref [4] (O(N))"` labels that embedded the conclusion into the legend. Labels are now just `"Ours"` and `"Ref [4]"`.
- **[High]** Added caption disclosing the architectural difference: Ours' Phase 2 does no per-attribute work at the device by construction.
- **[Medium]** Config mutations wrapped in try/finally.

#### `graphs/plot_remaining_phases.py`
- **[Critical]** `plot_phase5_tee` function **removed**. The TEE-count graph was plotting wall-clock noise; the x-axis variable `CURRENT_TEE_COUNT` was read by Phase 5 but only used in dead arithmetic.
- **[High]** Fixed `plot_phase5_fog` Ours chain — removed duplicated `ours_p1.run_phase1_simulation`. Ours was running Phase 1 once more than Refs in setup.
- **[High]** Fixed `plot_phase6_attr` — Ref [36]'s chain now includes `phase5` (was skipped), so its Phase 6 operates on real fog output like the other refs.
- **[Critical]** Removed `"(O(1) Batch)"` tag from Ours' label in `plot_phase6_attr` legend.
- **[High]** Added architectural-asymmetry captions on `plot_phase5_fog` (Ref [36] has no fog re-encryption) and `plot_phase6_attr` (Refs do per-packet, Ours does one-batch).
- **[High]** Added caption on `plot_phase5_attr` about n=256 match.
- **[Medium]** All config mutations wrapped in try/finally.
- `__main__` no longer calls `plot_phase5_tee`.

#### `run_all_tests.py`
- **[Medium]** `_avg` now returns `None` for empty lists (not `0.0`), so missing data is visually distinguishable from "ran very fast".
- **[Medium]** Grand summary now prints **two** totals:
  - `Core total (1+2+5+6)` — apples-to-apples across all schemes.
  - `Ours-full (1+2+3+4+5+6)` — includes PQ-SPIDER's gateway + scheduler phases; shown as `--` for refs since they have no analogue.
  - Previously, a single `End-to-end total` row silently charged Ours for Phases 3 and 4 while refs got 0.

### New files

#### `graphs/plot_phase4_scheduler.py` [NEW]
Missing from the original codebase. Plots Phase 4 Spider++ scheduler latency vs task count. Competitor schedulers [22]/[37]/[39] are pending paper upload — the file's `schemes` dict has clear instructions for how to add them.

#### `graphs/run_graph_suite.py` [NEW]
Missing from the original codebase. Single command to generate every Phase 1–6 graph with isolated try/except per plotter so one crash doesn't stop the others.

#### `run_all_pipeline.py` [NEW]
True one-command pipeline: runs all phases (via `run_all_tests.py`) **and** generates all graphs (via `graphs/run_graph_suite.py`) in a single invocation.

#### `requirements.txt` [NEW]
Pinned dependency list: `numpy`, `cryptography>=41.0`, `matplotlib>=3.7`, `bchlib>=1.0`. Documents that Kyber and Dilithium are pure-Python (not liboqs-backed) so absolute timings must not be compared to Ref [35]'s ARM-Cortex-A72 numbers.

### Files to delete

- `utils/enclave_monitor.py` — 0 bytes, dead
- `utils/plot_graphs.py` — 0 bytes, dead
- `PQ_Spider_Evaluation/` — nested folder, all files 0 bytes, abandoned restructure

---

## What this bundle does NOT fix

These are gaps, not bugs — they require source material or architectural decisions:

1. **Competitor schedulers [22], [37], [39] remain unimplemented.** The stubs in `phase4_load_balance/ref_*.py` still raise `NotImplementedError`. Upload the papers and re-implement per the IEEE methodology used for Refs [4]/[35]/[36].
2. **Real TEE parallelism not implemented.** The fake-parallelism code was removed rather than replaced. If you need a TEE parallelism graph, add `concurrent.futures.ProcessPoolExecutor` around the enclave decryption loop in `phase5/ours.py` and re-measure wall time — do not divide analytically.
3. **n=256 CP-ABE re-run is required** with `python run_all_pipeline.py` after applying this bundle — previous cached metrics used n=32 and will disagree with fresh runs. Delete `phase*/results/ours_metrics.json` before the first re-run to avoid confusion.
4. **Pure-Python Kyber/Dilithium absolute timings do not match Ref [35]'s paper values.** Either install `liboqs` (Kyber and Dilithium primitives would need to be rewritten to use it) or explicitly disclaim in the paper experimental section that all schemes were evaluated under the same pure-Python implementations to control for runtime variance.

---

## Sanity-check before publishing

After applying this bundle and running the pipeline, verify:

- `phase1/results/ours_metrics.json` — `aa_setup` should be noticeably larger than before (n=256 is 8× bigger ring).
- `phase5/results/ours_metrics.json` — `enclave_decrypt` should be a single number (not the old simulated parallel value) and should match the decryption loop wall time.
- `graphs/phase5_tee_latency.pdf` — **should no longer exist.** The file produced by previous runs should be deleted.
- `graphs/phase4_scheduler_latency.pdf` — **should now exist** (new graph).
- `graphs/phase5_fog_latency.pdf`, `phase6_attr_latency.pdf` — should include a figure caption at the bottom disclosing architectural asymmetry.
- Grand summary in terminal — should show two total rows (`Core total` and `Ours-full`), not one.

If any of these sanity checks fail, the bundle did not apply cleanly.
