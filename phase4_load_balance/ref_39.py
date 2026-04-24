"""
Phase IV (Ref [39]): DIST — Distributed RL-Based Task Scheduling
=================================================================
E. Oustad, "DIST: Distributed Learning-Based Energy-Efficient and
Reliable Task Scheduling and Resource Allocation in Fog Computing,"
IEEE Trans. Services Computing, vol. 18, no. 3, pp. 1336-, 2025.

Algorithm:
  DIST uses a **distributed reinforcement learning** (Q-learning)
  mechanism where each region independently learns optimal task
  placement.  The Q-table maps fog node actions to expected rewards
  based on latency, energy, and reliability.

  Q-update rule:
    Q(j) ← Q(j) + α · [R(j) + γ · max Q − Q(j)]

  Reward function:
    R(j) = −(w_lat · T_est(j) + w_eng · E_est(j)
            + w_rel · (1 − Trust(j)))

  Training: R rounds × I iterations per round.
  Complexity: O(R · I · |F| · T),  Communication: O(R · I · d)

Characteristics vs Spider++:
  - Multi-round RL training (not single-pass)
  - Three-factor reward (latency + energy + reliability)
  - No EPC memory awareness
  - No enclave-level scheduling
  - No computation reuse awareness
  - Distributed model (each region has own Q-table)
"""

import sys
import config
import time
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from utils.dataset_loader import DataLoader

# Q-learning hyperparameters (per paper [39])
ALPHA_LR     = 0.1      # Learning rate
GAMMA_DISC   = 0.9      # Discount factor
EPSILON      = 0.2      # ε-greedy exploration rate
NUM_ROUNDS   = 5        # R: training rounds
NUM_ITERS    = 3        # I: iterations per round

# Reward weight factors
W_LATENCY    = 0.5      # Weight for latency in reward
W_ENERGY     = 0.3      # Weight for energy in reward
W_RELIABILITY = 0.2     # Weight for reliability in reward


def compute_reward(fog_node):
    """
    DIST reward function per paper [39]:
    R(j) = -(w_lat · T_est + w_eng · E_est + w_rel · (1 − Trust))

    Latency estimate: (queue + 1) / service_rate + network_latency
    Energy proxy:     queue_depth × base_energy (proportional to load)
    Reliability:      trust_score (higher = more reliable)
    """
    enclaves = fog_node["enclaves"]
    total_q = sum(e["queue_length"] for e in enclaves)
    avg_rate = sum(e["service_rate"] for e in enclaves) / max(1, len(enclaves))

    # Latency estimate
    T_est = fog_node.get("network_latency", 1.0) + (total_q + 1) / max(1, avg_rate)

    # Energy proxy: linear with queue depth (more tasks = more energy)
    E_est = total_q * 0.1 + 0.5  # base + load-proportional

    # Reliability
    trust = fog_node.get("trust_score", 0.9)
    reliability_penalty = 1.0 - trust

    return -(W_LATENCY * T_est
             + W_ENERGY * E_est
             + W_RELIABILITY * reliability_penalty)


def train_q_table(fog_nodes):
    """
    Train Q-table using iterative Q-learning per paper [39].
    Q(j) ← Q(j) + α · [R(j) + γ · max(Q) − Q(j)]
    R rounds × I iterations.
    """
    num_nodes = len(fog_nodes)
    Q = np.zeros(num_nodes, dtype=np.float64)

    for r in range(NUM_ROUNDS):
        for i in range(NUM_ITERS):
            for j in range(num_nodes):
                reward = compute_reward(fog_nodes[j])
                Q[j] = Q[j] + ALPHA_LR * (reward + GAMMA_DISC * np.max(Q) - Q[j])

    return Q


def run_phase4_ref39():
    print("=" * 60)
    print("PQ-SPIDER Phase IV: DIST RL-Based Scheduling (Ref [39])")
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
    num_nodes = len(fog_nodes)
    print(f"  -> Scheduling {len(packets)} packets across "
          f"{num_nodes} fog nodes (DIST: Q-learning, "
          f"R={NUM_ROUNDS}, I={NUM_ITERS}).")

    metrics = {
        "node_scoring_per_pkt":    [],
        "assignments":             [],
        "total_scheduler_latency": 0,
        "rejected_count":          0,
    }

    start = time.perf_counter()

    for p in packets:
        t0 = time.perf_counter()

        # Train Q-table from current node states (R × I × |F| iterations)
        Q = train_q_table(fog_nodes)

        # ε-greedy action selection
        if np.random.random() < EPSILON:
            # Explore: random node
            target_idx = np.random.randint(num_nodes)
        else:
            # Exploit: highest Q-value (best expected reward)
            target_idx = int(np.argmax(Q))

        chosen_node = fog_nodes[target_idx]

        metrics["node_scoring_per_pkt"].append(
            (time.perf_counter() - t0) * 1000)

        # DIST has no enclave-level scheduling — pick min-queue enclave
        chosen_enc = min(chosen_node["enclaves"],
                         key=lambda e: e["queue_length"])

        # Update state (no admission control in paper [39])
        chosen_enc["queue_length"] += 1
        if chosen_enc["epc_availability"] >= config.PACKET_EPC_BYTES:
            chosen_enc["epc_availability"] -= config.PACKET_EPC_BYTES

        metrics["assignments"].append({
            "device":       p["device_id"],
            "fog_node":     chosen_node["id"],
            "enclave":      chosen_enc["id"],
            "node_score":   round(float(Q[target_idx]), 4),
            "enclave_score": 0,
        })

    metrics["total_scheduler_latency"] = (time.perf_counter() - start) * 1000

    # Load distribution
    per_node_load = {}
    for a in metrics["assignments"]:
        per_node_load[a["fog_node"]] = per_node_load.get(
            a["fog_node"], 0) + 1

    loader.save_metrics(Path(__file__).parent, metrics,
                        filename="ref39_metrics.json")
    loader.save_data(Path(__file__).parent, "ref39_schedule.json", {
        "assignments": metrics["assignments"],
    })

    avg_node = (sum(metrics["node_scoring_per_pkt"])
                / max(1, len(packets)))
    print(f"\n  DIST Q-learning scoring (avg/pkt): {avg_node:.4f} ms")
    print(f"  Assignments: {len(metrics['assignments'])} / "
          f"Rejected: {metrics['rejected_count']}")
    print(f"  Per-node load distribution:")
    for nid, count in sorted(per_node_load.items()):
        print(f"    Node {nid}: {count} packets")
    print("\n" + "=" * 60)
    print(f"Phase IV (Ref [39] DIST) Finished. Total: "
          f"{metrics['total_scheduler_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase4_ref39()
