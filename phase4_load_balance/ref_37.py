"""
Phase IV (Ref [37]): SDN-GH — Adaptive SDN-Based Load Balancing
================================================================
A. M. Jasim and H. Al-Raweshidy, "An Adaptive SDN-Based Load
Balancing Method for Edge/Fog-Based Real-Time Healthcare Systems,"
IEEE Systems Journal, vol. 18, no. 2, pp. 1139-1150, June 2024.

Algorithm:
  SDN-GH uses a centralized SDN controller that maintains a global
  view of node utilization and applies a **three-factor** greedy
  heuristic combining queue load, service rate, and network latency:

    Score_GH(F_j) = α1 · (Q_j / Q_max)
                  + α2 · (1 − μ_j / μ_max)
                  + α3 · (L_j / L_max)

  The SDN controller collects flow statistics and performs pairwise
  coordination across medical centers (MC), yielding complexity:
    O(|MC|² + |MC| + P)

  Note: This simulation models a single-controller view (no MC
  pairwise coordination) for fair comparison against Spider++.

Characteristics vs Spider++:
  - Three-factor scoring (queue + rate + latency) vs 7+ factors
  - No EPC memory pressure tracking
  - No trust/capability scoring
  - No intra-node enclave selection
  - No computation reuse awareness
  - Centralized SDN controller (single point of failure)
"""

import sys
import config
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from utils.dataset_loader import DataLoader

# SDN-GH weights (per paper [37] emphasis on load balancing)
ALPHA1_QUEUE   = 0.5    # Queue load weight
ALPHA2_RATE    = 0.3    # Service rate weight
ALPHA3_LATENCY = 0.2    # Network latency weight


def sdn_gh_score(fog_node, Q_max, mu_max, L_max):
    """
    SDN-GH scoring: three-factor greedy heuristic per paper [37].
    Score_GH = α1·(Q_j/Q_max) + α2·(1 − μ_j/μ_max) + α3·(L_j/L_max)
    Lower score = better node.
    """
    enclaves = fog_node["enclaves"]
    Q_j = sum(e["queue_length"] for e in enclaves)
    mu_j = sum(e["service_rate"] for e in enclaves) / max(1, len(enclaves))
    L_j = fog_node.get("network_latency", 1.0)

    queue_factor = Q_j / max(1, Q_max)
    rate_factor = 1.0 - (mu_j / max(1, mu_max))
    latency_factor = L_j / max(1, L_max)

    return (ALPHA1_QUEUE * queue_factor
            + ALPHA2_RATE * rate_factor
            + ALPHA3_LATENCY * latency_factor)


def run_phase4_ref37():
    print("=" * 60)
    print("PQ-SPIDER Phase IV: SDN-GH Greedy Scheduling (Ref [37])")
    print("=" * 60)

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase3_dir = Path(__file__).parent.parent / "phase3_edge_gateway"

    try:
        fog_nodes = loader.load_data(phase1_dir, "ours_key.json")
        batch = loader.load_data(phase3_dir, "ours_batch.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        return

    packets = batch["packets"]
    print(f"  -> Scheduling {len(packets)} packets across "
          f"{len(fog_nodes)} fog nodes (SDN-GH: queue+rate+latency).")

    metrics = {
        "node_scoring_per_pkt":    [],
        "assignments":             [],
        "total_scheduler_latency": 0,
        "rejected_count":          0,
    }

    start = time.perf_counter()

    for p in packets:
        t0 = time.perf_counter()

        # SDN controller maintains global view — compute normalization
        Q_max = max(
            sum(e["queue_length"] for e in fn["enclaves"])
            for fn in fog_nodes
        )
        mu_max = max(
            sum(e["service_rate"] for e in fn["enclaves"])
            / max(1, len(fn["enclaves"]))
            for fn in fog_nodes
        )
        L_max = max(
            fn.get("network_latency", 1.0)
            for fn in fog_nodes
        )

        # Score all nodes with three-factor greedy heuristic
        node_scores = []
        for fn in fog_nodes:
            s = sdn_gh_score(fn, Q_max, mu_max, L_max)
            node_scores.append((fn, s))

        metrics["node_scoring_per_pkt"].append(
            (time.perf_counter() - t0) * 1000)

        # Select node with lowest greedy score
        node_scores.sort(key=lambda x: x[1])
        chosen_node, score_val = node_scores[0]

        # SDN-GH has no enclave-level scheduling — pick min-queue enclave
        chosen_enc = min(chosen_node["enclaves"],
                         key=lambda e: e["queue_length"])

        # Update state
        chosen_enc["queue_length"] += 1
        if chosen_enc["epc_availability"] >= config.PACKET_EPC_BYTES:
            chosen_enc["epc_availability"] -= config.PACKET_EPC_BYTES

        metrics["assignments"].append({
            "device":       p["device_id"],
            "fog_node":     chosen_node["id"],
            "enclave":      chosen_enc["id"],
            "node_score":   round(score_val, 4),
            "enclave_score": 0,
        })

    metrics["total_scheduler_latency"] = (time.perf_counter() - start) * 1000

    # Load distribution
    per_node_load = {}
    for a in metrics["assignments"]:
        per_node_load[a["fog_node"]] = per_node_load.get(
            a["fog_node"], 0) + 1

    loader.save_metrics(Path(__file__).parent, metrics,
                        filename="ref37_metrics.json")
    loader.save_data(Path(__file__).parent, "ref37_schedule.json", {
        "assignments": metrics["assignments"],
    })

    avg_node = (sum(metrics["node_scoring_per_pkt"])
                / max(1, len(packets)))
    print(f"\n  SDN-GH scoring (avg/pkt): {avg_node:.4f} ms")
    print(f"  Assignments: {len(metrics['assignments'])} / "
          f"Rejected: {metrics['rejected_count']}")
    print(f"  Per-node load distribution:")
    for nid, count in sorted(per_node_load.items()):
        print(f"    Node {nid}: {count} packets")
    print("\n" + "=" * 60)
    print(f"Phase IV (Ref [37] SDN-GH) Finished. Total: "
          f"{metrics['total_scheduler_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase4_ref37()
