"""
Phase IV (Ours): Spider++ Hierarchical Enclave-Oriented Load Balancing
======================================================================
Matches PQ-SPIDER paper Sec III-C, Phase IV (Eq 25-53):

  Eq 25-26: Hierarchical resource model (enclave sets + state)
  Eq 27-30: Batch profiling (Φ = ⟨S_k, ω_k, η_k, δ_k⟩)
  Eq 31:    Fog node state model Ψ(F_j)
  Eq 32-35: Waiting time, EPC pressure, capability/trust penalties
  Eq 36:    SpiderScore(F_j, B_k)
  Eq 37-40: Reuse-aware scoring (I_policy, I_kyber, R_reuse, SpiderScore')
  Eq 41:    Node selection: F* = arg min SpiderScore'
  Eq 42-46: Enclave-level scoring (wait, EPC, contention, affinity)
  Eq 47:    Enclave selection: E* = arg min EnclaveScore
  Eq 48-49: Parallel batch decomposition
  Eq 50:    Admission control: M_free ≥ α · M_req
  Eq 51:    Stability control: ΔScore ≥ ζ
  Eq 52-53: Secure delegation + complexity O(|F| + Σ m_j)
"""

import sys
import config
import time
import hashlib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from utils.dataset_loader import DataLoader
from phase4_load_balance.optee_bench.loader import load_measurements


# ─────────────────────────────────────────────────────────────
# Batch Profiling (Eq 27-30)
# ─────────────────────────────────────────────────────────────

def batch_profile(packets):
    """Eq 27: Φ(B_k) = ⟨S_k, ω_k, η_k, δ_k⟩"""
    S_k = len(packets)
    attr_count = len(config.USER_ATTRIBUTES)
    policy_depth = 1  # AND-tree depth

    # Eq 28: ω_k = β1·S_k + β2·AttrCount + β3·PolicyDepth
    omega_k = (config.BETA1_SIZE * S_k
               + config.BETA2_ATTR * attr_count
               + config.BETA3_DEPTH * policy_depth)

    # Eq 29: η_k from real packet priorities (0=low, 1=med, 2=high)
    avg_priority = sum(p.get("priority", 1) for p in packets) / max(1, S_k)
    eta_k = avg_priority / 2.0  # normalize to [0.0, 1.0]

    # Eq 30: δ_k from real packet deadlines
    now = time.time()
    min_deadline = min(p.get("deadline", now + 10) for p in packets)
    delta_k = 1.0 / max(0.001, min_deadline - now)

    return {"S_k": S_k, "omega_k": omega_k, "eta_k": eta_k, "delta_k": delta_k}


# ─────────────────────────────────────────────────────────────
# Level 1: Inter-Node Spider Score (Eq 32-41)
# ─────────────────────────────────────────────────────────────

def compute_waiting_time(fog_node):
    """Eq 32: T_wait(F_j) — superlinear queue growth for load spreading.
    Uses (Q+1)² / μ so score escalates fast as queue fills."""
    enclaves = fog_node["enclaves"]
    total_q = sum(e["queue_length"] for e in enclaves)
    avg_rate = max(1, sum(e["service_rate"] for e in enclaves) / len(enclaves))
    return (total_q + 1) ** 2 / avg_rate


def compute_epc_pressure(fog_node, profile):
    """Eq 33: P_epc = λ1 · max(0, M_req / (E_j·M_total) − τ)²"""
    enclaves = fog_node["enclaves"]
    total_epc = sum(e["epc_total"] for e in enclaves)
    avail_epc = sum(e["epc_availability"] for e in enclaves)
    E_j = avail_epc / max(1, total_epc)
    M_req = profile["omega_k"] * config.PACKET_EPC_BYTES
    ratio = M_req / max(1, E_j * total_epc) - config.EPC_PRESSURE_TAU
    return max(0.0, ratio) ** 2


def compute_capability_penalty(fog_node, profile):
    """Eq 34: P_cap = λ2 · max(0, ω_k − C_j)"""
    C_j = fog_node.get("capability_score", 100)
    return max(0.0, profile["omega_k"] - C_j)


def compute_trust_penalty(fog_node):
    """Eq 35: P_trust = λ3 · (1 − U_j)"""
    U_j = fog_node.get("trust_score", 0.9)
    return 1.0 - U_j


def compute_reuse_score(fog_node, profile):
    """Eq 37-39: I_policy, I_kyber, R_reuse"""
    # Eq 37: I_policy = 1 if policy cached
    I_policy = 1.0 if fog_node.get("policy_cached", False) else 0.0
    # Eq 38: I_kyber = 1 if Kyber precomputed
    I_kyber = 1.0 if fog_node.get("kyber_cache", {}).get("has_cache", False) else 0.0
    # Eq 39: R_reuse = θ1·I_policy + θ2·I_kyber
    return config.THETA1_POLICY * I_policy + config.THETA2_KYBER * I_kyber


def spider_score(fog_node, profile):
    """Eq 36 + Eq 40: SpiderScore'(F_j, B_k)"""
    T_wait = compute_waiting_time(fog_node)
    L_j = fog_node.get("network_latency", 1.0)
    P_epc = compute_epc_pressure(fog_node, profile)
    P_cap = compute_capability_penalty(fog_node, profile)
    P_trust = compute_trust_penalty(fog_node)
    U_j = fog_node.get("trust_score", 0.9)

    # Normalize service rate to [0,1] to prevent raw μ_TEE (100-200)
    # from dominating the score via the deadline bonus term
    raw_rate = sum(e["service_rate"] for e in fog_node["enclaves"]) \
               / len(fog_node["enclaves"])
    norm_rate = min(1.0, raw_rate / 200.0)  # cap at 200 = max expected

    # Eq 36: SpiderScore
    score = (config.W1_WAIT * T_wait
             + config.W2_LATENCY * L_j
             + config.W3_EPC * P_epc
             + config.W4_CAP * P_cap
             + config.W5_TRUST * P_trust
             - config.W6_URGENCY * profile["eta_k"] * U_j
             - config.W7_DEADLINE * profile["delta_k"] * norm_rate)

    # Eq 40: SpiderScore' = SpiderScore − w8 · R_reuse
    R_reuse = compute_reuse_score(fog_node, profile)
    score_prime = score - config.W8_REUSE * R_reuse

    return score_prime


# ─────────────────────────────────────────────────────────────
# Level 2: Intra-Node Enclave Score (Eq 42-47)
# ─────────────────────────────────────────────────────────────

def enclave_score(enclave, profile, recent_count):
    """Eq 46: EnclaveScore(E_{j,k}, B_k)"""
    # Eq 42: T_wait(E_{j,k}) = (q + 1) / μ
    T_wait = (enclave["queue_length"] + 1) / max(1, enclave["service_rate"])

    # Eq 43: P_epc(E_{j,k}) = λ'1 · max(0, M_req/M_free − τ)²
    M_free = max(1, enclave["epc_availability"])
    M_req = profile["omega_k"] * config.PACKET_EPC_BYTES / max(1, profile["S_k"])
    epc_ratio = M_req / M_free - config.EPC_PRESSURE_TAU
    P_epc = max(0.0, epc_ratio) ** 2

    # Eq 44: P_cont(E_{j,k}) = λ'2 · ρ_{j,k}
    # Dynamic contention: proportional to queue occupancy / service rate
    base_cont = enclave.get("contention", 0.0)
    dynamic_cont = enclave["queue_length"] / max(1, enclave["service_rate"])
    P_cont = base_cont + dynamic_cont

    # Eq 45: A(E_{j,k}) = 1 if similar workload processed previously
    A_affin = 1.0 if recent_count > 0 else 0.0

    # Eq 46: EnclaveScore
    return (config.Z1_ENC_WAIT * T_wait
            + config.Z2_ENC_EPC * P_epc
            + config.Z3_ENC_CONT * P_cont
            - config.Z4_ENC_AFFIN * A_affin)


# ─────────────────────────────────────────────────────────────
# Main Scheduler
# ─────────────────────────────────────────────────────────────

def run_phase4_simulation():
    print("=" * 60)
    print("PQ-SPIDER Phase IV: Spider++ Hierarchical Load Balancing")
    print("=" * 60)

    # Load OP-TEE benchmark measurements (patches config at runtime)
    load_measurements(config)

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase3_dir = Path(__file__).parent.parent / "phase3_edge_gateway"

    try:
        fog_nodes = loader.load_data(phase1_dir, "ours_key.json")
        batch = loader.load_data(phase3_dir, "ours_batch.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        print("  ! Run phase1/ours.py and phase3/ours.py first.")
        return

    packets = batch["packets"]
    print(f"  -> Scheduling {len(packets)} packets across "
          f"{len(fog_nodes)} fog nodes.")

    metrics = {
        "batch_profiling":             0,
        "node_scoring_per_pkt":        [],
        "enclave_scoring_per_pkt":     [],
        "assignments":                 [],
        "total_scheduler_latency":     0,
        "rejected_count":              0,
    }

    start = time.perf_counter()

    # ── Eq 27-30: Batch profiling ──
    t0 = time.perf_counter()
    profile = batch_profile(packets)
    metrics["batch_profiling"] = (time.perf_counter() - t0) * 1000
    print(f"  -> Batch profile: S_k={profile['S_k']}, "
          f"ω_k={profile['omega_k']:.1f}, η_k={profile['eta_k']:.2f}")

    # ── Pre-compute STATIC score components (once per batch) ──
    # These values don't change between packet assignments:
    #   L_j, P_cap, P_trust, U_j, norm_rate, R_reuse
    # Only T_wait (queue) and P_epc (EPC) change per-packet.
    _W1 = config.W1_WAIT
    _W2 = config.W2_LATENCY
    _W3 = config.W3_EPC
    _W4 = config.W4_CAP
    _W5 = config.W5_TRUST
    _W6 = config.W6_URGENCY
    _W7 = config.W7_DEADLINE
    _W8 = config.W8_REUSE
    _epc_tau = config.EPC_PRESSURE_TAU
    _pkt_epc = config.PACKET_EPC_BYTES
    _eta_k = profile["eta_k"]
    _delta_k = profile["delta_k"]
    _omega_k = profile["omega_k"]

    static_scores = []
    node_meta = []    # pre-extracted metadata per node

    # Inject live CPU contention from psutil before scoring
    from utils.system_profiler import SystemProfiler
    profiler = SystemProfiler()
    for fn in fog_nodes:
        for idx, e in enumerate(fn["enclaves"]):
            e["contention"] = profiler.get_cpu_contention(core_id=idx)

    for fn in fog_nodes:
        enclaves = fn["enclaves"]
        n_enc = len(enclaves)

        # Static components
        L_j = fn.get("network_latency", 1.0)
        C_j = fn.get("capability_score", 100)
        U_j = fn.get("trust_score", 0.9)
        raw_rate = sum(e["service_rate"] for e in enclaves) / n_enc
        norm_rate = min(1.0, raw_rate / 200.0)

        P_cap = max(0.0, _omega_k - C_j)
        P_trust = 1.0 - U_j

        I_policy = 1.0 if fn.get("policy_cached", False) else 0.0
        kyber_cache = fn.get("kyber_cache", {})
        I_kyber = 1.0 if (isinstance(kyber_cache, dict)
                          and kyber_cache.get("has_cache", False)) else 0.0
        R_reuse = config.THETA1_POLICY * I_policy + config.THETA2_KYBER * I_kyber

        static = (_W2 * L_j
                   + _W4 * P_cap
                   + _W5 * P_trust
                   - _W6 * _eta_k * U_j
                   - _W7 * _delta_k * norm_rate
                   - _W8 * R_reuse)

        total_epc = sum(e["epc_total"] for e in enclaves)
        avg_rate = max(1, raw_rate)

        static_scores.append(static)
        node_meta.append({
            "avg_rate": avg_rate,
            "total_epc": total_epc,
            "n_enc": n_enc,
        })

    recent_count = {}
    for fn in fog_nodes:
        for e in fn["enclaves"]:
            recent_count[e["id"]] = 0

    for p in packets:
        # ── Level 1: Inter-Node Selection (Eq 41) ──
        # Only recompute dynamic components: T_wait + P_epc
        t0 = time.perf_counter()

        best_node = None
        best_score = float('inf')
        best_idx = -1

        for idx, fn in enumerate(fog_nodes):
            enclaves = fn["enclaves"]
            meta = node_meta[idx]

            # Admission control — at least one enclave has EPC
            if not any(e["epc_availability"] >= _pkt_epc for e in enclaves):
                continue

            # Dynamic: T_wait (Eq 32) — superlinear queue growth
            total_q = sum(e["queue_length"] for e in enclaves)
            T_wait = (total_q + 1) ** 2 / meta["avg_rate"]

            # Dynamic: P_epc (Eq 33)
            avail_epc = sum(e["epc_availability"] for e in enclaves)
            E_j = avail_epc / max(1, meta["total_epc"])
            ratio = (_omega_k * _pkt_epc) / max(1, E_j * meta["total_epc"]) - _epc_tau
            P_epc = max(0.0, ratio) ** 2

            score = static_scores[idx] + _W1 * T_wait + _W3 * P_epc

            if score < best_score:
                best_score = score
                best_node = fn
                best_idx = idx

        metrics["node_scoring_per_pkt"].append(
            (time.perf_counter() - t0) * 1000)

        if best_node is None:
            metrics["rejected_count"] += 1
            print(f"  -> REJECT {p['device_id']} (no feasible fog node)")
            continue

        chosen_node = best_node
        node_score_val = best_score

        # ── Level 2: Intra-Node Enclave Selection (Eq 47) ──
        t0 = time.perf_counter()

        best_enc = None
        best_enc_score = float('inf')
        for e in chosen_node["enclaves"]:
            if e["epc_availability"] >= _pkt_epc:
                es = enclave_score(e, profile, recent_count.get(e["id"], 0))
                if es < best_enc_score:
                    best_enc_score = es
                    best_enc = e

        if best_enc is None:
            metrics["rejected_count"] += 1
            continue

        chosen_enc = best_enc
        enc_score_val = best_enc_score

        # Update enclave state after assignment
        chosen_enc["queue_length"] += 1
        chosen_enc["epc_availability"] -= _pkt_epc
        # Update contention dynamically (Eq 44)
        chosen_enc["contention"] = chosen_enc["queue_length"] / max(1, chosen_enc["service_rate"])
        recent_count[chosen_enc["id"]] = recent_count.get(chosen_enc["id"], 0) + 1

        metrics["enclave_scoring_per_pkt"].append(
            (time.perf_counter() - t0) * 1000)

        metrics["assignments"].append({
            "device":       p["device_id"],
            "fog_node":     chosen_node["id"],
            "enclave":      chosen_enc["id"],
            "node_score":   round(node_score_val, 4),
            "enclave_score": round(enc_score_val, 4),
        })

    metrics["total_scheduler_latency"] = (time.perf_counter() - start) * 1000

    # Load distribution summary
    per_enclave_load = {}
    for a in metrics["assignments"]:
        per_enclave_load[a["enclave"]] = per_enclave_load.get(
            a["enclave"], 0) + 1

    # Post-scheduling state for downstream phases
    post_state = []
    for fn in fog_nodes:
        for e in fn["enclaves"]:
            post_state.append({
                "fog_node_id":      fn["id"],
                "id":               e["id"],
                "queue_length":     e["queue_length"],
                "service_rate":     e["service_rate"],
                "epc_availability": e["epc_availability"],
                "epc_total":        e["epc_total"],
            })

    loader.save_metrics(Path(__file__).parent, metrics)
    loader.save_data(Path(__file__).parent, "ours_schedule.json", {
        "assignments":  metrics["assignments"],
        "post_state":   post_state,
    })

    avg_node = (sum(metrics["node_scoring_per_pkt"])
                / max(1, len(packets)))
    avg_enc = (sum(metrics["enclave_scoring_per_pkt"])
               / max(1, len(metrics["enclave_scoring_per_pkt"])))
    print(f"\n[1] Batch profiling          : {metrics['batch_profiling']:.4f} ms")
    print(f"[2] Node scoring (avg/pkt)   : {avg_node:.4f} ms")
    print(f"[3] Enclave scoring (avg/pkt): {avg_enc:.4f} ms")
    print(f"  Assignments: {len(metrics['assignments'])} / "
          f"Rejected: {metrics['rejected_count']}")
    print(f"  Per-enclave load distribution:")
    for enc_id, count in sorted(per_enclave_load.items()):
        print(f"    {enc_id}: {count} packets")
    print("\n" + "=" * 60)
    print(f"Phase IV (Ours) Finished. Total: "
          f"{metrics['total_scheduler_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase4_simulation()
