"""
Intra-Node Enclave Scheduling for PQ-SPIDER
=============================================

Level 2 scheduling: selects which TEE enclave within a fog node
receives each task. Implements Spider (Eq 46) and two baselines
(Round-Robin, Least-Queue).
"""

from typing import List

import numpy as np

import config

from .params import SIMULATION_PARAMS
from .models import WorkloadTask, Enclave, clone_enclaves
from .generators import generate_tasks, _load_phase5_service_ms


def _enclave_score_eq46(
    enc: Enclave,
    task: WorkloadTask,
    epc_req: float,
    tau: float,
    z1: float, z2: float, z3: float, z4: float,
) -> float:
    """
    Spider EnclaveScore (Eq 46) — enhanced with actual completion estimate.

    Like the Level 1 scheduler (choose_node), we estimate when this enclave
    would actually finish the task, combining:
      - Eq 42: T_wait → actual queue delay (available_ms - arrival_ms)
      - Eq 43: P_epc → EPC pressure penalty
      - Eq 44: P_cont → contention from dynamic load
      - Eq 45: A_affin → workload affinity bonus (cache warm)
      + service time estimate: tee_work / service_rate
    """
    # Actual queue wait: how long until enclave is free
    queue_wait = max(0.0, enc.available_ms - task.arrival_ms)

    # Estimated service time on this enclave — use MEASURED Phase 5 base,
    # scaled by enclave rate (consistent with execute_on_enclave)
    base_ms = _load_phase5_service_ms()
    baseline_rate = config.MEASURED_BASELINE_RATE
    service_est = base_ms * (baseline_rate / max(0.01, enc.service_rate))

    # Contention estimate: world-switch cost per unit normalized load [A,D].
    # The scheduler uses the DETERMINISTIC estimate; actual execution adds
    # stochastic variance that the scheduler cannot perfectly predict.
    cont_per_unit = SIMULATION_PARAMS["contention_per_unit_ms"]
    norm_load = enc.queue_length / max(0.1, enc.service_rate)
    contention_cost = norm_load * cont_per_unit

    # Estimated completion delay
    T_wait = queue_wait + service_est + contention_cost

    # Eq 43: P_epc — granular EPC pressure (not just binary threshold)
    M_free = max(1.0, enc.epc_available)
    ratio = epc_req / M_free - tau
    P_epc = max(0.0, ratio) ** 2
    # EPC swap cost prediction: uses cited base from SIMULATION_PARAMS [B,C].
    # Scheduler predicts the MEAN; actual execution draws from a distribution.
    if enc.epc_available < epc_req:
        depletion = 1.0 - max(0.0, enc.epc_available) / max(1.0, enc.epc_total)
        epc_base = SIMULATION_PARAMS["epc_swap_base_ms"]
        P_epc += (0.5 + depletion) * epc_base

    # Eq 44: P_cont = world-switch contention + queue-balancing penalty.
    # 
    # CRITICAL: The queue_length term is what enables load balancing.
    # Previously: P_cont = contention + queue_length / service_rate
    #   → Ratio queue/rate is small (e.g., 1/0.4 = 2.5), making P_cont
    #     dominated by contention base. Spider would myopically pick
    #     the fastest enclave even when others were idle (JSQ optimal).
    #
    # Fixed: Add an explicit queue-imbalance term that scales with the
    # service-time of waiting tasks. This makes Spider behave like
    # Join-Shortest-Queue (JSQ, optimal under M/M/n) when EPC and rate
    # signals don't dominate.
    queue_penalty_ms = enc.queue_length * service_est  # waiting time for this task
    P_cont = enc.contention + queue_penalty_ms

    # Eq 45: A = graduated affinity bonus (0.0 to 1.0).
    # Previously this was binary (1.0 if recent_count > 0), making it
    # impossible to distinguish "barely warm" from "very warm" enclaves.
    # Now uses fractional affinity: warmer cache → larger bonus.
    # Window is config.ENCLAVE_AFFINITY_WINDOW (default 20).
    affinity_window = config.ENCLAVE_AFFINITY_WINDOW
    A_affin = min(1.0, enc.recent_count / max(1.0, affinity_window))

    return z1 * T_wait + z2 * P_epc + z3 * P_cont - z4 * A_affin


def choose_enclave(
    enclaves: List[Enclave],
    task_idx: int,
    task: WorkloadTask,
    epc_req: float,
    algorithm: str,
    rng: np.random.Generator,
) -> Enclave:
    """
    Intra-node enclave selection.

    Round-Robin:  blind cyclic rotation (ignores all state)
    Least-Queue:  picks enclave with shortest queue (ignores EPC/contention)
    Spider (Eq 46): full EnclaveScore with completion estimate + EPC + contention
    """

    if algorithm == "Round-Robin":
        return enclaves[task_idx % len(enclaves)]

    elif algorithm == "Least-Queue":
        return min(enclaves, key=lambda e: e.queue_length)

    elif algorithm == "Spider (Ours)":
        # Eq 49: Admission control — M_free >= alpha * M_req (alpha > 1)
        alpha_epc = config.ALPHA_EPC_SAFETY
        feasible = [e for e in enclaves if e.epc_available >= alpha_epc * epc_req]
        if not feasible:
            feasible = enclaves  # Graceful degradation if all overloaded

        best_enc = None
        best_score = float("inf")
        for e in feasible:
            sc = _enclave_score_eq46(
                e, task, epc_req,
                tau=0.5,   # Lower threshold for intra-node (smaller EPC per enclave)
                z1=config.Z1_ENC_WAIT,
                z2=config.Z2_ENC_EPC,
                z3=config.Z3_ENC_CONTENTION,
                z4=config.Z4_ENC_AFFIN,
            )
            if sc < best_score:
                best_score = sc
                best_enc = e
        return best_enc  # type: ignore[return-value]

    raise ValueError(f"Unknown algorithm: {algorithm}")


def execute_on_enclave(
    enc: Enclave,
    task: WorkloadTask,
    epc_req: float,
    rng: np.random.Generator,
) -> float:
    """
    Execute one task on chosen enclave and update its state.
    Returns latency (ms) from task arrival to completion.

    DECOUPLING NOTE: This execution model introduces stochastic factors
    that the scheduler (_enclave_score_eq46) cannot perfectly predict:
    1. Contention has ±30% lognormal variance (unpredictable cache state)
    2. EPC swap cost depends on task crypto_intensity (scheduler only
       knows the mean) and has ±20% lognormal variance
    3. OS scheduling jitter (exponential, unpredictable)
    This ensures Spider makes GOOD BUT IMPERFECT predictions, like a
    real scheduler operating on stale/noisy telemetry.
    """
    arrival = task.arrival_ms
    start = max(arrival, enc.available_ms)

    # Service time from Phase 5 measured fog latency (56.35ms baseline) [A],
    # scaled by enclave heterogeneity: fast enclaves finish faster.
    base_ms = _load_phase5_service_ms()
    baseline_rate = config.MEASURED_BASELINE_RATE
    rate_ratio = baseline_rate / max(0.01, enc.service_rate)
    service_ms = base_ms * rate_ratio * float(rng.lognormal(0.0, 0.06))

    # Contention overhead [A,D]: world-switch cost per context switch.
    # Base cost from SIMULATION_PARAMS, but actual overhead varies ±30%
    # due to unpredictable cache/TLB state — scheduler cannot predict this.
    if enc.queue_length > 0:
        cont_per_unit = SIMULATION_PARAMS["contention_per_unit_ms"]
        norm_load = enc.queue_length / max(0.1, enc.service_rate)
        service_ms += norm_load * cont_per_unit * float(rng.lognormal(0.0, 0.25))

    # EPC swap penalty [B,C]: derived from SGX page-fault cycle counts.
    # Actual cost depends on task-specific crypto working set size
    # (crypto_intensity) and has hardware variance — scheduler only
    # predicts the mean from SIMULATION_PARAMS.
    if enc.epc_available < epc_req:
        depletion = 1.0 - max(0.0, enc.epc_available) / max(1.0, enc.epc_total)
        swap_lo, swap_hi = SIMULATION_PARAMS["epc_swap_range"]
        # Task-dependent: heavier crypto tasks cause more page faults
        task_factor = 1.0 + 0.3 * task.crypto_intensity / 30.0
        service_ms += float(rng.uniform(swap_lo, swap_hi)) * (0.5 + depletion) * task_factor
        
    # ALWAYS deduct EPC to correctly track overbooking.
    # The enclave's available memory will go negative, indicating heavy swapping,
    # until tasks finish and _drain_queues returns the memory.
    enc.epc_available -= epc_req
    
    # OS scheduling jitter: unpredictable Linux CFS delays that no
    # scheduler can anticipate. Exponential distribution, mean ~0.8ms.
    service_ms += float(rng.exponential(0.8))

    finish = start + service_ms

    # Track this task's exact finish time for accurate drain
    enc._finish_times.append(finish)
    enc.queue_length = len(enc._finish_times)
    enc.available_ms = finish
    enc.contention = enc.queue_length / max(1.0, enc.service_rate)
    # Affinity tracking: count tasks within a sliding "warm cache" window.
    # Without this cap, recent_count grows unbounded and every enclave
    # ends up with recent_count > 0, neutralizing the A_affin bonus.
    # Cap defined in config.ENCLAVE_AFFINITY_WINDOW (default 20).
    affinity_window = config.ENCLAVE_AFFINITY_WINDOW
    enc.recent_count = min(affinity_window, enc.recent_count + 1)

    return float(finish - arrival)


def _drain_queues(enclaves: List[Enclave], current_ms: float, epc_per_task: float = 0.0) -> None:
    """
    Drain completed tasks from enclave queues based on current time.
    Reclaims EPC memory from tasks that have finished processing.

    Uses explicit per-task finish times for exact tracking.  Previous
    proportional estimate had a mathematical bug (always evaluated to
    false), so queues never partially drained.
    """
    for enc in enclaves:
        if not enc._finish_times:
            # Idle enclave: cache cools down over time
            if enc.recent_count > 0:
                enc.recent_count = max(0, enc.recent_count - 1)
            continue
        # Remove all tasks whose finish time <= current_ms
        before = len(enc._finish_times)
        enc._finish_times = [t for t in enc._finish_times if t > current_ms]
        completed = before - len(enc._finish_times)
        if completed > 0:
            enc.queue_length = len(enc._finish_times)
            enc.contention = enc.queue_length / max(1.0, enc.service_rate)
            if epc_per_task > 0:
                enc.epc_available = min(enc.epc_total,
                                        enc.epc_available + completed * epc_per_task)
            # Cache cools as tasks finish — affinity decays with completions
            enc.recent_count = max(0, enc.recent_count - completed)
        if enc.queue_length == 0:
            enc.contention = 0.0
            # Update available_ms when fully drained
            enc.available_ms = min(enc.available_ms, current_ms)


def simulate_intra_node(
    n_tasks: int,
    algorithm: str,
    base_enclaves: List[Enclave],
    seed: int,
) -> float:
    """
    Run one intra-node scheduling experiment.
    All algorithms get same task stream + same initial enclave state.
    """

    alg_offset = {"Round-Robin": 7, "Least-Queue": 19, "Spider (Ours)": 41}[algorithm]
    base_rng = np.random.default_rng(seed)
    rng = np.random.default_rng(seed + alg_offset)

    tasks = generate_tasks(
        n_tasks, base_rng,
        offered_load=config.INTRA_NODE_OFFERED_LOAD,
    )
    enclaves = clone_enclaves(base_enclaves)
    epc_req = config.PACKET_EPC_BYTES * 28

    latencies = []
    for i, task in enumerate(tasks):
        _drain_queues(enclaves, task.arrival_ms, epc_per_task=epc_req)
        enc = choose_enclave(enclaves, i, task, epc_req, algorithm, rng)
        lat = execute_on_enclave(enc, task, epc_req, rng)
        latencies.append(lat)

    arr = np.array(latencies)
    lo, hi = np.percentile(arr, [2, 98])
    return float(arr[(arr >= lo) & (arr <= hi)].mean())
