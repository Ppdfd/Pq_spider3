"""
Phase IV (Ref [37]): SDN-GH — Adaptive SDN-Based Load Balancing
================================================================
A. M. Jasim and H. Al-Raweshidy, "An Adaptive SDN-Based Load
Balancing Method for Edge/Fog-Based Real-Time Healthcare Systems,"
IEEE Systems Journal, vol. 18, no. 2, pp. 1139-1150, June 2024.

Algorithm (Algorithm 2, Eq. 8):
  SDN-GH uses an SDN controller with a global network view that
  performs BINARY OFFLOADING DECISIONS.  For each incoming task, the
  controller checks whether offloading to another node would reduce
  the total response time compared to local processing.

  The offloading decision is:
    T^{x2}_{x1} = 1  if t_offloading < t_local
                  0  otherwise                        (Eq. 8)

  where:
    t_local = Q_local / μ_local + t_proc(local)
    t_offloading = t_communication + Q_remote / μ_remote + t_proc(remote)

  The SDN controller collects workload, queue duration, and propagation
  delay metrics.  If offloading is beneficial, the task is sent to the
  candidate node with the minimum offloading time.

  Implementation note: Paper [37] describes pairwise coordination
  across Medical Centers (MCs).  This simulation models a single-
  controller view for fair comparison against Spider++.  The
  controller evaluates each candidate fog node as a potential
  offload target.

Characteristics vs Spider++:
  - Binary offloading decision (not weighted multi-factor score)
  - Two factors: processing time + communication overhead
  - No EPC memory awareness
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


def estimate_local_time(fog_node):
    """
    Estimate local processing time per paper [37]:
    t_local = (Q_local + 1) / μ_local
    This represents queue waiting time + service time for the local node.
    """
    enclaves = fog_node["enclaves"]
    total_q = sum(e["queue_length"] for e in enclaves)
    total_rate = sum(e["service_rate"] for e in enclaves)
    return (total_q + 1) / max(1, total_rate)


def estimate_offload_time(fog_node):
    """
    Estimate offloading time per paper [37] Eq. 8:
    t_offloading = t_communication + Q_remote / μ_remote + t_proc(remote)

    t_communication includes propagation delay and result delivery time,
    modelled as 2 × network_latency (round-trip).
    """
    enclaves = fog_node["enclaves"]
    total_q = sum(e["queue_length"] for e in enclaves)
    total_rate = sum(e["service_rate"] for e in enclaves)

    # Communication cost: propagation delay (round-trip)
    t_comm = 2.0 * fog_node.get("network_latency", 1.0)

    # Remote processing: queue wait + service
    t_proc_remote = (total_q + 1) / max(1, total_rate)

    return t_comm + t_proc_remote


def run_phase4_ref37():
    print("=" * 60)
    print("PQ-SPIDER Phase IV: SDN-GH Binary Offloading (Ref [37])")
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
          f"{len(fog_nodes)} fog nodes (SDN-GH: binary offloading, Eq. 8).")

    metrics = {
        "node_scoring_per_pkt":    [],
        "assignments":             [],
        "total_scheduler_latency": 0,
        "rejected_count":          0,
    }

    start = time.perf_counter()

    # Default local node = node 0 (simulates the originating MC)
    for p in packets:
        t0 = time.perf_counter()

        # SDN-GH Algorithm 2: For each task, the SDN controller:
        # 1. Computes t_local for the default node
        # 2. Evaluates t_offloading to each candidate
        # 3. If any t_offloading < t_local, offload to the best candidate

        # Default: assign to node with minimum current queue (local MC)
        local_idx = min(range(len(fog_nodes)),
                        key=lambda i: sum(e["queue_length"]
                                          for e in fog_nodes[i]["enclaves"]))
        local_node = fog_nodes[local_idx]
        t_local = estimate_local_time(local_node)

        # Evaluate offloading candidates (Eq. 8)
        best_offload_idx = None
        best_offload_time = t_local  # Only offload if faster than local

        for idx, fn in enumerate(fog_nodes):
            if idx == local_idx:
                continue
            t_off = estimate_offload_time(fn)
            # Eq. 8: T^{x2}_{x1} = 1 if t_offloading < t_local
            if t_off < best_offload_time:
                best_offload_time = t_off
                best_offload_idx = idx

        # Decision: offload if beneficial, otherwise process locally
        if best_offload_idx is not None:
            chosen_node = fog_nodes[best_offload_idx]
            score_val = best_offload_time
        else:
            chosen_node = local_node
            score_val = t_local

        metrics["node_scoring_per_pkt"].append(
            (time.perf_counter() - t0) * 1000)

        # SDN-GH has no enclave-level scheduling — assign to enclave
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
