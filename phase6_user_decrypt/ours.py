"""
Phase VI (Ours): PQ-SPIDER User Verification and Decryption
============================================================
Matches PQ-SPIDER paper Sec III-C, Phase VI (Eq 74-79):

  Step 1 (Eq 74): Verify_Dilithium(pk_FN, σ, H(BID ∥ CT_AES ∥ CT_{L-ABE}))
  Step 2 (Eq 75): Σ_{i∈I} ω_i M_i = (1, 0, ..., 0) — LSSS weights
  Step 3 (Eq 76): C'_i ← Eval(CT_i, SK_u) ≈ M_i · V_base + e_eval
  Step 4 (Eq 77): C_rec = Σ ω_i C'_i ≈ A^⊤ s + e_total
  Step 5 (Eq 78): K_AES ← Decode(⌊CT_0 − C_rec⌉_2)
  Step 6 (Eq 79): M_agg ← AES-GCM.Dec(K_AES, IV, CT_AES, Tag_AES)
"""

import os
import sys
import time
import hashlib
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.aes_gcm import SecureAESGCM
from crypto_primitives.dilithium import SecureDilithium
from crypto_primitives.cp_abe import LatticeCPABE
from utils.dataset_loader import DataLoader


def run_phase6_simulation():
    print("=" * 60)
    print("PQ-SPIDER Phase VI Simulation: User Decryption (Ours)")
    print("=" * 60)

    metrics = {
        "dilithium_verify":    0,
        "policy_eval":         0,
        "cpabe_decrypt":       0,
        "aes_gcm_decrypt":     0,
        "total_user_latency":  0,
    }

    loader = DataLoader()
    phase5_dir = Path(__file__).parent.parent / "phase5_fog_node"

    try:
        omega = loader.load_data(phase5_dir, "ours_omega.json")
        sku_blob = loader.load_data(phase5_dir, "ours_sku.json")
    except FileNotFoundError:
        print("  ! Run phase 5 first.")
        return

    start_total = time.perf_counter()

    # ── Step 1: Integrity & Authenticity Verification ──
    # Eq 74: Verify_Dilithium(pk_FN, σ, H(BID ∥ CT_AES ∥ CT_{L-ABE}))
    t0 = time.perf_counter()
    dil = SecureDilithium()
    pk_sig = {
        "rho": bytes.fromhex(omega["pk_sig"]["rho"]),
        "t1": omega["pk_sig"]["t1"],
    }
    ct_aes = bytes.fromhex(omega["ct_aes"])
    batch_id = bytes.fromhex(omega["batch_id"])
    import json
    ct_labe_bytes = json.dumps({
        "policy_type": omega["ct_labe"]["policy_type"],
        "rho": omega["ct_labe"]["rho"],
    }, sort_keys=True).encode()
    hash_input = hashlib.sha256(batch_id + ct_aes + ct_labe_bytes).digest()
    sigma = bytes.fromhex(omega["sigma"])
    valid = dil.verify(hash_input, sigma, pk_sig)
    t_ver = (time.perf_counter() - t0) * 1000
    metrics["dilithium_verify"] = t_ver
    print(f"[1/4] Dilithium verify (Eq 74): {t_ver:.2f} ms  -> valid={valid}")
    assert valid, "Dilithium signature invalid"

    # ── Steps 2-5: CP-ABE Decryption ──
    cpabe = LatticeCPABE(n=sku_blob["n"], q=sku_blob["q"])
    cpabe.A = np.array(sku_blob["A"], dtype=np.int64)
    cpabe._pub = {a: np.array(v, dtype=np.int64)
                  for a, v in sku_blob["pub_vectors"].items()}
    cpabe._sec = {a: np.array(v, dtype=np.int64)
                  for a, v in sku_blob["sk_u"].items()}
    sk_u = {a: np.array(v, dtype=np.int64)
            for a, v in sku_blob["sk_u"].items()}

    ct_labe = {
        "policy_type": omega["ct_labe"]["policy_type"],
        "rho":         omega["ct_labe"]["rho"],
        "M":           omega["ct_labe"]["M"],
        "ct_rows":     omega["ct_labe"]["ct_rows"],
        "ct0":         omega["ct_labe"].get("ct0", []),
        "ct_attr":     omega["ct_labe"].get("ct_attr", []),
    }

    # Step 2 (Eq 75): Policy satisfaction — find weights ω_i
    # Step 3 (Eq 76): Ciphertext share evaluation
    # Step 4 (Eq 77): Secret reconstruction C_rec = Σ ω_i C'_i
    t0 = time.perf_counter()
    pe = cpabe.policy_eval(ct_labe, sk_u)
    t_policy = (time.perf_counter() - t0) * 1000
    metrics["policy_eval"] = t_policy

    if pe is None:
        print("  ! Policy not satisfied.  Aborting.")
        return metrics

    # Step 5 (Eq 78): K_AES ← Decode(⌊CT_0 − C_rec⌉_2)
    t0 = time.perf_counter()
    k_aes = cpabe.cpabe_decrypt(ct_labe, sk_u, pe)
    t_cpabe = (time.perf_counter() - t0) * 1000
    metrics["cpabe_decrypt"] = t_cpabe

    print(f"[2-4] Policy eval + share eval (Eq 75-77): {t_policy:.2f} ms")
    print(f"[5]   CP-ABE key recovery (Eq 78): {t_cpabe:.2f} ms  "
          f"(K_AES recovered: {len(k_aes) if k_aes else 0} B)")

    # ── Step 6: Final Decryption ──
    # Eq 79: M_agg ← AES-GCM.Dec(K_AES, IV, CT_AES, Tag_AES)
    t0 = time.perf_counter()
    if k_aes is None:
        print("  ! Policy not satisfied. Aborting.")
        return metrics
    aes = SecureAESGCM(key=k_aes)
    iv = bytes.fromhex(omega["iv"])
    aad = bytes.fromhex(omega["aad"])
    try:
        m_agg = aes.decrypt(ct_aes, iv, associated_data=aad)
        print(f"  -> Plaintext recovered ({len(m_agg)} B)")
    except Exception as e:
        print(f"  ! AES-GCM decrypt failed: {e}")
    t_aes = (time.perf_counter() - t0) * 1000
    metrics["aes_gcm_decrypt"] = t_aes
    print(f"[6/6] AES-GCM decrypt (Eq 79): {t_aes:.2f} ms")

    metrics["total_user_latency"] = (time.perf_counter() - start_total) * 1000

    loader.save_metrics(Path(__file__).parent, metrics)

    print("\n" + "=" * 60)
    print("Phase VI Simulation Finished.")
    print(f"Total User Latency: {metrics['total_user_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase6_simulation()
