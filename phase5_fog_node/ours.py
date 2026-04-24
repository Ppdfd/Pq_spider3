"""
Phase V (Ours): Multi-Enclave TEE-Assisted Split-Phase CP-ABE Processing
========================================================================
Matches PQ-SPIDER paper Sec III-C, Phase V (Eq 54-73):

  Step 1 (Eq 54):  GTag' ← H(Sort({Auth_i}) ∥ t_G)   — Batch verify
  Step 2 (Eq 55):  B_k → {B_k^(1),...,B_k^(r)}        — Batch decomposition
  Step 3 (Eq 56-60): Enclave-parallel decrypt + aggregate
  Step 4 (Eq 61-62): K_AES ← {0,1}^256; AES-GCM encrypt
  Step 5 (Eq 63-68): TEE partial CP-ABE (s, v, CT_0, V_base, Ψ_out)
  Step 6 (Eq 69-71): REE policy completion from cache
  Step 7 (Eq 72-73): Dilithium sign + Ω package
"""

import os
import sys
import config
import time
import json
import hashlib
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.chacha20 import SecureChaCha20
from crypto_primitives.aes_gcm import SecureAESGCM
from crypto_primitives.kyber import SecureKyber
from crypto_primitives.dilithium import SecureDilithium
from crypto_primitives.cp_abe import LatticeCPABE
from utils.dataset_loader import DataLoader


def _compute_g_tag(auths, t_G):
    """Eq 54: GTag' ← H(Sort({Auth_i | P_i ∈ P_valid}) ∥ t_G)"""
    return hashlib.sha256(b"".join(sorted(auths)) + t_G).digest()


def kdf(shared_secret, puf_secret, device_id, timestamp, counter):
    """Eq 16: K_{S,i} = KDF(H(k_kem) ∥ R_secret ∥ ID ∥ t ∥ ctr)"""
    h_kkem = hashlib.sha256(shared_secret).digest()
    msg = (h_kkem + puf_secret + device_id.encode()
           + str(timestamp).encode() + str(counter).encode())
    return hashlib.sha256(msg).digest()


def run_phase5_simulation():
    print("=" * 60)
    print("PQ-SPIDER Phase V Simulation: Fog Node Split-Phase Processing (Ours)")
    print("=" * 60)

    metrics = {
        "batch_verify":        0,
        "enclave_decrypt":     0,
        "aes_reencrypt":       0,
        "tee_partial_cpabe":   0,
        "ree_policy_expand":   0,
        "dilithium_sign":      0,
        "total_fog_latency":   0,
    }

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase3_dir = Path(__file__).parent.parent / "phase3_edge_gateway"

    try:
        batch = loader.load_data(phase3_dir, "ours_batch.json")
        packets = batch["packets"]
        fog_nodes = loader.load_data(phase1_dir, "ours_key.json")
        registry = loader.load_data(phase1_dir, "device_registry.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        sys.exit(1)

    print(f"  -> Loaded {len(packets)} IIoT packets.")
    devices_info = {d["device_id"]: d for d in registry}
    fog_node0 = fog_nodes[0]
    sk_fn = bytes.fromhex(fog_node0["sk"])

    aa_setup = loader.load_data(phase1_dir, "aa_setup.json")
    cpabe = LatticeCPABE(n=aa_setup["n"], q=aa_setup["q"])
    cpabe.A = np.array(aa_setup["mpk"]["A"], dtype=np.int64)
    for attr, vec in aa_setup["mpk"]["pub_vectors"].items():
        cpabe._pub[attr] = np.array(vec, dtype=np.int64)
    for attr in aa_setup["user_attributes"]:
        cpabe._ensure_attr(attr)

    # Load Dilithium keys from Phase I (keygen charged to Phase I timer)
    dil = SecureDilithium()
    pk_sig = {
        "rho": bytes.fromhex(fog_node0["pk_sig"]["rho"]),
        "t1":  fog_node0["pk_sig"]["t1"],
    }
    sk_sig = {
        "rho":     bytes.fromhex(fog_node0["sk_sig"]["rho"]),
        "sigma":   bytes.fromhex(fog_node0["sk_sig"]["sigma"]),
        "pk_hash": bytes.fromhex(fog_node0["sk_sig"]["pk_hash"]),
        "s1":      fog_node0["sk_sig"]["s1"],
        "s2":      fog_node0["sk_sig"]["s2"],
        "t0":      fog_node0["sk_sig"]["t0"],
    }

    # Eq 67: Base vector optimization — C_base(T_ID) = A^⊤ precomputed
    # Eq 69: Load precomputed LSSS policy cache from Phase I
    try:
        policy_cache = loader.load_data(phase1_dir, "policy_cache.json")
        print("  -> Loaded precomputed LSSS policy cache (Eq 4/69)")
    except FileNotFoundError:
        policy_cache = None
        print("  -> No policy cache found; will build fresh")

    start_total = time.perf_counter()

    # ── Step 1: Batch integrity verification (Eq 54) ──
    t0 = time.perf_counter()
    all_auths = [bytes.fromhex(p["auth_i"]) for p in packets]
    t_G = bytes.fromhex(batch["t_G"])
    received_g_tag = bytes.fromhex(batch["g_tag"])

    g_tag_fog = _compute_g_tag(all_auths, t_G)
    assert g_tag_fog == received_g_tag, "Batch integrity validation failed!"

    t_verify = (time.perf_counter() - t0) * 1000
    metrics["batch_verify"] = t_verify
    print(f"[1/7] Batch verify GTag (Eq 54): {t_verify:.2f} ms")

    # ── Step 2-3: Enclave packet decryption (Eq 55-60) ──
    # Sequential measurement; real parallelism requires ProcessPoolExecutor.
    print(f"[2-3/7] Enclave decrypt + aggregate ({len(packets)} packets)...")
    aggregated_plaintexts = []
    kyber_fn = SecureKyber()

    t_dec_start = time.perf_counter()
    for p in packets:
        # Kyber Decap
        c_kem = bytes.fromhex(p["c_kem"])
        k_kem = kyber_fn.decap(c_kem, sk_fn)

        # Eq 16: Session-key re-derivation
        device_id = p["device_id"]
        r_secret = bytes.fromhex(devices_info[device_id]["r_secret"])
        ks_i = kdf(k_kem, r_secret, device_id, p["timestamp"], 1)

        # Eq 56: m_ℓ ← ChaCha20-Poly1305.Dec(K_{S,ℓ}, N_ℓ, CT_ℓ, AAD_ℓ, Tag_ℓ)
        ct_i  = bytes.fromhex(p["ct_i"])
        nonce = bytes.fromhex(p["nonce"])
        aad   = bytes.fromhex(p["aad"])
        chacha = SecureChaCha20(key=ks_i)
        pt = chacha.decrypt(ct_i, nonce, associated_data=aad)
        aggregated_plaintexts.append(pt)
    t_decrypt = (time.perf_counter() - t_dec_start) * 1000
    metrics["enclave_decrypt"] = t_decrypt
    print(f"  -> Enclave decrypt × {len(packets)}: {t_decrypt:.2f} ms")

    # Eq 57-60: Aggregation
    m_agg   = b"".join(aggregated_plaintexts)
    aad_agg = b"".join(bytes.fromhex(p["aad"]) for p in packets)
    print(f"  -> M_agg: {len(m_agg)} bytes from {len(packets)} packets")

    # ── Step 4: AES-GCM re-encryption (Eq 61-62) ──
    t0 = time.perf_counter()
    k_aes = os.urandom(32)  # Eq 61: K_AES ← {0,1}^256
    aes = SecureAESGCM(key=k_aes)
    # Eq 62: (CT_AES, Tag_AES) ← AES-GCM.Enc(K_AES, IV, M_agg, AAD_agg)
    ct_aes, iv = aes.encrypt(m_agg, associated_data=aad_agg)
    t_aes = (time.perf_counter() - t0) * 1000
    metrics["aes_reencrypt"] = t_aes
    print(f"[4/7] AES-GCM re-encrypt (Eq 61-62): {t_aes:.2f} ms")

    # ── Step 5: TEE partial CP-ABE (Eq 63-68) ──
    # Eq 69: Retrieve precomputed LSSS from cache (or build fresh)
    t0 = time.perf_counter()
    if policy_cache:
        policy = policy_cache["policy"]
    else:
        policy = {"type": "AND", "attributes": aa_setup["user_attributes"]}
    policy_pkg = cpabe.ree_build_policy(policy)
    t_ree_build = (time.perf_counter() - t0) * 1000

    # Eq 63-66: TEE samples s, e_0, builds v, computes CT_0 and V_base
    t0 = time.perf_counter()
    tee_out = cpabe.tee_partial_encrypt(k_aes, policy_pkg)
    t_tee = (time.perf_counter() - t0) * 1000
    metrics["tee_partial_cpabe"] = t_tee

    # ── Step 6: REE CP-ABE completion (Eq 69-71) ──
    # Eq 70: CT_i = M_i · V_base + A^⊤_{ρ(i)} r_i + e_{1,i}
    # Eq 71: CT_{L-ABE} = (CT_0, (M, ρ_ID), {CT_i})
    t0 = time.perf_counter()
    ct_labe = cpabe.ree_finalize_ct(policy_pkg, tee_out)
    t_ree_finalize = (time.perf_counter() - t0) * 1000
    metrics["ree_policy_expand"] = t_ree_build + t_ree_finalize
    print(f"[5-6/7] CP-ABE TEE partial (Eq 63-68): {t_tee:.2f} ms   "
          f"REE expand (Eq 69-71): {metrics['ree_policy_expand']:.2f} ms")

    # ── Step 7: Dilithium sign + Ω package (Eq 72-73) ──
    # Eq 72: σ ← Sign_Dilithium(sk_FN, H(BID ∥ CT_AES ∥ CT_{L-ABE}))
    batch_id = b"BID-001"
    ct_labe_bytes = json.dumps({
        "policy_type": ct_labe["policy_type"],
        "rho":         ct_labe["rho"],
    }, sort_keys=True).encode()
    hash_input = hashlib.sha256(batch_id + ct_aes + ct_labe_bytes).digest()

    t0 = time.perf_counter()
    sigma = dil.sign(hash_input, sk_sig)
    t_sign = (time.perf_counter() - t0) * 1000
    metrics["dilithium_sign"] = t_sign
    print(f"[7/7] Dilithium sign (Eq 72): {t_sign:.2f} ms")

    metrics["total_fog_latency"] = (time.perf_counter() - start_total) * 1000

    # Eq 73: Ω = ⟨BID, CT_AES, Tag_AES, IV, CT_{L-ABE}, σ⟩
    def _to_py(v):
        if isinstance(v, np.ndarray): return v.tolist()
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, list): return [_to_py(x) for x in v]
        if isinstance(v, dict): return {k: _to_py(x) for k, x in v.items()}
        return v

    omega = {
        "batch_id": batch_id.hex(),
        "ct_aes":   ct_aes.hex(),
        "iv":       iv.hex(),
        "ct_labe": {
            "policy_type": ct_labe["policy_type"],
            "rho":         ct_labe["rho"],
            "M":           _to_py(ct_labe["M"]),
            "ct_rows":     _to_py(ct_labe["ct_rows"]),
            "ct0":         _to_py(ct_labe.get("ct0", [])),
            "ct_attr":     _to_py(ct_labe.get("ct_attr", [])),
        },
        "sigma":    sigma.hex(),
        "aad":      aad_agg.hex(),
        "pk_sig": {
            "rho": pk_sig["rho"].hex(),
            "t1":  _to_py([list(p) for p in pk_sig["t1"]]),
        },
    }
    loader.save_metrics(Path(__file__).parent, metrics)
    loader.save_data(Path(__file__).parent, "ours_omega.json", omega)

    sk_u_plain = {attr: cpabe._sec[attr].tolist()
                  for attr in aa_setup["user_attributes"]}
    loader.save_data(Path(__file__).parent, "ours_sku.json", {
        "sk_u":        sk_u_plain,
        "A":           cpabe.A.tolist(),
        "pub_vectors": {a: v.tolist() for a, v in cpabe._pub.items()},
        "n":           cpabe.n,
        "q":           cpabe.q,
    })

    print("\n" + "=" * 60)
    print(f"Phase V Simulation Finished. Total Fog Latency : "
          f"{metrics['total_fog_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase5_simulation()
