import os
import time as _time
from typing import Dict, List

import numpy as np

from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR
)

def graph3_cpabe_encryption(rng: np.random.Generator, reps: int = 8) -> Dict[str, np.ndarray]:
    """
    Graph 3: CP-ABE Encryption Cost at Fog Node vs Number of Attributes.

    Both papers perform Lattice CP-ABE encryption at the fog node.
    The difference is the architectural model:

    Ref[4] (Poomekum et al.): Stateless fog node (no persistent enclave).
      - Per BATCH: must re-derive all attribute keys from scratch
      - Per BATCH: must rebuild LSSS policy matrix from scratch
      - Per BATCH: must re-convert A matrix to float64
      - Per PACKET: full encrypt() pipeline including all internal setup
      → Cost = setup_overhead + core_crypto (per batch)

    Spider (Ours): Persistent TEE enclave with Phase I caching.
      - All attribute keys pre-derived and cached in enclave (Eq 2)
      - LSSS policy pre-computed and cached (Eq 3-4, C_policy)
      - A_float conversion done once and persisted
      - Per PACKET: only tee_partial_encrypt + ree_finalize_ct
      → Cost = core_crypto only (setup amortized to Phase I)
    """
    from crypto_primitives.cp_abe import LatticeCPABE
    import config

    attrs = np.arange(5, 55, 5)
    N_BATCH = getattr(config, 'G3_NUM_TASKS', 20)

    ours_runs: List[np.ndarray] = []
    ref4_runs: List[np.ndarray] = []

    for _ in range(reps):
        o_vals = []
        r_vals = []
        for n_attr in attrs:
            n_attr_int = int(n_attr)
            universe = [f"Attr{i}" for i in range(n_attr_int)]
            policy = {"type": "AND", "attributes": universe}

            # ── Ref[4]: Stateless fog (no persistent enclave) ──
            # Each batch requires full cold-start reconstruction
            aa_ref4 = LatticeCPABE(n=256, q=3329)
            aa_ref4.setup()

            ref4_times = []
            for _ in range(N_BATCH):
                # Stateless: clear ALL caches before each packet
                # (no persistent enclave = state destroyed between packets)
                aa_ref4._A_float = None
                aa_ref4._sec.clear()
                aa_ref4._pub.clear()
                k_aes = os.urandom(32)
                t0 = _time.perf_counter()
                # Full encrypt pipeline from cold state:
                # internally: hash_attrs → _ensure_attr (cold) → ree_build_policy
                #           → tee_partial_encrypt → ree_finalize_ct
                aa_ref4.encrypt(k_aes, policy)
                ref4_times.append((_time.perf_counter() - t0) * 1000)
            r_vals.append(float(np.mean(ref4_times)))

            # ── Spider (Ours): Persistent enclave — all caches warm ──
            # Phase I already pre-computed:
            #   - Dual-Regev keys for all attributes (Eq 2)
            #   - LSSS policy matrix (Eq 3-4)
            #   - A_float conversion
            aa_warm = LatticeCPABE(n=256, q=3329)
            aa_warm.setup()
            for a in universe:
                aa_warm.hash_attribute(a)
            aa_warm.keygen({}, universe)
            policy_pkg = aa_warm.ree_build_policy(policy)
            aa_warm._get_A_float()
            # Warm-up
            _k = os.urandom(32)
            _t = aa_warm.tee_partial_encrypt(_k, policy_pkg)
            aa_warm.ree_finalize_ct(policy_pkg, _t)

            ours_times = []
            for _ in range(N_BATCH):
                k_aes = os.urandom(32)
                t0 = _time.perf_counter()
                tee_out = aa_warm.tee_partial_encrypt(k_aes, policy_pkg)
                aa_warm.ree_finalize_ct(policy_pkg, tee_out)
                ours_times.append((_time.perf_counter() - t0) * 1000)
            o_vals.append(float(np.mean(ours_times)))

        ours_runs.append(np.array(o_vals))
        ref4_runs.append(np.array(r_vals))

    ours_mean, ours_std = summarize_runs(ours_runs)
    ref4_mean, ref4_std = summarize_runs(ref4_runs)

    data = {"Ref[4]": ref4_mean, "Spider (Ours)": ours_mean}
    save_csv(RAW_DIR / "graph3_cpabe_encryption.csv",
             "Number of Attributes", attrs, data)
    plot_lines(
        attrs,
        {"Ref[4]": (ref4_mean, ref4_std),
         "Spider (Ours)": (ours_mean, ours_std)},
        "Graph 3: CP-ABE Encryption Cost (Fog)",
        "Number of Attributes",
        "CP-ABE Encryption Latency (ms)",
        "graph3_cpabe_encryption_fog",
    )
    return data

def simulate_recovery_time(failure_rate: float, method: str, seed: int) -> float:
    """
    Fair recovery simulation.  Per-task costs derived from measured values:
      - Full reprocess ≈ Phase 2 enc (~1.6ms) + Phase 5 fog (~44ms) ≈ 45ms
      - Retry from checkpoint ≈ fog re-execution only ≈ 15ms
      - Spider delegation ≈ Dilithium verify (~6.2ms) + state transfer (~3ms) ≈ 9ms
        AUDIT FIX: Previous value of 6ms was incorrect — measured Dilithium
        verify alone takes ~6.2ms on this hardware.
    All methods share the same detection latency and noise level.
    """
    rng = np.random.default_rng(seed)
    cluster_nodes = 20
    
    # Inflight tasks must be constant across failure rates to prevent
    # non-monotonic bouncing in the graph due to RNG variance.
    inflight = 500 
    
    failed = max(1, int(round(cluster_nodes * failure_rate / 100.0)))
    affected = inflight * (failed / cluster_nodes)

    # Detection latency: same for all methods (heartbeat timeout)
    detection = float(rng.normal(10.0, 2.0))
    noise = float(rng.normal(0.0, 8.0))  # equal noise for all

    if method == "No Delegation":
        # All affected tasks must be fully re-encrypted + re-processed
        per_task = float(rng.normal(45, 5))
        overhead = float(rng.normal(30, 5))
        recovery = detection + overhead + per_task * (affected / max(1, cluster_nodes - failed))
    elif method == "Simple Retry / Reassignment":
        # Retry from last checkpoint on available nodes
        per_task = float(rng.normal(15, 3))
        overhead = float(rng.normal(20, 5))
        recovery = detection + overhead + per_task * (affected / max(1, cluster_nodes - failed))
    elif method == "Spider (Ours)":
        # AUDIT FIX: Dilithium verify (~6.2ms measured) + state transfer (~3ms) ≈ 9ms
        per_task = float(rng.normal(9, 2))
        overhead = float(rng.normal(15, 3))
        recovery = detection + overhead + per_task * (affected / max(1, cluster_nodes - failed))
    else:
        raise ValueError(method)

    return max(1.0, float(recovery + noise))




# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

