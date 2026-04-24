"""
Phase 1 (Ref [35]): Zaheer et al. — PQC Key Generation (Kyber + Dilithium)
===========================================================================
Implements the System Setup phase of:
  A. N. Zaheer, M. Farhan, M. R. Naeem, M. M. Alnfiai,
  "Quantum-Resilient Cryptographic Frameworks: Design and Analysis of
   Post-Quantum Algorithms for Secure and Efficient Edge-Assisted IoT
   Ecosystems in Consumer Electronics Devices," IEEE TCE, Nov 2025.

Paper scheme (Sec III-C, Fig. 2):
  This is a PQC-based secure data storage & processing framework.
  There is NO attribute-based access control — the paper benchmarks
  standalone NIST PQC algorithms (Kyber, Dilithium, SPHINCS+).

  Setup in the paper consists of:
    1. Initialize post-quantum cryptographic engine
    2. Generate CRYSTALS-Kyber keypair (pk_KEM, sk_KEM)
    3. Generate CRYSTALS-Dilithium keypair (pk_sig, sk_sig)
    4. Establish secure channel between edge nodes via QKD (simulated)

  No attribute universe, no CP-ABE setup, no LSSS.
  Measured operations (Table II, III): Kyber KeyGen + Dilithium KeyGen.
"""

import os
import sys
import config
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.kyber import SecureKyber
from crypto_primitives.dilithium import SecureDilithium
from utils.dataset_loader import DataLoader


def run_phase1_ref35():
    print("=" * 60)
    print("PQ-SPIDER Phase 1 Simulation: System Setup (Ref [35] Zaheer et al.)")
    print("=" * 60)

    metrics = {
        "aa_setup": 0,           # No AA → 0
        "user_keygen": 0,        # No user CP-ABE key → 0
        "fog_node_init": [],
        "total_init": 0,
        "paper_note": "No CP-ABE; only Kyber + Dilithium per-node keygen"
    }

    start_total = time.perf_counter()

    # ── Step 1: No Attribute Authority setup in [35] ──
    print("[1/3] Trusted Authority Setup (none — [35] has no CP-ABE)...")
    t0 = time.perf_counter()
    # The paper has no master secret key or attribute universe.
    # It just initializes an empty PQC engine.
    t_aa = (time.perf_counter() - t0) * 1000
    metrics["aa_setup"] = t_aa
    print(f"  -> TA Setup (no-op): {t_aa:.3f} ms")

    # ── Step 2: No user CP-ABE keygen in [35] ──
    print("\n[2/3] User Registration (no CP-ABE keygen in [35])...")
    t0 = time.perf_counter()
    t_kg = (time.perf_counter() - t0) * 1000
    metrics["user_keygen"] = t_kg
    print(f"  -> User KeyGen (no-op): {t_kg:.3f} ms")

    # ── Step 3: Per-node Kyber + Dilithium KeyGen ──
    num_fog_nodes = config.NUM_GLOBAL_NODES
    print(f"\n[3/3] Initializing {num_fog_nodes} Edge Nodes (Kyber + Dilithium)...")

    fog_nodes = []
    # We also retain fog-0's key pairs so phase2/5/6 can share them.
    edge0_kyber_pk = None
    edge0_kyber_sk = None
    edge0_dil_pk   = None
    edge0_dil_sk   = None

    for i in range(num_fog_nodes):
        t_fn0 = time.perf_counter()

        # CRYSTALS-Kyber KeyGen (for KEM)
        kyber = SecureKyber()
        pk_kem, sk_kem = kyber.keygen()

        # CRYSTALS-Dilithium KeyGen (for signatures)
        dil = SecureDilithium()
        pk_sig, sk_sig = dil.keygen()

        t_fn = (time.perf_counter() - t_fn0) * 1000

        if i == 0:
            edge0_kyber_pk = pk_kem
            edge0_kyber_sk = sk_kem
            edge0_dil_pk   = pk_sig
            edge0_dil_sk   = sk_sig

        fog_nodes.append({
            "id": i,
            "pk_kem_len": len(pk_kem),
            "init_time": t_fn,
        })
        metrics["fog_node_init"].append(t_fn)
        print(f"  -> Edge Node {i} Ready ({t_fn:.2f} ms)")

    metrics["total_init"] = (time.perf_counter() - start_total) * 1000

    loader = DataLoader()
    phase_dir = Path(__file__).parent
    loader.save_metrics(phase_dir, metrics, filename="ref35_metrics.json")

    # Persist fog-0's long-lived Kyber + Dilithium key pairs so that
    # phase2 (device encap to the edge), phase5 (edge decap + sign),
    # and phase6 (user verify) can all use the same keys.  Without
    # this, phase5 was doing fresh keygen + encap + decap per packet
    # which is ~3x the real cost of just decap.
    loader.save_data(phase_dir, "ref35_setup.json", {
        "edge0_kyber_pk": edge0_kyber_pk.hex(),
        "edge0_kyber_sk": edge0_kyber_sk.hex(),
        "edge0_dil_pk": {
            "rho": edge0_dil_pk["rho"].hex(),
            "t1":  [list(p) for p in edge0_dil_pk["t1"]],
        },
        "edge0_dil_sk": {
            "rho":     edge0_dil_sk["rho"].hex(),
            "sigma":   edge0_dil_sk["sigma"].hex(),
            "pk_hash": edge0_dil_sk["pk_hash"].hex(),
            "s1":      [list(p) for p in edge0_dil_sk["s1"]],
            "s2":      [list(p) for p in edge0_dil_sk["s2"]],
            "t0":      [list(p) for p in edge0_dil_sk["t0"]],
        },
    })

    print("\n" + "=" * 60)
    print("Phase 1 (Ref [35]) Finished.")
    print(f"Total Latency:       {metrics['total_init']:.2f} ms")
    print(f"Average Node Init:   {sum(metrics['fog_node_init'])/num_fog_nodes:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase1_ref35()
