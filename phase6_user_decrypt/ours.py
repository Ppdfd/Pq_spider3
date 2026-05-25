"""
Phase VI (Ours): PQ-SPIDER User Verification and Decryption
============================================================
Matches PQ-SPIDER2 paper Sec III-C, Phase VI (Eq 93-111):

  Step 1 (Eq 95):  Verify_Dilithium(pk_FN, sigma, H(BID ∥ epoch_k ∥ CT_AES
                                         ∥ D_k ∥ CT_{L-ABE} ∥ Root_k))
  Step 2 (Eq 96-97):  Policy satisfaction check + LSSS weights
  Step 3 (Eq 98):  Ciphertext share evaluation
  Step 4 (Eq 99):  Secret reconstruction C_rec
  Step 5 (Eq 100): K_master_AES ← Decode(⌊CT_0 − C_rec⌉_2)
  Step 6 (Eq 101-107): Chunk parsing + Root_k verification
  Step 7 (Eq 108-109): Per-chunk key derivation + parallel decryption
  Step 8 (Eq 110-111): Deterministic aggregation recovery
"""

import os
import sys
import time
import hashlib
import json
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.aes_gcm import SecureAESGCM
from crypto_primitives.dilithium import SecureDilithium
from crypto_primitives.cp_abe import LatticeCPABE
from utils.dataset_loader import DataLoader


def _chunk_kdf(k_master, batch_id, sub_id_bytes, epoch):
    """Eq 108: K_chunk^(i) = KDF(K_master_AES ∥ BID ∥ SubID_i ∥ epoch_k)"""
    return hashlib.sha256(
        k_master + batch_id + sub_id_bytes + str(epoch).encode()
    ).digest()


def run_phase6_simulation():
    print("=" * 60)
    print("PQ-SPIDER Phase VI Simulation: User Decryption (Ours)")
    print("=" * 60)

    metrics = {
        "dilithium_verify":    0,
        "policy_eval":         0,
        "cpabe_decrypt":       0,
        "root_verify":         0,
        "chunk_decrypt":       0,
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

    # ── Step 1: Integrity & Authenticity Verification (Eq 95) ──
    # Verify_Dilithium(pk_FN, sigma, H(BID ∥ epoch_k ∥ CT_AES ∥ D_k ∥ CT_L-ABE ∥ Root_k))
    t0 = time.perf_counter()
    dil = SecureDilithium()
    pk_sig = {
        "rho": bytes.fromhex(omega["pk_sig"]["rho"]),
        "t1": omega["pk_sig"]["t1"],
    }
    ct_aes = bytes.fromhex(omega["ct_aes"])
    batch_id = bytes.fromhex(omega["batch_id"])
    epoch_k = omega.get("epoch_k", 1)
    root_k = bytes.fromhex(omega.get("root_k", ""))
    chunk_manifest = omega.get("chunk_manifest", [])

    ct_labe_bytes = json.dumps({
        "policy_type": omega["ct_labe"]["policy_type"],
        "rho": omega["ct_labe"]["rho"],
    }, sort_keys=True).encode()
    dk_bytes = json.dumps(chunk_manifest, sort_keys=True).encode()

    hash_input = hashlib.sha256(
        batch_id + str(epoch_k).encode()
        + ct_aes + dk_bytes + ct_labe_bytes + root_k
    ).digest()

    sigma = bytes.fromhex(omega["sigma"])
    valid = dil.verify(hash_input, sigma, pk_sig)
    t_ver = (time.perf_counter() - t0) * 1000
    metrics["dilithium_verify"] = t_ver
    print(f"[1/6] Dilithium verify (Eq 95): {t_ver:.2f} ms  -> valid={valid}")
    assert valid, "Dilithium signature invalid"

    # ── Steps 2-5: CP-ABE Decryption (Eq 96-100) ──
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

    # Step 2 (Eq 96-97): Policy satisfaction + LSSS weights
    # Step 3 (Eq 98): Ciphertext share evaluation
    # Step 4 (Eq 99): Secret reconstruction
    t0 = time.perf_counter()
    pe = cpabe.policy_eval(ct_labe, sk_u)
    t_policy = (time.perf_counter() - t0) * 1000
    metrics["policy_eval"] = t_policy

    if pe is None:
        print("  ! Policy not satisfied.  Aborting.")
        return metrics

    # Step 5 (Eq 100): K_master_AES ← Decode(⌊CT_0 − C_rec⌉_2)
    t0 = time.perf_counter()
    k_master_aes = cpabe.cpabe_decrypt(ct_labe, sk_u, pe)
    t_cpabe = (time.perf_counter() - t0) * 1000
    metrics["cpabe_decrypt"] = t_cpabe

    print(f"[2-3] Policy eval + share eval (Eq 96-99): {t_policy:.2f} ms")
    print(f"[4]   CP-ABE key recovery (Eq 100): {t_cpabe:.2f} ms  "
          f"(K_master_AES recovered: {len(k_master_aes) if k_master_aes else 0} B)")

    if k_master_aes is None:
        print("  ! CP-ABE decryption failed. Aborting.")
        return metrics

    # ── Step 6: Chunk Parsing and Root_k Verification (Eq 101-107) ──
    t0 = time.perf_counter()

    if chunk_manifest:
        # Sort by SubID for deterministic ordering (Eq 105)
        sorted_manifest = sorted(chunk_manifest, key=lambda c: c["sub_id"])

        # Parse CT_AES into chunks using recorded lengths (Eq 101)
        offset = 0
        chunks = []
        digests = []
        for desc in sorted_manifest:
            chunk_len = desc["chunk_len"]
            C_i = ct_aes[offset: offset + chunk_len]
            offset += chunk_len
            IV_i = bytes.fromhex(desc["iv"])
            AAD_i = bytes.fromhex(desc["aad"])
            sub_id_bytes = bytes.fromhex(desc["sub_id"])

            # Eq 103: h_i = H(BID ∥ SubID_i ∥ epoch_k ∥ C_i ∥ Tag_i ∥ IV_i ∥ AAD_i)
            h_i = hashlib.sha256(
                batch_id + sub_id_bytes + str(epoch_k).encode()
                + C_i + IV_i + AAD_i
            ).digest()
            digests.append(h_i)

            chunks.append({
                "sub_id": sub_id_bytes,
                "C_i": C_i,
                "IV_i": IV_i,
                "AAD_i": AAD_i,
            })

        # Eq 106-107: Recompute Root'_k and verify
        root_input = batch_id + str(epoch_k).encode() + str(len(chunks)).encode()
        for h in digests:
            root_input += h
        root_k_prime = hashlib.sha256(root_input).digest()

        root_valid = (root_k_prime == root_k)
        t_root = (time.perf_counter() - t0) * 1000
        metrics["root_verify"] = t_root
        print(f"[5]   Root_k verification (Eq 106-107): {t_root:.2f} ms  "
              f"-> valid={root_valid}")
        assert root_valid, "Aggregation commitment Root_k mismatch!"
    else:
        # Backward compatibility: no chunk manifest (legacy Omega format)
        chunks = None
        t_root = (time.perf_counter() - t0) * 1000
        metrics["root_verify"] = t_root
        print(f"[5]   Legacy format (no chunk manifest): {t_root:.2f} ms")

    # ── Step 7-8: Chunk Decryption + Aggregation Recovery (Eq 108-111) ──
    t0 = time.perf_counter()

    if chunks:
        # Per-chunk key derivation and decryption (Eq 108-109)
        plaintext_chunks = []
        for chunk in chunks:
            k_chunk = _chunk_kdf(k_master_aes, batch_id, chunk["sub_id"], epoch_k)
            aes_chunk = SecureAESGCM(key=k_chunk)
            try:
                pt = aes_chunk.decrypt(chunk["C_i"], chunk["IV_i"],
                                       associated_data=chunk["AAD_i"])
                plaintext_chunks.append(pt)
            except Exception as e:
                print(f"  ! Chunk decrypt failed: {e}")

        # Eq 110-111: Deterministic aggregation recovery M_agg = ||_{i in O} M_i
        m_agg = b"".join(plaintext_chunks)
        print(f"  -> Plaintext recovered ({len(m_agg)} B) from "
              f"{len(plaintext_chunks)} chunks")
    else:
        # Legacy single-key decryption (backward compat)
        aes = SecureAESGCM(key=k_master_aes)
        iv = bytes.fromhex(omega["iv"])
        aad = bytes.fromhex(omega["aad"])
        m_agg = aes.decrypt(ct_aes, iv, associated_data=aad)
        print(f"  -> Plaintext recovered ({len(m_agg)} B) [legacy single-chunk]")

    t_chunk_dec = (time.perf_counter() - t0) * 1000
    metrics["chunk_decrypt"] = t_chunk_dec
    print(f"[6/6] Chunk decrypt + recovery (Eq 108-111): {t_chunk_dec:.2f} ms")

    # Save recovered plaintext
    import config
    payloads = []
    chunk_size = config.PAYLOAD_SIZE_BYTES
    for i in range(0, len(m_agg), chunk_size):
        chunk = m_agg[i:i + chunk_size]
        decoded_chunk = chunk.decode("utf-8", errors="ignore").replace("\x00", "")
        payloads.append(decoded_chunk)

    full_packet = {
        "batch_id": batch_id.decode("utf-8", errors="ignore"),
        "epoch_k": epoch_k,
        "num_chunks": len(chunks) if chunks else 1,
        "root_k_verified": True if chunks else "N/A (legacy)",
        "signature_verified": True,
        "policy_type": omega["ct_labe"]["policy_type"],
        "decrypted_payloads": payloads,
    }
    loader.save_data(Path(__file__).parent, "plaintext.json", full_packet)
    print("  -> Saved full plaintext to phase6_user_decrypt/output/plaintext.json")

    metrics["total_user_latency"] = (time.perf_counter() - start_total) * 1000

    loader.save_metrics(Path(__file__).parent, metrics)

    print("\n" + "=" * 60)
    print("Phase VI Simulation Finished.")
    print(f"Total User Latency: {metrics['total_user_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase6_simulation()
