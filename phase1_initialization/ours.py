"""
Phase I (Ours): PQ-SPIDER System Initialization
===================================================================
Matches PQ-SPIDER paper Sec III-C, Phase I (Eq 1-12 + Policy Prep):

  AA Setup:
    Eq 1:  ID_j = H(attr_j)                        — Attribute hashing
    Eq 2:  (MPK, MSK) ← Setup(1^λ, {ID_j})         — Lattice trapdoor gen
           For each attr: t_j ← small_vec, u_j = A^T · t_j  (dual-Regev keys)
    Eq 3:  (M, ρ_ID) ← PolicyTreeGen(T_ID)         — LSSS precomputation
    Eq 4:  C_policy(T_ID) = (M, ρ_ID)              — Cache for reuse
    Eq 5:  SK_u ← KeyGen(MSK, {ID_j}_{j ∈ Attr_u}) — User key

  Gateway Initialization:
    Eq 6:  (pk_GW, sk_GW) ← KeyGen_Kyber(1^λ)     — Gateway Kyber
    Eq 7:  (c_gkem, k_gkem) ← Encap_Kyber(pk_GW)  — Device-GW encap

  Fog Node Initialization:
    Eq 8:  (pk_FN, sk_FN) ← KeyGen_Kyber(1^λ)     — Fog Kyber

  Kyber Precomputation:
    Eq 9:  A ← ExpandA(seed_FN)                    — Kyber precomputation
    Eq 10: Â = NTT(A)                              — NTT cache
    Eq 11: C_Kyber(F_j) = Â                        — Persisted for reuse

  Enclave Instantiation:
    Eq 12: F_j = {E_{j,k} | k=1,...,m_j}           — Enclave instantiation

  Policy Preparation (NEW):
    Devices pre-compute hashed attribute identifiers and construct
    T_ID using {ID_j}, ensuring semantic privacy during encryption.
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

from utils.system_profiler import SystemProfiler

from crypto_primitives.cp_abe import LatticeCPABE
from crypto_primitives.kyber import SecureKyber
from crypto_primitives.dilithium import SecureDilithium
from crypto_primitives.puf import SRAM_PUF, FuzzyExtractor
from utils.dataset_loader import DataLoader


# Ring dimension aligned with Ref [4] (n=256). q=3329 matches Kyber's
# ring field; the two schemes differ only in modulus.
CPABE_N = 256
CPABE_Q = 3329


def run_phase1_simulation():
    print("="*60)
    print("PQ-SPIDER Phase I Simulation: System Initialization (Ours)")
    print("="*60)

    metrics = {
        "aa_setup": 0,
        "attr_keygen": 0,
        "policy_precompute": 0,
        "user_keygen": 0,
        "gateway_init": 0,
        "fog_node_init": [],
        "kyber_precompute": [],
        "device_precompute": [],
        "total_init": 0
    }

    start_total = time.perf_counter()

    # ── Step 1: Attribute Authority (AA) Setup ──
    # Eq 1: ID_j = H(attr_j) for each attr in universe
    # Eq 2: (MPK, MSK) ← Setup(1^λ, {ID_j})
    #        Generates matrix A and dual-Regev keys (t_j, u_j) for ALL attributes
    print("[1/7] Initializing Attribute Authority (CP-ABE Setup)...")
    t0 = time.perf_counter()
    aa = LatticeCPABE(n=CPABE_N, q=CPABE_Q)
    universe = config.CP_ABE_UNIVERSE
    # Eq 2: Generate MPK (matrix A)
    aa.setup()
    # Eq 1: Hash all attributes in universe → ID_j = H(attr_j)
    hashed_ids = {attr: aa.hash_attribute(attr) for attr in universe}
    t_aa = (time.perf_counter() - t0) * 1000
    metrics["aa_setup"] = t_aa
    print(f"  -> AA Setup Completed: {t_aa:.2f} ms (n={CPABE_N}, q={CPABE_Q})")

    # Eq 2 cont.: Generate dual-Regev key pairs for ALL attributes
    #   For each attr: t_j ← small_vec(n), u_j = A^T · t_j mod q
    #   This binds public parameter matrices to the hashed identifiers
    print("  -> Generating dual-Regev keys for attribute universe...")
    t0 = time.perf_counter()
    _ = aa.keygen({}, universe)
    t_attr_kg = (time.perf_counter() - t0) * 1000
    metrics["attr_keygen"] = t_attr_kg
    print(f"  -> Attribute KeyGen: {t_attr_kg:.2f} ms ({len(universe)} attributes)")

    # ── Step 2: LSSS Policy Precomputation ──
    # Eq 3: (M, ρ_ID) ← PolicyTreeGen(T_ID)
    # Eq 4: C_policy(T_ID) = (M, ρ_ID) — cached for reuse in Phase V
    #        Uses hashed IDs (not semantic labels) to preserve privacy
    print("\n[2/7] Precomputing LSSS Policy (C_policy cache)...")
    t0 = time.perf_counter()
    policy = {"type": "AND", "attributes": config.USER_ATTRIBUTES}
    policy_pkg = aa.ree_build_policy(policy)
    t_policy = (time.perf_counter() - t0) * 1000
    metrics["policy_precompute"] = t_policy
    print(f"  -> Policy precomputed and cached: {t_policy:.2f} ms")

    # ── Step 3: User Registration ──
    # Eq 5: SK_u ← KeyGen(MSK, {ID_j}_{j ∈ Attr_u})
    print("\n[3/7] Registering Authorized User (KeyGen)...")
    t0 = time.perf_counter()
    user_attributes = config.USER_ATTRIBUTES
    sk_u = aa.keygen({}, user_attributes)
    t_kg = (time.perf_counter() - t0) * 1000
    metrics["user_keygen"] = t_kg
    print(f"  -> User KeyGen Completed: {t_kg:.2f} ms")

    # ── Step 4: Gateway Initialization ──
    # Eq 6: (pk_GW, sk_GW) ← KeyGen_Kyber(1^λ)
    print("\n[4/7] Initializing Edge Gateway (Kyber KeyGen)...")
    t0 = time.perf_counter()
    kyber_gw = SecureKyber()
    pk_gw, sk_gw = kyber_gw.keygen()
    t_gw = (time.perf_counter() - t0) * 1000
    metrics["gateway_init"] = t_gw
    print(f"  -> Edge Gateway Ready ({t_gw:.2f} ms)")

    # ── Step 5: Fog Node Initialization + Kyber Precomputation ──
    # Eq 8:  (pk_FN, sk_FN) ← KeyGen_Kyber(1^λ)     — Fog Kyber keypair
    # Eq 9:  A ← ExpandA(seed_FN)                    — Kyber matrix expansion
    # Eq 10: Â = NTT(A)                              — NTT domain cache
    # Eq 11: C_Kyber(F_j) = Â                        — Persisted for reuse
    # Eq 12: F_j = {E_{j,k}}                         — Enclave instantiation
    num_fog_nodes = config.NUM_GLOBAL_NODES
    print(f"\n[5/7] Initializing {num_fog_nodes} Fog Nodes "
          f"(Kyber + Dilithium + Kyber Precomputation + Enclaves)...")

    fog_nodes = []
    ENC_PER_NODE = config.ENC_PER_NODE
    EPC_BUDGET_BYTES = config.EPC_BUDGET_BYTES

    # Reuse single crypto instances across all fog nodes (avoids
    # re-initializing zeta tables, NTT precomputation per node)
    kyber_fn = SecureKyber()
    dil_fn = SecureDilithium()

    # ── Live hardware profiling (replaces hardcoded QEMU constants) ──
    profiler = SystemProfiler()
    measured_rtt = profiler.get_network_latency_ms()
    base_capability = profiler.get_capability_score()
    hw_summary = profiler.get_system_summary()
    print(f"  [SystemProfiler] CPU={hw_summary['cpu_freq_mhz']}MHz, "
          f"RAM={hw_summary['total_ram_mb']:.0f}MB, "
          f"cores={hw_summary['cpu_cores']}, "
          f"RTT={measured_rtt:.3f}ms, "
          f"C_base={base_capability}")

    # Heterogeneous capacity tiers — 3 classes of fog nodes
    # (Eq 31: F_j has distinct computational profiles)
    CAPACITY_TIERS = [
        {"tier": "High",   "cpu_speed": 1.5, "mem_mb": 8192, "enc_count": 4},
        {"tier": "Medium", "cpu_speed": 1.0, "mem_mb": 4096, "enc_count": 3},
        {"tier": "Low",    "cpu_speed": 0.6, "mem_mb": 2048, "enc_count": 2},
    ]

    for i in range(num_fog_nodes):
        t_fn0 = time.perf_counter()

        # Assign tier: first 30% High, next 40% Medium, last 30% Low
        if i < max(1, num_fog_nodes * 3 // 10):
            tier = CAPACITY_TIERS[0]   # High
        elif i < max(2, num_fog_nodes * 7 // 10):
            tier = CAPACITY_TIERS[1]   # Medium
        else:
            tier = CAPACITY_TIERS[2]   # Low

        enc_count = tier["enc_count"]

        # Eq 8: Kyber KEM keypair
        pk, sk = kyber_fn.keygen()

        # Eq 9-11: Kyber Precomputation — expand A via SHAKE256
        t_kyber_pre = time.perf_counter()
        seed_fn = hashlib.sha256(pk[:32]).digest()
        # Eq 9: A ← ExpandA(seed_FN) — SHAKE256 expansion
        shake = hashlib.shake_256(seed_fn)
        raw = shake.digest(256 * 2)  # 2 bytes per coefficient
        A_expanded = np.frombuffer(raw, dtype=np.uint16).astype(np.int64) % 3329
        # Eq 10: Â = NTT(A) — NTT domain cache
        A_hat = np.fft.fft(A_expanded.astype(np.float64)).real.astype(np.int64) % 3329
        # Eq 11: C_Kyber(F_j) = Â — persisted for reuse scoring
        kyber_cache = {"A_hat": A_hat.tolist(), "has_cache": True}
        metrics["kyber_precompute"].append(
            (time.perf_counter() - t_kyber_pre) * 1000
        )

        # Dilithium signing keypair (charged to Phase I per audit)
        pk_sig, sk_sig = dil_fn.keygen()

        # Eq 12: Enclave instantiation F_j = {E_{j,k}}
        per_enc_epc = EPC_BUDGET_BYTES // enc_count
        enclaves = []
        for k in range(enc_count):
            seed = hashlib.sha256(f"node{i}-enc{k}".encode()).digest()
            # Service rate scales with CPU speed tier
            base_rate = 80 + (int.from_bytes(seed[:2], "little") % 121)
            service_rate = int(base_rate * tier["cpu_speed"])
            enclaves.append({
                "id":                 f"E_{i}_{k}",
                "queue_length":       0,
                "service_rate":       service_rate,
                "epc_availability":   per_enc_epc,
                "epc_total":          per_enc_epc,
                "contention":         profiler.get_cpu_contention(core_id=k),
            })

        t_fn = (time.perf_counter() - t_fn0) * 1000

        fog_nodes.append({
            "id": i,
            "pk": pk.hex(),
            "sk": sk.hex(),
            "pk_sig": {
                "rho": pk_sig["rho"].hex(),
                "t1":  [list(p) for p in pk_sig["t1"]],
            },
            "sk_sig": {
                "rho":     sk_sig["rho"].hex(),
                "sigma":   sk_sig["sigma"].hex(),
                "pk_hash": sk_sig["pk_hash"].hex(),
                "s1":      [list(p) for p in sk_sig["s1"]],
                "s2":      [list(p) for p in sk_sig["s2"]],
                "t0":      [list(p) for p in sk_sig["t0"]],
            },
            "kyber_cache": kyber_cache if i < max(1, num_fog_nodes * 3 // 10) else {
                "has_cache": False, "A_ntt": [], "pk_ntt": []
            },
            "policy_cached": i < max(1, num_fog_nodes * 3 // 10),
            "init_time": t_fn,
            "enclaves": enclaves,
            # Heterogeneous node profile (Eq 31)
            # Live measurements from psutil SystemProfiler
            "capacity_tier":    tier["tier"],
            "cpu_speed_factor": tier["cpu_speed"],
            "mem_total_mb":     tier["mem_mb"],
            "network_latency":  measured_rtt + (i * 0.05),  # base RTT + hop offset
            "capability_score": int(base_capability * tier["cpu_speed"]) - (i * 3),
            "trust_score":      config.MEASURED_BASE_TRUST,
        })
        metrics["fog_node_init"].append(t_fn)
        print(f"  -> Fog Node {i} Ready ({t_fn:.2f} ms) "
              f"[{tier['tier']}, {enc_count} enclaves, "
              f"CPUx{tier['cpu_speed']:.1f}]")

    # ── Step 6: IIoT Device Initialization ──
    # Eq 7: (c_gkem, k_gkem) ← Encap_Kyber(pk_GW)
    print("\n[6/7] Initializing IIoT Devices "
          "(PUF Generation + Gateway Encap)...")
    device_registry = []
    num_devices = config.NUM_DEVICES
    kyber_dev = SecureKyber()      # reuse one instance for all devices

    for i in range(num_devices):
        t0 = time.perf_counter()
        device_id = f"IIoT-DEV-{i:03d}"

        puf = SRAM_PUF()
        challenge = b"Phase2_Challenge"
        r_noisy = puf.evaluate(challenge)
        r_secret, _ = FuzzyExtractor.generate(r_noisy)

        # Eq 7: (c_gkem, k_gkem) ← Encap_Kyber(pk_GW)
        cg_kem, kg_kem = kyber_dev.encap(pk_gw)

        device_registry.append({
            "device_id": device_id,
            "r_secret": r_secret.hex(),
            "cg_kem": cg_kem.hex(),
            "kg_kem": kg_kem.hex(),
        })
        metrics["device_precompute"].append((time.perf_counter() - t0) * 1000)

    # ── Step 7: Policy Preparation (Device/Gateway-Side) ──
    # Paper: "IIoT devices (or associated gateways) pre-compute hashed
    # attribute identifiers and construct the access policy tree T_ID
    # using {ID_j}, ensuring that no semantic attribute information is
    # exposed during encryption and evaluation."
    print("\n[7/7] Policy Preparation "
          "(Hashing attribute IDs + Constructing T_ID)...")
    t0 = time.perf_counter()
    # Construct T_ID using hashed identifiers (not semantic labels)
    hashed_user_attrs = [str(hashed_ids[attr]) for attr in config.USER_ATTRIBUTES]
    t_id_policy = {"type": "AND", "attributes": hashed_user_attrs}
    # Pre-build LSSS from T_ID for reuse at encryption time
    t_id_pkg = aa.ree_build_policy(t_id_policy)
    t_policy_prep = (time.perf_counter() - t0) * 1000
    metrics["policy_preparation"] = t_policy_prep
    print(f"  -> T_ID constructed with {len(hashed_user_attrs)} hashed attributes: "
          f"{t_policy_prep:.2f} ms")

    metrics["total_init"] = (time.perf_counter() - start_total) * 1000

    # Persist AA setup for downstream phases
    aa_setup = {
        "mpk": {
            "A": aa.A.tolist(),
            "pub_vectors": {attr: vec.tolist()
                            for attr, vec in aa._pub.items()}
        },
        "sk_u": {attr: vec.tolist() for attr, vec in sk_u.items()},
        "universe": universe,
        "user_attributes": user_attributes,
        "q": aa.q,
        "n": aa.n
    }

    # Persist precomputed policy cache (Eq 4)
    def _to_py(v):
        if isinstance(v, np.ndarray): return v.tolist()
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, list): return [_to_py(x) for x in v]
        if isinstance(v, dict): return {k: _to_py(x) for k, x in v.items()}
        return v

    policy_cache = {
        "policy": policy,
        "policy_pkg": _to_py(policy_pkg),
        # Policy Preparation: T_ID constructed with hashed identifiers
        "t_id_policy": t_id_policy,
        "t_id_pkg": _to_py(t_id_pkg),
    }

    loader = DataLoader()
    phase_dir = Path(__file__).parent
    loader.save_metrics(phase_dir, metrics)
    loader.save_data(phase_dir, "ours_key.json", fog_nodes)
    loader.save_data(phase_dir, "ours_gw_key.json",
                     {"pk": pk_gw.hex(), "sk": sk_gw.hex()})
    loader.save_data(phase_dir, "aa_setup.json", aa_setup)
    loader.save_data(phase_dir, "device_registry.json", device_registry)
    loader.save_data(phase_dir, "policy_cache.json", policy_cache)

    print("\n" + "="*60)
    print(f"Phase I Simulation Finished. Total Latency: "
          f"{metrics['total_init']:.2f} ms")
    print("="*60)
    return metrics


if __name__ == "__main__":
    run_phase1_simulation()
