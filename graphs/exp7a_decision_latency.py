"""
Experiment 7 — Scenario 1: Load-Balancing Decision Latency
============================================================

Measures ACTUAL wall-clock time of each algorithm's full scheduling
decision pipeline as the number of fog nodes increases from 5 to 50.

Each algorithm's decision process reflects its paper-specified complexity
(Table IV) by calling the real scoring functions with architecturally
faithful overhead:

  Ref[22]:  choose_node() → O(|F|)
            Simple OLB scan. Just scores all nodes once.

  Spider:   choose_node() + choose_enclave() → O(|F| + Σm_j)
            Scores all nodes, then scores enclaves on the selected node.

  Ref[37]:  choose_node() + SDN coordination → O(|MC|² + |MC| + P)
            Scores all nodes, then performs pairwise capacity coordination
            (SDN controller must compare all MC pairs for offloading).

  Ref[39]:  choose_node() × I iterations → O(R·I·|F|)
            Runs the scoring function I times to simulate RL convergence
            (DIST paper Section IV.C: α=0.1, γ=0.95, I≈5 iterations).

No hardcoded latency constants — all timing comes from actual execution.
"""

import time
from typing import Dict, List

import numpy as np

import config
from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR,
)
from phase4_load_balance.inter_node import (
    choose_node, _score_ref22, _score_ref37, _score_ref39, _score_spider,
)
from phase4_load_balance.intra_node import (
    choose_enclave, _enclave_score_eq46,
)
from phase4_load_balance.models import FogNode, Enclave, clone_nodes, clone_enclaves
from phase4_load_balance.generators import generate_tasks, generate_nodes, generate_enclaves


# RL convergence iterations for Ref[39] (from paper Section IV.C)
REF39_RL_ITERATIONS = 5


def _sdn_coordination(nodes: List[FogNode], task, rng: np.random.Generator) -> None:
    """Ref[37] SDN coordination overhead: O(|F|²) pairwise capacity check.

    The SDN controller in Jasim & Al-Raweshidy's scheme must compare
    all pairs of mobile controllers to find the best offloading target
    (Paper Fig. 2, 7 hierarchical scenarios). Each pair requires:
      1. Capacity aggregation (TEE + REE rates)
      2. Load ratio computation
      3. Offloading feasibility check (t_offload vs t_local, Eq 8)
      4. Routing cost estimation (network_ms between pair)
    """
    import math
    n = len(nodes)
    best_pair_score = float('inf')
    for i in range(n):
        for j in range(i + 1, n):
            # Per-pair SDN operations (realistic controller work)
            cap_i = nodes[i].tee_rate + nodes[i].ree_rate
            cap_j = nodes[j].tee_rate + nodes[j].ree_rate
            load_ratio_i = nodes[i].assigned_count / max(1.0, cap_i)
            load_ratio_j = nodes[j].assigned_count / max(1.0, cap_j)
            # Offloading feasibility: Eq 8 binary decision
            net_cost = nodes[i].network_ms + nodes[j].network_ms
            t_offload = net_cost + task.tee_work / max(0.01, cap_j)
            t_local = task.tee_work / max(0.01, cap_i)
            feasible = t_offload < t_local
            # Routing cost estimation (log-barrier for capacity)
            route_score = net_cost + math.log1p(load_ratio_i + load_ratio_j)
            if feasible and route_score < best_pair_score:
                best_pair_score = route_score


def _measure_full_decision(
    nodes: List[FogNode],
    enclaves_per_node: List[List[Enclave]],
    tasks,
    algorithm: str,
    rng_seed: int,
    warmup: int = 50,
) -> float:
    """
    Measure the average FULL decision latency (µs) for one algorithm.

    Each algorithm calls the real scoring functions with architecturally
    faithful overhead reflecting its paper complexity class.
    """
    rng = np.random.default_rng(rng_seed)
    working_nodes = clone_nodes(nodes)
    working_enclaves = [clone_enclaves(e) for e in enclaves_per_node]
    epc_req = config.PACKET_EPC_BYTES * 28

    elapsed_ns: list = []

    for i, task in enumerate(tasks):
        t0 = time.perf_counter_ns()

        if algorithm == "Ref[22]":
            # O(|F|): simple linear scan — just choose_node
            choose_node(working_nodes, task, "Ref[22]", rng)

        elif algorithm == "Spider (Ours)":
            # O(|F| + Σm_j): fog scoring + enclave scoring
            selected = choose_node(working_nodes, task, "Spider (Ours)", rng)
            # Also score enclaves on the selected node (Level 2)
            node_encs = working_enclaves[selected.node_id]
            choose_enclave(node_encs, i, task, epc_req, "Spider (Ours)", rng)

        elif algorithm == "Ref[37]":
            # O(|MC|² + |MC| + P): SDN coordination + scoring
            choose_node(working_nodes, task, "Ref[37]", rng)
            # Quadratic SDN pairwise capacity coordination
            _sdn_coordination(working_nodes, task, rng)

        elif algorithm == "Ref[39]":
            # O(R·I·|F|): run scoring I times (RL iterations)
            for _ in range(REF39_RL_ITERATIONS):
                choose_node(working_nodes, task, "Ref[39]", rng)

        t1 = time.perf_counter_ns()

        if i >= warmup:
            elapsed_ns.append(t1 - t0)

    return float(np.mean(elapsed_ns)) / 1000.0  # ns → µs


def graph7_decision_latency(rng: np.random.Generator) -> Dict[str, np.ndarray]:
    """Scenario 1: Decision latency vs number of fog nodes."""

    fog_counts = config.EXP7_SC1_FOG_COUNTS
    reps = config.EXP7_SC1_REPS
    n_tasks = config.EXP7_SC1_N_TASKS
    algorithms = ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]
    n_enclaves = getattr(config, 'EXP7_SC2_ENCLAVES_PER_FOG', 4)

    x = np.array(fog_counts)
    mean_series: Dict[str, np.ndarray] = {}
    std_series: Dict[str, np.ndarray] = {}

    for alg in algorithms:
        rep_values = []
        for rep in range(reps):
            vals = []
            for n in fog_counts:
                seed = GLOBAL_SEED + 70000 + 1000 * rep + 37 * n
                base_rng = np.random.default_rng(seed)

                tasks = generate_tasks(n_tasks, base_rng, offered_load=0.70)
                nodes = generate_nodes(n, heterogeneous=True, rng=base_rng)
                # Generate enclaves for each node (needed for Spider Level 2)
                enclaves_per_node = [
                    generate_enclaves(n_enclaves, np.random.default_rng(seed + nid))
                    for nid in range(n)
                ]

                lat_us = _measure_full_decision(
                    nodes, enclaves_per_node, tasks, alg, rng_seed=seed,
                )
                vals.append(lat_us)
            rep_values.append(np.array(vals))
        mean, std = summarize_runs(rep_values)
        mean_series[alg] = mean
        std_series[alg] = std

    # Save raw data
    save_csv(
        RAW_DIR / "graph7_decision_latency.csv",
        "Number of Fog Nodes", x, mean_series,
    )

    # Plot
    plot_lines(
        x,
        {k: (mean_series[k], std_series[k]) for k in algorithms},
        "",
        "Number of Fog Nodes",
        "Average Decision Latency (µs)",
        "graph7_decision_latency",
        ylim_bottom=0.0,
    )

    print("  → Scenario 1 decision latency summary (µs at 50 nodes):")
    for alg in algorithms:
        print(f"    {alg:20s}: {mean_series[alg][-1]:.1f} µs")

    return mean_series
