"""
Phase IV (Ref [39]): DIST — Distributed RL-Based Task Scheduling
=================================================================
E. Oustad, "DIST: Distributed Learning-Based Energy-Efficient and
Reliable Task Scheduling and Resource Allocation in Fog Computing,"
IEEE Trans. Services Computing, vol. 18, no. 3, pp. 1336-, 2025.

Algorithm (Algorithm 1, Sec. III-C):
  DIST uses a distributed Q-learning framework where each fog node
  maintains its own Q-table.  Three Q-tables are used:
    - Global Q-table:   group-level task scheduling
    - Regional Q-table: individual task assignment within regions
    - Energy Q-table:   DVFS-level management

  Q-update (Bellman equation):
    Q(s,a) ← Q(s,a) + α · [R + γ · max_a' Q(s',a') − Q(s,a)]

  Reward function (Eq. 16-17):
    R = Σ_{i ∈ scheduled} hasmissed_i × (−10 + w_i/100)
    where hasmissed_i = +1 if finished < deadline, −1 otherwise.

  Hyperparameters (from paper Sec. III-C):
    α = 0.1   (learning rate)
    γ = 0.95  (discount factor)
    ε: starts at 1.0, decays exponentially to 0.01

  Actions: (i) schedule a new task, (ii) idle, (iii) adjust DVFS.

  Implementation notes:
    - DVFS actions are simplified: we model energy states as a discrete
      factor that modifies service rate (DVFS level 0.7x, 1.0x, 1.3x),
      which is the paper's core idea of trading energy for performance.
    - Regional Q-tables are implemented per-node, with periodic
      aggregation (weighted average of non-zero entries) matching
      the paper's cooperative learning mechanism.
    - The exploration rate decays exponentially per the paper's spec.

Characteristics vs Spider:
  - Multi-round RL training (not single-pass)
  - Deadline-miss penalty reward function
  - Energy-aware via DVFS modelling
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

# Q-learning hyperparameters (per paper [39] Sec. III-C)
ALPHA_LR        = 0.1      # Learning rate (paper: α = 0.1)
GAMMA_DISC      = 0.95     # Discount factor (paper: γ = 0.95)
EPSILON_START   = 1.0      # Initial exploration rate (paper: starts at 1.0)
EPSILON_END     = 0.01     # Final exploration rate (paper: decays to 0.01)
EPSILON_DECAY   = 0.85     # Exponential decay factor per round
NUM_ROUNDS      = 5        # R: training rounds
NUM_ITERS       = 3        # I: iterations per round

# DVFS levels: paper models dynamic voltage/frequency scaling
# These represent fractional performance multipliers
DVFS_LEVELS = [0.7, 1.0, 1.3]


def compute_reward_dist(fog_node, task_deadline_slack):
    """
    DIST reward function per paper [39] Eq. 16-17:

    R = Σ hasmissed_i × (−10 + w_i/100)
    hasmissed_i = +1 if f_i < d_i (on-time), −1 otherwise

    We simulate a single-task view: the node's estimated finish time
    is compared against the task's deadline.
    """
    enclaves = fog_node["enclaves"]
    total_q = sum(e["queue_length"] for e in enclaves)
    total_rate = sum(e["service_rate"] for e in enclaves)

    # Estimated processing time including current queue
    est_proc = (total_q + 1) / max(1, total_rate)
    network_lat = fog_node.get("network_latency", 1.0)
    est_finish = est_proc + network_lat

    # Task weight (proportional to computational intensity)
    w_i = total_q * 10 + 50  # workload-proportional weight

    # Eq. 17: hasmissed = +1 if on-time, −1 if missed
    if est_finish < task_deadline_slack:
        hasmissed = 1    # On-time: positive contribution
    else:
        hasmissed = -1   # Missed: negative contribution

    # Eq. 16: R = hasmissed × (−10 + w_i/100)
    reward = hasmissed * (-10 + w_i / 100.0)

    return reward


def train_q_tables(fog_nodes, task_deadline_slack=10.0, epsilon=0.2):
    """
    Train distributed Q-tables per paper [39] Algorithm 1.

    Three Q-table layers:
      1. Global Q-table: aggregated across all nodes
      2. Regional Q-tables: per-node, for individual task assignment
      3. Energy Q-tables: per-node, for DVFS level selection

    Q(s,a) ← Q(s,a) + α · [R + γ · max_a'(Q(s',a')) − Q(s,a)]
    Training: R rounds × I iterations.
    """
    num_nodes = len(fog_nodes)
    num_dvfs = len(DVFS_LEVELS)

    # Regional Q-tables: one per node, indexed by node action
    regional_Q = np.zeros((num_nodes, num_nodes), dtype=np.float64)
    # Energy Q-tables: one per node, indexed by DVFS level
    energy_Q = np.zeros((num_nodes, num_dvfs), dtype=np.float64)

    for r in range(NUM_ROUNDS):
        for i in range(NUM_ITERS):
            for src_node in range(num_nodes):
                # --- Regional Q-table update ---
                # Evaluate each target node as a potential assignment
                for target in range(num_nodes):
                    reward = compute_reward_dist(
                        fog_nodes[target], task_deadline_slack)
                    regional_Q[src_node, target] = (
                        regional_Q[src_node, target]
                        + ALPHA_LR * (reward
                                      + GAMMA_DISC * np.max(regional_Q[src_node])
                                      - regional_Q[src_node, target])
                    )

                # --- Energy Q-table update ---
                # Evaluate DVFS levels for this node
                for dvfs_idx, dvfs_mult in enumerate(DVFS_LEVELS):
                    # Reward considers energy savings vs. deadline risk
                    base_reward = compute_reward_dist(
                        fog_nodes[src_node], task_deadline_slack)
                    # Lower DVFS = less energy but higher miss risk
                    energy_bonus = (1.0 - dvfs_mult) * 5.0  # energy saving bonus
                    perf_penalty = max(0, (1.0 - dvfs_mult)) * 8.0  # slowdown penalty
                    dvfs_reward = base_reward + energy_bonus - perf_penalty

                    energy_Q[src_node, dvfs_idx] = (
                        energy_Q[src_node, dvfs_idx]
                        + ALPHA_LR * (dvfs_reward
                                      + GAMMA_DISC * np.max(energy_Q[src_node])
                                      - energy_Q[src_node, dvfs_idx])
                    )

        # --- Cooperative aggregation across nodes ---
        # Paper: "The final Q-value for an action A in state S is
        #         calculated as a weighted average of the non-zero
        #         Q-values from multiple nodes."
        nonzero_mask = regional_Q != 0
        col_sums = nonzero_mask.sum(axis=0)
        col_sums[col_sums == 0] = 1
        global_Q = (regional_Q.sum(axis=0) / col_sums)

        # Broadcast global knowledge back to regional tables
        for src_node in range(num_nodes):
            for target in range(num_nodes):
                if regional_Q[src_node, target] == 0:
                    regional_Q[src_node, target] = global_Q[target] * 0.5

    # Final action selection: combine regional + energy Q-values
    # For each target node, the combined value considers both
    # the assignment quality and the DVFS optimality
    combined_Q = np.zeros(num_nodes, dtype=np.float64)
    for target in range(num_nodes):
        # Average regional Q across source nodes
        avg_regional = global_Q[target]
        # Best DVFS level for this target
        best_dvfs_q = np.max(energy_Q[target])
        combined_Q[target] = avg_regional + 0.3 * best_dvfs_q

    return combined_Q


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
          f"{num_nodes} fog nodes (DIST: distributed Q-learning, "
          f"α={ALPHA_LR}, γ={GAMMA_DISC}, "
          f"R={NUM_ROUNDS}, I={NUM_ITERS}).")

    metrics = {
        "node_scoring_per_pkt":    [],
        "assignments":             [],
        "total_scheduler_latency": 0,
        "rejected_count":          0,
    }

    start = time.perf_counter()

    # Exponential ε decay per paper [39]: starts at 1.0, decays to 0.01
    epsilon = EPSILON_START

    for pkt_idx, p in enumerate(packets):
        t0 = time.perf_counter()

        # Train distributed Q-tables from current node states
        # (R × I × |F| iterations per Bellman update)
        deadline_slack = p.get("deadline", time.time() + 10) - time.time()
        Q = train_q_tables(fog_nodes, task_deadline_slack=deadline_slack,
                           epsilon=epsilon)

        # ε-greedy action selection with exponential decay
        if np.random.random() < epsilon:
            # Explore: random node
            target_idx = np.random.randint(num_nodes)
        else:
            # Exploit: highest Q-value (best expected reward)
            target_idx = int(np.argmax(Q))

        # Decay ε exponentially (paper: 1.0 → 0.01)
        epsilon = max(EPSILON_END, epsilon * EPSILON_DECAY)

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
    print(f"  Hyperparameters: α={ALPHA_LR}, γ={GAMMA_DISC}, "
          f"ε={EPSILON_START}→{EPSILON_END} (decay={EPSILON_DECAY})")
    print(f"  DVFS levels: {DVFS_LEVELS}")
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
