"""
Phase IV (Ref [22]): OLB — Optimised Load Balancing
=====================================================
M. Ala'anzy et al., "Dynamic Load Balancing for Enhanced Network
Performance in IoT-Enabled Smart Healthcare With Fog Computing,"
IEEE Access, 2024.

Algorithm:
  OLB dynamically assigns each task by scanning ALL candidate fog
  nodes and selecting the one with **minimum estimated latency**:
    Latency(F_j) = L_net(F_j) + T_proc(F_j)
  where:
    L_net  = network latency to fog node j
    T_proc = (Q_j + 1) / μ_j  (estimated processing time)

  Complexity: O(T · |F|)  — full-state query per task.

Characteristics vs Spider++:
  - Single-level scheduling (no intra-node enclave selection)
  - Two-factor latency estimate (network + queue/rate)
  - No EPC memory awareness
  - No trust/capability scoring
  - No computation reuse awareness (no cache discount)
"""

import sys
import config
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from utils.dataset_loader import DataLoader


def olb_score(fog_node):
    """
    OLB scoring: minimum-latency selection per paper [22].
    Latency = network_latency + estimated_processing_time.
    Processing estimate = (total_queue + 1) / avg_service_rate.
    """
    enclaves = fog_node["enclaves"]
    total_q = sum(e["queue_length"] for e in enclaves)
    avg_rate = sum(e["service_rate"] for e in enclaves) / max(1, len(enclaves))
    processing_est = (total_q + 1) / max(1, avg_rate)
    network_lat = fog_node.get("network_latency", 1.0)
    return network_lat + processing_est


def run_phase4_ref22():
    print("=" * 60)
    print("PQ-SPIDER Phase IV: OLB Latency-Based Scheduling (Ref [22])")
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
          f"{len(fog_nodes)} fog nodes (OLB: min-latency).")

    metrics = {
        "node_scoring_per_pkt":    [],
        "assignments":             [],
        "total_scheduler_latency": 0,
        "rejected_count":          0,
    }

    start = time.perf_counter()

    for p in packets:
        t0 = time.perf_counter()

        # OLB: scan ALL nodes, select minimum estimated latency
        node_scores = []
        for fn in fog_nodes:
            s = olb_score(fn)
            node_scores.append((fn, s))

        metrics["node_scoring_per_pkt"].append(
            (time.perf_counter() - t0) * 1000)

        # Select node with lowest latency (lowest score)
        node_scores.sort(key=lambda x: x[1])
        chosen_node, score_val = node_scores[0]

        # OLB has no enclave-level scheduling — assign to enclave
        # with shortest queue (consistent heuristic across baselines)
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
                        filename="ref22_metrics.json")
    loader.save_data(Path(__file__).parent, "ref22_schedule.json", {
        "assignments": metrics["assignments"],
    })

    avg_node = (sum(metrics["node_scoring_per_pkt"])
                / max(1, len(packets)))
    print(f"\n  OLB scoring (avg/pkt): {avg_node:.4f} ms")
    print(f"  Assignments: {len(metrics['assignments'])} / "
          f"Rejected: {metrics['rejected_count']}")
    print(f"  Per-node load distribution:")
    for nid, count in sorted(per_node_load.items()):
        print(f"    Node {nid}: {count} packets")
    print("\n" + "=" * 60)
    print(f"Phase IV (Ref [22] OLB) Finished. Total: "
          f"{metrics['total_scheduler_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase4_ref22()
