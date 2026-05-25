"""
Phase V (Ours): Multi-Enclave TEE-Assisted Split-Phase CP-ABE Processing
========================================================================
Matches PQ-SPIDER2 paper Sec III-C, Phase V (Eq 54-92):

  Step 1 (Eq 54-55):  GTag' verification
  Step 2 (Eq 56-64):  Enclave-parallel batch decomposition
                       B_k → {B_k^(1),...,B_k^(r)} with SubID_i
  Step 3 (Eq 65-73):  Per-enclave: decrypt, aggregate, chunk-encrypt,
                       auth token τ_i = MAC(h_i)
  Step 4 (Eq 74-81):  Trusted deterministic merge + Root_k commitment
  Step 5 (Eq 82-87):  TEE partial CP-ABE (s, v, CT_0, V_base, Ψ_out)
  Step 6 (Eq 88-90):  REE policy completion from cache
  Step 7 (Eq 91-92):  Dilithium sign + Ω package with D_k manifest
"""

import os
import sys
import config
import time
import json
import hashlib
import hmac
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
    """Eq 15: K_{S,i} = KDF(H(k_kem) ∥ R_secret ∥ ID ∥ t ∥ ctr)"""
    h_kkem = hashlib.sha256(shared_secret).digest()
    msg = (h_kkem + puf_secret + device_id.encode()
           + str(timestamp).encode() + str(counter).encode())
    return hashlib.sha256(msg).digest()


def _chunk_kdf(k_master, batch_id, sub_id, epoch):
    """Eq 68: K_chunk^(i) = KDF(K_master_AES ∥ BID ∥ SubID_i ∥ epoch_k)"""
    return hashlib.sha256(
        k_master + batch_id + sub_id + str(epoch).encode()
    ).digest()


def _compute_sub_id(batch_id, index, epoch):
    """Eq 64: SubID_i = H(BID ∥ i ∥ epoch_k)"""
    return hashlib.sha256(
        batch_id + str(index).encode() + str(epoch).encode()
    ).digest()


def run_phase5_simulation():
    print("=" * 60)
    print("PQ-SPIDER Phase V Simulation: Fog Node Split-Phase Processing (Ours)")
    print("=" * 60)

    metrics = {
        "batch_verify":        0,
        "enclave_decrypt":     0,
        "chunk_encrypt":       0,
        "merge_commit":        0,
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

    # Eq 88: Load precomputed LSSS policy cache from Phase I
    try:
        policy_cache = loader.load_data(phase1_dir, "policy_cache.json")
        print("  -> Loaded precomputed LSSS policy cache (Eq 4/88)")
    except FileNotFoundError:
        policy_cache = None
        print("  -> No policy cache found; will build fresh")

    start_total = time.perf_counter()

    # ── Step 1: Batch integrity verification (Eq 54-55) ──
    t0 = time.perf_counter()
    all_auths = [bytes.fromhex(p["auth_i"]) for p in packets]
    t_G = bytes.fromhex(batch["t_G"])
    received_g_tag = bytes.fromhex(batch["g_tag"])

    g_tag_fog = _compute_g_tag(all_auths, t_G)
    assert g_tag_fog == received_g_tag, "Batch integrity validation failed!"

    t_verify = (time.perf_counter() - t0) * 1000
    metrics["batch_verify"] = t_verify
    print(f"[1/7] Batch verify GTag (Eq 54): {t_verify:.2f} ms")

    # ── Step 2: Enclave-parallel batch decomposition (Eq 56-64) ──
    # Determine decomposition factor r (Eq 59)
    batch_id = b"BID-001"
    epoch_k = 1
    enc_count = fog_node0.get("enclaves", [{}])
    n_enclaves = len(enc_count) if isinstance(enc_count, list) else config.ENC_PER_NODE
    n_packets = len(packets)

    # Eq 59: r = min(N_E, ceil(|B_k|*s_k / (eta*M_EPC)) + ...)
    # Simplified: r = min(available_enclaves, ceil(n_packets / packets_per_enclave))
    # Using at least 2 sub-batches if there are enough packets and enclaves
    r = min(n_enclaves, max(1, n_packets))
    r = max(1, r)  # At least 1 sub-batch

    # Eq 61-63: Partition packets into r approximately balanced sub-batches
    sub_batches = [[] for _ in range(r)]
    for i, pkt in enumerate(packets):
        sub_batches[i % r].append(pkt)

    # Generate SubID for each sub-batch (Eq 64)
    sub_ids = [_compute_sub_id(batch_id, i, epoch_k) for i in range(r)]

    print(f"[2/7] Batch decomposition: {n_packets} packets -> "
          f"{r} sub-batches (Eq 56-64)")

    # ── Step 3: Enclave-parallel decrypt + chunk encrypt (Eq 65-73) ──
    # Eq 65: K_master_AES ← {0,1}^256
    k_master_aes = os.urandom(32)
    kyber_fn = SecureKyber()

    # Enclave-sealed key for auth tokens (Eq 72)
    k_tee_seal = os.urandom(32)

    enclave_outputs = []  # Γ_i from each enclave (Eq 73)

    t_dec_start = time.perf_counter()
    for sub_idx in range(r):
        sub_packets = sub_batches[sub_idx]
        sub_id = sub_ids[sub_idx]

        # Decrypt packets in this sub-batch (Eq 66)
        sub_plaintexts = []
        for p in sub_packets:
            c_kem = bytes.fromhex(p["c_kem"])
            k_kem = kyber_fn.decap(c_kem, sk_fn)
            device_id = p["device_id"]
            r_secret = bytes.fromhex(devices_info[device_id]["r_secret"])
            ks_i = kdf(k_kem, r_secret, device_id, p["timestamp"], 1)
            ct_i = bytes.fromhex(p["ct_i"])
            nonce = bytes.fromhex(p["nonce"])
            aad = bytes.fromhex(p["aad"])
            chacha = SecureChaCha20(key=ks_i)
            pt = chacha.decrypt(ct_i, nonce, associated_data=aad)
            sub_plaintexts.append(pt)

        # Eq 67: Streaming aggregation S_j = H(S_{j-1} ∥ m_j)
        M_i = b"".join(sub_plaintexts)
        AAD_i = b"".join(bytes.fromhex(p["aad"]) for p in sub_packets)

        # Eq 68: K_chunk^(i) = KDF(K_master_AES ∥ BID ∥ SubID_i ∥ epoch_k)
        k_chunk = _chunk_kdf(k_master_aes, batch_id, sub_id, epoch_k)

        # Eq 69-70: (C_i, Tag_i) ← AES-GCM.Enc(K_chunk^(i), IV_i, M_i, AAD_i)
        aes_chunk = SecureAESGCM(key=k_chunk)
        C_i, IV_i = aes_chunk.encrypt(M_i, associated_data=AAD_i)

        # Eq 71: h_i = H(BID ∥ SubID_i ∥ epoch_k ∥ C_i ∥ Tag_i ∥ IV_i ∥ AAD_i)
        h_i = hashlib.sha256(
            batch_id + sub_id + str(epoch_k).encode()
            + C_i + IV_i + AAD_i
        ).digest()

        # Eq 72: τ_i = MAC_{K_TEE_i}(h_i)
        tau_i = hmac.new(k_tee_seal, h_i, hashlib.sha256).digest()

        # Eq 73: Γ_i = (SubID_i, C_i, Tag_i, IV_i, AAD_i, h_i, τ_i)
        enclave_outputs.append({
            "sub_id": sub_id,
            "C_i": C_i,
            "IV_i": IV_i,
            "AAD_i": AAD_i,
            "h_i": h_i,
            "tau_i": tau_i,
            "chunk_len": len(C_i),
        })

    t_decrypt = (time.perf_counter() - t_dec_start) * 1000
    metrics["enclave_decrypt"] = t_decrypt
    print(f"[3/7] Enclave decrypt + chunk encrypt x {r} sub-batches: "
          f"{t_decrypt:.2f} ms")

    # ── Step 4: Trusted deterministic merge + Root_k (Eq 74-81) ──
    t0 = time.perf_counter()

    # Eq 74: Verify each enclave MAC token
    for gamma in enclave_outputs:
        expected_tau = hmac.new(k_tee_seal, gamma["h_i"], hashlib.sha256).digest()
        assert hmac.compare_digest(gamma["tau_i"], expected_tau), \
            "Enclave MAC verification failed!"

    # Eq 75: Deterministic merge ordering O = SortBy(SubID_i)
    enclave_outputs.sort(key=lambda g: g["sub_id"])

    # Eq 76-78: Merge encrypted chunks
    CT_AES = b"".join(g["C_i"] for g in enclave_outputs)

    # Eq 79: IV set
    IVs = [g["IV_i"] for g in enclave_outputs]

    # Eq 80-81: Root_k = H(BID ∥ epoch_k ∥ r ∥ h^(1) ∥ ... ∥ h^(r))
    root_input = batch_id + str(epoch_k).encode() + str(r).encode()
    for g in enclave_outputs:
        root_input += g["h_i"]
    Root_k = hashlib.sha256(root_input).digest()

    # Build chunk manifest D_k (Eq 94)
    # D_k = {(SubID_i, |C_i|, AAD_i, IV_i, Tag_i)}_i
    chunk_manifest = []
    for g in enclave_outputs:
        chunk_manifest.append({
            "sub_id": g["sub_id"].hex(),
            "chunk_len": g["chunk_len"],
            "aad": g["AAD_i"].hex(),
            "iv": g["IV_i"].hex(),
        })

    t_merge = (time.perf_counter() - t0) * 1000
    metrics["merge_commit"] = t_merge
    print(f"[4/7] Deterministic merge + Root_k (Eq 74-81): {t_merge:.2f} ms")

    # Aggregate AAD for the full batch (for CP-ABE context binding)
    aad_agg = b"".join(g["AAD_i"] for g in enclave_outputs)
    print(f"  -> CT_AES: {len(CT_AES)} bytes, {r} chunks, "
          f"Root_k: {Root_k[:8].hex()}...")

    # ── Step 5: TEE partial CP-ABE (Eq 82-87) ──
    # Eq 88: Retrieve precomputed LSSS from cache (or build fresh)
    t0 = time.perf_counter()
    if policy_cache:
        policy = policy_cache["policy"]
    else:
        policy = {"type": "AND", "attributes": aa_setup["user_attributes"]}
    policy_pkg = cpabe.ree_build_policy(policy)
    t_ree_build = (time.perf_counter() - t0) * 1000

    # Eq 82-86: TEE samples s, e_0, builds v, computes CT_0 and V_base
    t0 = time.perf_counter()
    tee_out = cpabe.tee_partial_encrypt(k_master_aes, policy_pkg)
    t_tee = (time.perf_counter() - t0) * 1000
    metrics["tee_partial_cpabe"] = t_tee

    # ── Step 6: REE CP-ABE completion (Eq 88-90) ──
    # Eq 89: CT_i = M_i * V_base + A^T_{rho(i)} r_i + e_{1,i}
    # Eq 90: CT_{L-ABE} = (CT_0, (M, rho_ID), {CT_i})
    t0 = time.perf_counter()
    ct_labe = cpabe.ree_finalize_ct(policy_pkg, tee_out)
    t_ree_finalize = (time.perf_counter() - t0) * 1000
    metrics["ree_policy_expand"] = t_ree_build + t_ree_finalize
    print(f"[5-6/7] CP-ABE TEE partial (Eq 82-86): {t_tee:.2f} ms   "
          f"REE expand (Eq 88-90): {metrics['ree_policy_expand']:.2f} ms")

    # ── Step 7: Dilithium sign + Omega package (Eq 91-92) ──
    # Eq 91: sigma ← Sign_Dilithium(sk_FN, H(BID ∥ epoch_k ∥ CT_AES
    #                                         ∥ D_k ∥ CT_{L-ABE} ∥ Root_k))
    ct_labe_bytes = json.dumps({
        "policy_type": ct_labe["policy_type"],
        "rho":         ct_labe["rho"],
    }, sort_keys=True).encode()
    dk_bytes = json.dumps(chunk_manifest, sort_keys=True).encode()
    hash_input = hashlib.sha256(
        batch_id + str(epoch_k).encode()
        + CT_AES + dk_bytes + ct_labe_bytes + Root_k
    ).digest()

    t0 = time.perf_counter()
    sigma = dil.sign(hash_input, sk_sig)
    t_sign = (time.perf_counter() - t0) * 1000
    metrics["dilithium_sign"] = t_sign
    print(f"[7/7] Dilithium sign (Eq 91): {t_sign:.2f} ms")

    metrics["total_fog_latency"] = (time.perf_counter() - start_total) * 1000

    # Eq 92: Omega = (BID, epoch_k, CT_AES, D_k, CT_{L-ABE}, Root_k, sigma)
    def _to_py(v):
        if isinstance(v, np.ndarray): return v.tolist()
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, list): return [_to_py(x) for x in v]
        if isinstance(v, dict): return {k: _to_py(x) for k, x in v.items()}
        return v

    omega = {
        "batch_id": batch_id.hex(),
        "epoch_k": epoch_k,
        "ct_aes":   CT_AES.hex(),
        "chunk_manifest": chunk_manifest,  # D_k (Eq 94)
        "root_k":   Root_k.hex(),          # Aggregation commitment (Eq 81)
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
    print(f"  Enclave-parallel: {r} sub-batches, Root_k: {Root_k[:8].hex()}...")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase5_simulation()
