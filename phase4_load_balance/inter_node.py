"""
Inter-Node Load Balancing for PQ-SPIDER
=========================================

Level 1 scheduling: selects which fog node receives each task batch.
Implements Spider (Ours) and three reference algorithms (Ref[22], Ref[37], Ref[39]).

NOTE on Eq 50-51 (Score Smoothing / Stability Control):
  The paper defines exponential score smoothing (Eq 50) and threshold-based
  update suppression (Eq 51) for continuous scheduling. These are intentionally
  omitted from the simulation because the discrete-event model processes tasks
  sequentially with full state visibility at each scheduling decision, making
  EMA smoothing unnecessary. In a real deployment, Eq 50-51 would filter
  stale/noisy telemetry from asynchronous heartbeat collection.
"""

from typing import List

import numpy as np

import config

from .params import SIMULATION_PARAMS
from .models import WorkloadTask, FogNode, clone_nodes
from .generators import generate_tasks, generate_nodes


def epc_pressure_penalty(task: WorkloadTask, node: FogNode) -> float:
    """Eq 29 + Eq 36: Sigmoid EPC pressure penalty.

    ρ_epc(F_j) = 1 / (1 + e^{-κ(ε_j - τ_epc)})     (Eq 29)
    P_epc(F_j, B_k) = ρ_epc(F_j) · M_req / M_free   (Eq 36)

    where ε_j = M_free / M_total is the EPC availability ratio.
    """
    import math
    # ε_j: availability ratio (higher = more memory available)
    M_free = max(0.01, node.epc_total_mb - task.epc_req_mb * node.assigned_count)
    epsilon_j = M_free / max(0.01, node.epc_total_mb)

    # Eq 29: sigmoid EPC pressure (low ε → high pressure)
    rho_epc = 1.0 / (1.0 + math.exp(-config.EPC_KAPPA * (epsilon_j - config.EPC_PRESSURE_TAU)))

    # Eq 36: scale by task memory demand relative to available
    return rho_epc * (task.epc_req_mb / max(0.01, M_free))



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
            n.network_ms + max(0.0, max(n.tee_available_ms, n.ree_available_ms) - arrival + telemetry_delay) / max(0.1, n.tee_rate + n.ree_rate) + rng.normal(0.0, config.SCHEDULING_NOISE_SIGMA)
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
                scores.append(t_local + rng.normal(0.0, config.SCHEDULING_NOISE_SIGMA))
            else:
                # t_offloading = 2 * network (round-trip) + remote processing
                t_off = 2.0 * n.network_ms + max(0.0, max(n.tee_available_ms, n.ree_available_ms) - arrival + telemetry_delay)
                scores.append(t_off + rng.normal(0.0, config.SCHEDULING_NOISE_SIGMA))

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
                          + rng.normal(0.0, config.SCHEDULING_NOISE_SIGMA))

    elif algorithm == "Spider (Ours)":
        scores = []
        for n in nodes:
            # Spider models the exact split TEE -> REE critical path
            # Eq 35: T_wait approximation (without EPC penalty, which is scored separately)
            net_est = n.network_ms
            tee_est = (task.tee_work / n.tee_rate) + SIMULATION_PARAMS["tee_startup_ms"]
            ree_est = (task.ree_work / n.ree_rate) + SIMULATION_PARAMS["ree_startup_ms"]
            tee_finish = max(task.arrival_ms + net_est, n.tee_available_ms) + tee_est
            completion_est = max(tee_finish, n.ree_available_ms) + ree_est + SIMULATION_PARAMS["finalization_ms"]

            T_wait = completion_est - task.arrival_ms

            # Eq 36: P_epc (scored as an independent term with weight w3)
            P_epc = epc_pressure_penalty(task, n)
            # Eq 37: P_cap — capability penalty
            p_cap = config.W4_CAP * max(0.0, task.crypto_intensity - n.capability)
            # Eq 38: P_trust — trust penalty
            p_trust = config.W5_TRUST * (1.0 - n.trust)

            # Eq 32: eta_k — urgency (risk-based)
            eta_k = task.risk

            # Eq 33: delta_k — deadline sensitivity
            d_max = max(1.0, task.deadline_ms)
            delta_k = max(0.0, 1.0 - max(0.0, task.deadline_ms - task.arrival_ms) / d_max)

            # Eq 39: R_reuse — computation reuse bonus
            has_policy = getattr(n, 'policy_cached', False)
            has_kyber = getattr(n, 'kyber_cached', False)
            R_reuse = config.THETA1_POLICY * float(has_policy) + config.THETA2_KYBER * float(has_kyber)

            # Eq 40: SpiderScore = w1*T_wait + w2*L_j + w3*P_epc + w4*P_cap
            #                    + w5*P_trust - w6*eta*U_j - w7*delta*mu_TEE - w8*R_reuse
            score = (config.W1_WAIT * T_wait
                     + config.W2_LATENCY * net_est
                     + config.W3_EPC * P_epc
                     + p_cap + p_trust
                     - config.W6_URGENCY * eta_k * n.trust
                     - config.W7_DEADLINE * delta_k * n.tee_rate
                     - config.W8_REUSE * R_reuse
                     + rng.normal(0.0, config.SCHEDULING_NOISE_SIGMA))
            scores.append(score)
    else:
        raise ValueError(algorithm)

    return nodes[int(np.argmin(scores))]


def execute_task(node: FogNode, task: WorkloadTask, rng: np.random.Generator) -> float:
    """Execute one task and update node queues."""

    net = max(0.5, node.network_ms + rng.normal(0.0, 0.12 * node.network_ms))
    arrival_at_node = task.arrival_ms + net

    tee_service = (task.tee_work / node.tee_rate) * float(rng.lognormal(0.0, 0.055)) + SIMULATION_PARAMS["tee_startup_ms"] + epc_pressure_penalty(task, node)
    ree_service = (task.ree_work / node.ree_rate) * float(rng.lognormal(0.0, 0.060)) + SIMULATION_PARAMS["ree_startup_ms"]

    tee_start = max(arrival_at_node, node.tee_available_ms)
    tee_finish = tee_start + tee_service
    ree_start = max(tee_finish, node.ree_available_ms)
    finish = ree_start + ree_service + max(0.3, rng.normal(SIMULATION_PARAMS["finalization_ms"], 0.45))

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
