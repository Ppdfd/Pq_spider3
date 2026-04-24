"""
Phase 1 (Ref [36]): Man et al. — System Setup via MLWE + 4DCCM
================================================================
Canonical re-implementation of the Key Generation phase of:
  Z. Man, Z. Yu, J. Yu, C. Gao, X. Meng,
  "Edge Computing in Internet of Things: Lattice-Based and Split
   Encryption for Post-Quantum Data Security,"
  IEEE Internet of Things Journal, Vol. 12, No. 23, Dec 2025.

This file now uses the shared primitives:
    crypto_primitives.mlwe_pke       — Eq. 12 key generation
    crypto_primitives.chaotic_4dccm  — Eq. 2 state initialization

Rather than duplicating the NTT and chaotic iteration logic here,
which is how this file was originally written.  All cost formulas
are still extracted from paper [36] Sec III-B.

Paper parameters (Sec III-B, Key Generation):
    q = 3329, n = 256, k = 2, psi = 17, omega = 1175

Paper operations (Step 2-3):
    1. Sample a ∈ Z_q[x]^{k×n}            uniform
    2. Sample s ∈ Z_q[x]^{k×n}            coefficients in [-1, 1]
    3. Sample e ∈ Z_q[x]^{k×n}            coefficients in [-1, 1]
    4. b_i = INTT(NTT(a_i) · NTT(s_i)) + e_i   mod q          (Eq. 12)
    5. Publish pk = (a, b), keep sk = s

Additionally: initialize a 4DCCM chaotic state (x0, y0, z0, w0).
The paper has NO attribute-based access control, NO user keys,
NO fog-node signing keys.
"""

import sys
import config
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives import mlwe_pke, chaotic_4dccm
from utils.dataset_loader import DataLoader


def run_phase1_ref36():
    print("=" * 60)
    print("PQ-SPIDER Phase 1 Simulation: System Setup (Ref [36] Man et al.)")
    print("=" * 60)

    metrics = {
        "aa_setup":        0,      # No CP-ABE in [36]
        "user_keygen":     0,      # No user-specific keys
        "fog_node_init":   [],
        "total_init":      0,
        "paper_note":      "No CP-ABE; MLWE keys + 4DCCM chaotic state only",
    }

    start_total = time.perf_counter()

    # ── Step 1: No Trusted Authority in [36] ──
    print("[1/3] Trusted Authority Setup (none — [36] has no CP-ABE)...")
    t0 = time.perf_counter()
    t_aa = (time.perf_counter() - t0) * 1000
    metrics["aa_setup"] = t_aa
    print(f"  -> TA Setup (no-op): {t_aa:.3f} ms")

    # ── Step 2: No user keygen in [36] ──
    print("\n[2/3] User Registration (no user key in [36])...")
    t0 = time.perf_counter()
    t_kg = (time.perf_counter() - t0) * 1000
    metrics["user_keygen"] = t_kg
    print(f"  -> User KeyGen (no-op): {t_kg:.3f} ms")

    # ── Step 3: Per-edge-node MLWE + 4DCCM init ──
    num_nodes = config.NUM_GLOBAL_NODES
    print(f"\n[3/3] Initializing {num_nodes} Edge Nodes (MLWE + 4DCCM)...")

    nodes = []
    for idx in range(num_nodes):
        t_fn0 = time.perf_counter()

        # Paper [36] Eq. 12:  MLWE key generation (shared primitive)
        pk_mlwe, sk_mlwe = mlwe_pke.keygen()

        # Paper [36] Sec II-B:  initialize 4DCCM chaotic state
        chaos_state = chaotic_4dccm.init_state()

        t_fn = (time.perf_counter() - t_fn0) * 1000
        nodes.append({
            "id":          idx,
            "chaos_state": chaos_state,
            "init_time":   t_fn,
        })
        metrics["fog_node_init"].append(t_fn)
        print(f"  -> Edge Node {idx} Ready ({t_fn:.2f} ms)")

    metrics["total_init"] = (time.perf_counter() - start_total) * 1000

    loader = DataLoader()
    phase_dir = Path(__file__).parent
    loader.save_metrics(phase_dir, metrics, filename="ref36_metrics.json")

    print("\n" + "=" * 60)
    print("Phase 1 (Ref [36]) Finished.")
    print(f"Total Latency:       {metrics['total_init']:.2f} ms")
    print(f"Average Node Init:   "
          f"{sum(metrics['fog_node_init']) / num_nodes:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase1_ref36()
