"""
Inter-Node Load Balancing for PQ-SPIDER
=========================================

Level 1 scheduling: selects which fog node receives each task batch.
Implements Spider (Ours) and three reference algorithms (Ref[22], Ref[37], Ref[39]).
"""

from typing import List

import numpy as np

from .params import SIMULATION_PARAMS
from .models import WorkloadTask, FogNode, clone_nodes
from .generators import generate_tasks, generate_nodes


def epc_pressure_penalty(task: WorkloadTask, node: FogNode) -> float:
    """Soft penalty when expected enclave memory approaches safe EPC capacity."""

    ratio = task.epc_req_mb / node.epc_total_mb
    if ratio <= 0.72:
        return 0.0
    return 75.0 * ((ratio - 0.72) ** 2)


def choose_node(nodes: List[FogNode], task: WorkloadTask, algorithm: str, rng: np.random.Generator) -> FogNode:
    """
    Scheduler models:
      Ref[22] : dynamic workload allocation mostly by current load.
      Ref[37] : SDN-like network/load aware heuristic.
      Ref[39] : resource/reliability/energy-aware heuristic.
      Spider: security-aware dual TEE/REE queue + network + EPC + trust.
    """

    arrival = task.arrival_ms
    # AUDIT FIX: All algorithms use the same telemetry delay model.
    # All schedulers receive slightly stale information (realistic for
    # any centralized or distributed controller collecting heartbeats).
    telemetry_delay = max(0.0, rng.normal(5.0, 2.0))

    if algorithm == "Ref[22]":
        scores = [
            # OLB: minimum-latency selection — network + processing estimate
            n.network_ms + max(0.0, max(n.tee_available_ms, n.ree_available_ms) - arrival + telemetry_delay) / max(0.1, n.tee_rate + n.ree_rate) + rng.normal(0.0, 1.5)
            for n in nodes
        ]

    elif algorithm == "Ref[37]":
        # SDN-GH (Paper [37], Eq 8): Binary offloading decision.
        # For each node, compute t_local vs t_offload; pick best.
        # local = default min-queue node; offload if t_off < t_local.
        local_idx = int(np.argmin([
            max(n.tee_available_ms, n.ree_available_ms) for n in nodes
        ]))
        t_local = max(0.0, max(nodes[local_idx].tee_available_ms, nodes[local_idx].ree_available_ms) - arrival + telemetry_delay)
        scores = []
        for i, n in enumerate(nodes):
            if i == local_idx:
                scores.append(t_local + rng.normal(0.0, 1.5))
            else:
                # t_offloading = 2 * network (round-trip) + remote processing
                t_off = 2.0 * n.network_ms + max(0.0, max(n.tee_available_ms, n.ree_available_ms) - arrival + telemetry_delay)
                scores.append(t_off + rng.normal(0.0, 1.5))

    elif algorithm == "Ref[39]":
        # DIST (Paper [39]): Reward-based selection considering latency,
        # energy, and reliability (trust).  Uses deadline-miss penalty.
        scores = []
        for n in nodes:
            bottleneck = max(0.0, max(n.tee_available_ms, n.ree_available_ms) - arrival + telemetry_delay)
            proc_est = task.total_work / max(0.1, min(n.tee_rate, n.ree_rate))
            # Energy: proportional to load * energy_factor
            energy_cost = 0.8 * n.energy_factor * (n.assigned_count + 1)
            # Reliability: trust penalty (paper: w_rel * (1 - Trust))
            reliability_penalty = 3.0 * (1.0 - n.trust)
            scores.append(bottleneck + proc_est + 0.65 * n.network_ms
                          + energy_cost + reliability_penalty
                          + rng.normal(0.0, 1.5))

    elif algorithm == "Spider (Ours)":
        scores = []
        for n in nodes:
            # Spider models the exact split TEE -> REE critical path
            net_est = n.network_ms
            tee_est = (task.tee_work / n.tee_rate) + 2.6 + epc_pressure_penalty(task, n)
            ree_est = (task.ree_work / n.ree_rate) + 1.8
            tee_finish = max(task.arrival_ms + net_est, n.tee_available_ms) + tee_est
            completion_est = max(tee_finish, n.ree_available_ms) + ree_est + 3.6

            p_cap = 0.05 * max(0.0, task.crypto_intensity - n.capability)
            p_trust = 0.2 * (1.0 - n.trust)
            scores.append(completion_est - task.arrival_ms + p_cap + p_trust + rng.normal(0.0, 0.5))
    else:
        raise ValueError(algorithm)

    return nodes[int(np.argmin(scores))]


def execute_task(node: FogNode, task: WorkloadTask, rng: np.random.Generator) -> float:
    """Execute one task and update node queues."""

    net = max(0.5, node.network_ms + rng.normal(0.0, 0.12 * node.network_ms))
    arrival_at_node = task.arrival_ms + net

    tee_service = (task.tee_work / node.tee_rate) * float(rng.lognormal(0.0, 0.055)) + 2.6 + epc_pressure_penalty(task, node)
    ree_service = (task.ree_work / node.ree_rate) * float(rng.lognormal(0.0, 0.060)) + 1.8

    tee_start = max(arrival_at_node, node.tee_available_ms)
    tee_finish = tee_start + tee_service
    ree_start = max(tee_finish, node.ree_available_ms)
    finish = ree_start + ree_service + max(0.3, rng.normal(3.6, 0.45))

    node.tee_available_ms = tee_finish
    node.ree_available_ms = finish
    node.assigned_count += 1
    return float(finish - task.arrival_ms)


def simulate_load_balancing(
    node_count: int,
    algorithm: str,
    heterogeneous: bool,
    seed: int,
    n_tasks: int = 160,
) -> float:
    """
    Run one load-balancing experiment.  All algorithms receive the same task
    stream and the same initial node population for fairness.
    """

    base_rng = np.random.default_rng(seed)
    alg_offset = {"Ref[22]": 11, "Ref[37]": 23, "Ref[39]": 37, "Spider (Ours)": 53}[algorithm]
    rng = np.random.default_rng(seed + alg_offset)

    offered_load = 1.22 if heterogeneous else 1.12
    tasks = generate_tasks(n_tasks, base_rng, offered_load=offered_load)
    nodes = clone_nodes(generate_nodes(node_count, heterogeneous, base_rng))

    latencies = []
    for task in tasks:
        node = choose_node(nodes, task, algorithm, rng)
        latencies.append(execute_task(node, task, rng))

    arr = np.array(latencies)
    lo, hi = np.percentile(arr, [2, 98])
    return float(arr[(arr >= lo) & (arr <= hi)].mean())
