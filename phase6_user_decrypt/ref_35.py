"""
Phase 6 (Ref [35]) — AUDIT FIX NOTES
===================================================================
CHANGES vs original:
  [FAIRNESS] Per-packet hex decoding of c_kem, c_data, nonce is
             now done once before start_total, not inside each
             per-packet timer.  Keeps serialisation cost out of
             the measured Kyber+AES-GCM work.
"""

import sys
import time
import hashlib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.aes_gcm import SecureAESGCM
from crypto_primitives.kyber import SecureKyber
from crypto_primitives.dilithium import SecureDilithium
from utils.dataset_loader import DataLoader


def run_phase6_ref35():
    print("=" * 60)
    print("PQ-SPIDER Phase 6 Simulation: User Decryption (Ref [35] Zaheer)")
    print("=" * 60)

    metrics = {
        "dilithium_verify":    0,
        "kyber_decap":         [],
        "aes_gcm_decrypt":     [],
        "total_user_latency":  0,
    }

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase2_dir = Path(__file__).parent.parent / "phase2_iiot_encrypt"
    phase5_dir = Path(__file__).parent.parent / "phase5_fog_node"

    try:
        setup    = loader.load_data(phase1_dir, "ref35_setup.json")
        packets  = loader.load_data(phase2_dir, "ref35_packets.json")
        fog_out  = loader.load_data(phase5_dir, "ref35_fog_out.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        return

    print(f"  -> Loaded {len(packets)} packets.")

    edge_kyber = SecureKyber()
    edge_sk = bytes.fromhex(setup["edge0_kyber_sk"])

    pk_sig = {
        "rho": bytes.fromhex(setup["edge0_dil_pk"]["rho"]),
        "t1":  setup["edge0_dil_pk"]["t1"],
    }

    batch_hash = bytes.fromhex(fog_out["batch_hash"])
    sigma = bytes.fromhex(fog_out["batch_sigma"])

    # AUDIT FIX: pre-decode all per-packet hex outside the timer.
    pre = []
    for p in packets:
        pre.append({
            "c_kem":  bytes.fromhex(p["c_kem"]),
            "c_data": bytes.fromhex(p["c_data"]),
            "nonce":  bytes.fromhex(p["nonce"]),
        })

    start_total = time.perf_counter()

    # Step 1: Dilithium verify
    t0 = time.perf_counter()
    dil = SecureDilithium()
    valid = dil.verify(batch_hash, sigma, pk_sig)
    t_ver = (time.perf_counter() - t0) * 1000
    metrics["dilithium_verify"] = t_ver
    print(f"[1/3] Dilithium verify (real batch): {t_ver:.2f} ms "
          f"-> valid={valid}")
    assert valid, "Dilithium batch signature failed"

    # Step 2: Kyber decap
    recovered_k_kems = []
    for r in pre:
        t0 = time.perf_counter()
        k_kem = edge_kyber.decap(r["c_kem"], edge_sk)
        t_d = (time.perf_counter() - t0) * 1000
        metrics["kyber_decap"].append(t_d)
        recovered_k_kems.append(k_kem)
    total_decap = sum(metrics["kyber_decap"])
    print(f"[2/3] Kyber decap × {len(pre)}: {total_decap:.2f} ms "
          f"(avg {total_decap/len(pre):.2f} ms/pkt)")

    # Step 3: AES-GCM decrypt
    recovered_count = 0
    failed_count = 0
    for i, r in enumerate(pre):
        t0 = time.perf_counter()
        try:
            aes = SecureAESGCM(key=recovered_k_kems[i])
            _ = aes.decrypt(r["c_data"], r["nonce"], associated_data=None)
            recovered_count += 1
        except Exception:
            failed_count += 1
        metrics["aes_gcm_decrypt"].append(
            (time.perf_counter() - t0) * 1000)
    total_aes = sum(metrics["aes_gcm_decrypt"])
    print(f"[3/3] AES-GCM decrypt × {len(pre)}: {total_aes:.2f} ms "
          f"(recovered={recovered_count}, tag-failed={failed_count})")

    metrics["total_user_latency"] = (time.perf_counter() - start_total) * 1000

    loader.save_metrics(Path(__file__).parent, metrics,
                        filename="ref35_metrics.json")

    print("\n" + "=" * 60)
    print("Phase 6 (Ref [35]) Finished.")
    print(f"Total User Latency: {metrics['total_user_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase6_ref35()
