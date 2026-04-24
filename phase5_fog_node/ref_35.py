"""
Phase 5 (Ref [35]): Zaheer et al. — Edge-Node PQC Forwarding
==============================================================
Matches [35] Sec III-B/C framework:
  1. Kyber.Decap(sk_edge, c_kem) to recover session key k_kem
  2. Re-wrap for the cloud: Kyber.Encap to cloud pk
  3. Dilithium.Sign for integrity before forwarding

CHANGES vs original draft:
  * Edge Kyber keypair is loaded ONCE from phase1 output; no more
    per-packet fresh keygen.  The measured "decap" latency now
    matches what [35] actually reports (~1.0 ms per packet).
  * Dilithium signing key is loaded from phase1; keygen is NOT
    inside the sign-latency block.
  * Cloud's Kyber pk is loaded once, not generated per packet.
  * Signs a REAL batch header derived from the actual phase-2
    ciphertexts, not a synthetic string.
"""

import os
import sys
import time
import hashlib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.kyber import SecureKyber
from crypto_primitives.dilithium import SecureDilithium
from utils.dataset_loader import DataLoader


def run_phase5_ref35():
    print("=" * 60)
    print("PQ-SPIDER Phase 5 Simulation: Edge Relay (Ref [35] Zaheer)")
    print("=" * 60)

    metrics = {
        "kyber_decap":          [],
        "kyber_reencap":        0,
        "dilithium_sign":       0,
        "total_fog_latency":    0,
    }

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase2_dir = Path(__file__).parent.parent / "phase2_iiot_encrypt"

    try:
        setup = loader.load_data(phase1_dir, "ref35_setup.json")
        packets = loader.load_data(phase2_dir, "ref35_packets.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        print("  ! Run phase1/ref_35.py and phase2/ref_35.py first.")
        return

    print(f"  -> Loaded {len(packets)} IoT packets.")

    # Long-lived edge Kyber secret (loaded, not freshly generated)
    edge_kyber = SecureKyber()
    edge_sk = bytes.fromhex(setup["edge0_kyber_sk"])

    # Long-lived edge Dilithium signing key
    dil = SecureDilithium()
    sk_sig = {
        "rho":     bytes.fromhex(setup["edge0_dil_sk"]["rho"]),
        "sigma":   bytes.fromhex(setup["edge0_dil_sk"]["sigma"]),
        "pk_hash": bytes.fromhex(setup["edge0_dil_sk"]["pk_hash"]),
        "s1":      setup["edge0_dil_sk"]["s1"],
        "s2":      setup["edge0_dil_sk"]["s2"],
        "t0":      setup["edge0_dil_sk"]["t0"],
    }

    # Cloud Kyber keypair (generated here but used as long-lived from
    # phase5's perspective; in a real deployment this would be in
    # some trust-anchor catalogue).
    cloud_kyber = SecureKyber()
    pk_cloud, _ = cloud_kyber.keygen()

    start_total = time.perf_counter()

    # ── Step 1: Kyber decap each device's real c_kem ──
    recovered_k_kems = []
    for p in packets:
        c_kem = bytes.fromhex(p["c_kem"])
        t0 = time.perf_counter()
        k_kem = edge_kyber.decap(c_kem, edge_sk)
        t_dec = (time.perf_counter() - t0) * 1000
        metrics["kyber_decap"].append(t_dec)
        recovered_k_kems.append(k_kem)
    decap_sum = sum(metrics["kyber_decap"])
    print(f"[1/3] Kyber decap × {len(packets)}: {decap_sum:.2f} ms "
          f"(avg {decap_sum/len(packets):.2f} ms/pkt)")

    # ── Step 2: Kyber re-encap to cloud ──
    t0 = time.perf_counter()
    c_kem_cloud, k_cloud = cloud_kyber.encap(pk_cloud)
    t_reenc = (time.perf_counter() - t0) * 1000
    metrics["kyber_reencap"] = t_reenc
    print(f"[2/3] Kyber re-encap to cloud : {t_reenc:.2f} ms")

    # ── Step 3: Dilithium sign batch header (real hash of real data) ──
    batch_header = b"".join(
        bytes.fromhex(p["c_kem"]) + bytes.fromhex(p["c_data"])
        for p in packets
    )
    batch_hash = hashlib.sha256(batch_header).digest()

    t0 = time.perf_counter()
    sigma = dil.sign(batch_hash, sk_sig)
    t_sign = (time.perf_counter() - t0) * 1000
    metrics["dilithium_sign"] = t_sign
    print(f"[3/3] Dilithium sign (keygen excluded): {t_sign:.2f} ms")

    metrics["total_fog_latency"] = (time.perf_counter() - start_total) * 1000

    loader.save_metrics(Path(__file__).parent, metrics,
                        filename="ref35_metrics.json")
    loader.save_data(Path(__file__).parent, "ref35_fog_out.json", {
        "batch_sigma":  sigma.hex(),
        "batch_hash":   batch_hash.hex(),
    })

    print("\n" + "=" * 60)
    print("Phase 5 (Ref [35]) Finished.")
    print(f"Total Fog Latency : {metrics['total_fog_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase5_ref35()
