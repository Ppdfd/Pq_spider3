"""
Graph 8: Recovery Latency vs Number of Fog Nodes
=================================================
PQ-SPIDER2 Section VII-C: Fault-Tolerance and Secure Recovery Evaluation

Dynamic discrete-event simulation that exercises ALL Section V equations:
  Eq 117-119 : partition_into_groups() — group partitioning
  Eq 120     : generate_heartbeat()    — authenticated heartbeat
  Eq 121-122 : check_heartbeat_timeout() — elapsed interval / suspicious check
  Eq 123     : quorum_failure_detection() + detect_failures() — quorum confirm
  Eq 124     : DelegationCapsule.create() — secure state transfer
  Eq 125     : select_recovery_node()  — SpiderScore recovery selection

Each strategy shares the same task stream, node population, failure set,
and execution model. Metrics emerge from the simulation dynamics.
"""

from typing import Dict, List, Tuple, Set
from dataclasses import dataclass

import numpy as np

import config
from utils.eval_utils import summarize_runs, save_csv, plot_lines, RAW_DIR

from phase4_load_balance.params import SIMULATION_PARAMS
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import FogNode, WorkloadTask, clone_nodes
from phase4_load_balance.failure_detection import (
    FogNodeState,
    MonitoringGroup,
    DelegationCapsule,
    partition_into_groups,
    generate_heartbeat,
    check_heartbeat_timeout,
    quorum_failure_detection,
    detect_failures,
    select_recovery_node,
)


# ═══════════════════════════════════════════════════════════════════════
# Shared execution model
# ═══════════════════════════════════════════════════════════════════════

def _execute_recovery_task(
    node: FogNode,
    task: WorkloadTask,
    restart_fraction: float,
    detection_delay_ms: float,
    rng: np.random.Generator,
) -> float:
    """Execute a recovery task on the selected node.

    Uses the same TEE→REE split-path execution model as Phase IV
    inter_node.execute_task for fairness across all strategies.

    Returns recovery_latency_ms (time from detection to task completion).
    """
    net = max(0.5, node.network_ms + rng.normal(0.0, 0.12 * node.network_ms))

    tee_service = (
        task.tee_work * restart_fraction / max(0.1, node.tee_rate)
    ) * float(rng.lognormal(0.0, 0.055)) + SIMULATION_PARAMS["tee_startup_ms"]

    ree_service = (
        task.ree_work * restart_fraction / max(0.1, node.ree_rate)
    ) * float(rng.lognormal(0.0, 0.060)) + SIMULATION_PARAMS["ree_startup_ms"]

    tee_start = max(detection_delay_ms + net, node.tee_available_ms)
    tee_finish = tee_start + tee_service
    ree_start = max(tee_finish, node.ree_available_ms)
    finish = ree_start + ree_service + max(
        0.3, rng.normal(SIMULATION_PARAMS["finalization_ms"], 0.45)
    )

    # Update node queues
    node.tee_available_ms = tee_finish
    node.ree_available_ms = finish
    node.assigned_count += 1

    return float(finish - detection_delay_ms)


def _assign_tasks_to_nodes(
    tasks: List[WorkloadTask],
    n_nodes: int,
    rng: np.random.Generator,
) -> List[int]:
    """Assign each task to a home node. Returns list of node indices."""
    assignments = list(range(len(tasks)))
    for i in range(len(assignments)):
        assignments[i] = i % n_nodes
    # Shuffle for realistic distribution
    rng.shuffle(assignments)
    return assignments


# ═══════════════════════════════════════════════════════════════════════
# Dynamic heartbeat simulation
# ═══════════════════════════════════════════════════════════════════════

def _run_heartbeat_simulation(
    states: List[FogNodeState],
    failed_set: Set[int],
    strategy: str,
    rng: np.random.Generator,
) -> Tuple[float, List[int], List[int]]:
    """
    Simulate heartbeat exchange and failure detection over time.

    For Spider-FT:
      - Eq 117-119: partition_into_groups()
      - Eq 120: generate_heartbeat() — each alive node sends authenticated heartbeats
      - Eq 121-122: check_heartbeat_timeout() — elapsed interval check
      - Eq 123: detect_failures() → quorum_failure_detection() — quorum confirm

    For baselines (centralized):
      - All nodes report to central monitor (extra network hop)
      - Simple timeout check (Eq 122 only, NO quorum Eq 123)
      - Higher network jitter → more false positives

    Returns:
      (detection_time_ms, detected_node_ids, false_positive_node_ids)
    """
    tau_h = config.HEARTBEAT_TIMEOUT_MS
    heartbeat_interval = 10.0  # ms between heartbeat rounds
    max_rounds = 30

    detected_ids: List[int] = []
    false_positive_ids: List[int] = []
    detection_time = max_rounds * heartbeat_interval  # default: no detection

    if strategy == "Spider-FT (Ours)":
        # ── Eq 117-119: Group partitioning ──
        groups = partition_into_groups(states)

        for round_num in range(1, max_rounds + 1):
            current_ms = round_num * heartbeat_interval

            # ── Eq 120: Authenticated heartbeat exchange ──
            # Alive nodes send heartbeats to group peers.
            # Failed nodes just stop sending — the monitor does NOT
            # know they are dead yet (that's what detection discovers).
            for s in states:
                if s.node_id in failed_set:
                    # Failed: heartbeat stays stale (never updated)
                    continue
                # Generate authenticated heartbeat (Eq 120)
                hb = generate_heartbeat(s, current_ms)
                # Intra-group delivery: low jitter (peers are colocated)
                delivery_jitter = abs(rng.normal(0.0, 1.5))
                s.last_heartbeat_ms = current_ms - delivery_jitter
                s.epoch += 1

            # ── Eq 121-123: Group-based detection with quorum ──
            newly_detected = detect_failures(groups, current_ms, tau_h)
            if newly_detected:
                detection_time = current_ms
                for nid in newly_detected:
                    if nid in failed_set:
                        detected_ids.append(nid)
                    else:
                        false_positive_ids.append(nid)
                break  # First detection triggers recovery

    else:
        # ── Baselines: Centralized timeout detection (no quorum) ──
        extra_delay = config.CENTRALIZED_EXTRA_DELAY_MS

        for round_num in range(1, max_rounds + 1):
            current_ms = round_num * heartbeat_interval

            for s in states:
                if s.node_id in failed_set:
                    # Failed: heartbeat stays stale
                    continue
                # Centralized: higher jitter (extra hop to central monitor)
                base_jitter = abs(rng.normal(0.0, 3.5)) + extra_delay
                # 5% chance of network congestion spike
                if rng.random() < 0.05:
                    base_jitter += rng.uniform(30.0, 60.0)
                s.last_heartbeat_ms = current_ms - base_jitter

            # Central monitor checks EACH node individually (Eq 122 only)
            # NO quorum (Eq 123) — single timeout triggers declaration
            round_detected = []
            for s in states:
                if s.declared_failed:
                    continue
                # Eq 121-122: timeout check
                if check_heartbeat_timeout(s, current_ms, tau_h):
                    s.declared_failed = True
                    round_detected.append(s.node_id)

            if round_detected:
                detection_time = current_ms + extra_delay  # processing delay
                for nid in round_detected:
                    if nid in failed_set:
                        detected_ids.append(nid)
                    else:
                        false_positive_ids.append(nid)
                break

        # Add strategy-specific overhead
        if strategy == "Full Checkpoint":
            detection_time += config.CHECKPOINT_SYNC_OVERHEAD_MS

    return detection_time, detected_ids, false_positive_ids


# ═══════════════════════════════════════════════════════════════════════
# Strategy-specific recovery
# ═══════════════════════════════════════════════════════════════════════

def _simulate_no_ft(tasks, assignments, failed_set):
    """No Fault-Tolerance: orphaned workloads are dropped."""
    n_orphaned = sum(1 for a in assignments if a in failed_set)
    return {
        "detection_time_ms": float("inf"),
        "recovery_latency_ms": 0.0,
        "task_completion_ratio": (len(tasks) - n_orphaned) / len(tasks),
        "control_messages": 0,
        "false_positive_rate": 0.0,
    }


def _recover_tasks(
    strategy: str,
    tasks: List[WorkloadTask],
    assignments: List[int],
    progress: List[float],
    failed_set: Set[int],
    states: List[FogNodeState],
    detection_time: float,
    false_positive_ids: List[int],
    rng: np.random.Generator,
) -> Tuple[int, float, int]:
    """
    Run recovery for orphaned tasks. Returns (completed, avg_latency, control_msgs).

    Spider-FT uses:
      - Eq 124: DelegationCapsule.create() — secure state transfer
      - Eq 125: select_recovery_node() — SpiderScore-based selection
      - Sub-batch restart (partial execution)

    Baselines use:
      - No delegation capsule → full batch restart
      - Simple node selection (random / round-robin / least-queue)
    """
    orphaned = [(i, tasks[i]) for i, a in enumerate(assignments) if a in failed_set]
    if not orphaned:
        return 0, 0.0, 0

    alive_states = [s for s in states if s.is_alive and not s.declared_failed]
    recovery_lats: List[float] = []
    completed = 0
    control_msgs = 0

    if strategy == "Spider-FT (Ours)":
        # ── Eq 124 + 125: Delegation capsule recovery ──
        for task_idx, task in orphaned:
            # Eq 124: Create authenticated delegation capsule
            # Preserves partial progress + cryptographic state
            capsule = DelegationCapsule.create(
                workload_id=f"batch_{task_idx}",
                sub_batch_id=f"sub_{task_idx}_0",
                progress=progress[task_idx],
                metadata={
                    "records": task.records,
                    "attrs": task.attrs,
                    "policy_depth": task.policy_depth,
                },
                partial_ct=b"\x00" * 32,  # simulated partial ciphertext
                timestamp_ms=detection_time,
                epoch=1,
                signing_key=b"spider_delegation_key",
            )
            control_msgs += 1  # capsule transfer message

            # Eq 125: F_recover = argmin SpiderScore(F_j, B_k)
            recovery_state = select_recovery_node(states, rng)
            if recovery_state is None:
                continue

            # Sub-batch recovery: resume from capsule.progress
            restart_fraction = max(0.05, 1.0 - capsule.progress)
            lat = _execute_recovery_task(
                recovery_state.fog_node, task,
                restart_fraction=restart_fraction,
                detection_delay_ms=detection_time,
                rng=rng,
            )
            recovery_lats.append(lat)
            if lat <= task.deadline_ms:
                completed += 1

    elif strategy == "Centralized HB":
        # Random alive node, full batch restart, no delegation
        for _, task in orphaned:
            if not alive_states:
                break
            node = alive_states[int(rng.integers(0, len(alive_states)))].fog_node
            lat = _execute_recovery_task(
                node, task, restart_fraction=1.0,
                detection_delay_ms=detection_time, rng=rng,
            )
            recovery_lats.append(lat)
            if lat <= task.deadline_ms:
                completed += 1
        control_msgs = len(states)  # O(N) per heartbeat round

    elif strategy == "Full Checkpoint":
        # Random alive node, resume from checkpoint (partial restart)
        for _, task in orphaned:
            if not alive_states:
                break
            node = alive_states[int(rng.integers(0, len(alive_states)))].fog_node
            restart_frac = max(0.1, 1.0 - config.G8_CHECKPOINT_PROGRESS
                               + rng.uniform(-0.1, 0.1))
            lat = _execute_recovery_task(
                node, task, restart_fraction=restart_frac,
                detection_delay_ms=detection_time, rng=rng,
            )
            recovery_lats.append(lat)
            if lat <= task.deadline_ms:
                completed += 1
        control_msgs = len(states) * 3  # O(N × state_size) per checkpoint

    elif strategy == "Round-Robin":
        # Cyclic node selection, full restart
        for idx, (_, task) in enumerate(orphaned):
            if not alive_states:
                break
            node = alive_states[idx % len(alive_states)].fog_node
            lat = _execute_recovery_task(
                node, task, restart_fraction=1.0,
                detection_delay_ms=detection_time, rng=rng,
            )
            recovery_lats.append(lat)
            if lat <= task.deadline_ms:
                completed += 1
        control_msgs = len(states)

    elif strategy == "Least-Queue":
        # Shortest queue node, full restart
        for _, task in orphaned:
            if not alive_states:
                break
            best = min(alive_states, key=lambda s: s.fog_node.assigned_count)
            node = best.fog_node
            lat = _execute_recovery_task(
                node, task, restart_fraction=1.0,
                detection_delay_ms=detection_time, rng=rng,
            )
            recovery_lats.append(lat)
            if lat <= task.deadline_ms:
                completed += 1
        control_msgs = len(states)

    avg_lat = float(np.mean(recovery_lats)) if recovery_lats else 0.0
    return completed, avg_lat, control_msgs


# ═══════════════════════════════════════════════════════════════════════
# Scenario runner
# ═══════════════════════════════════════════════════════════════════════

STRATEGY_NAMES = [
    "No FT",
    "Centralized HB",
    "Full Checkpoint",
    "Round-Robin",
    "Least-Queue",
    "Spider-FT (Ours)",
]


def _run_scenario(n_nodes: int, failure_rate: float, seed: int) -> Dict:
    """
    Run one complete failure scenario for all strategies.

    All strategies share:
      - Same task stream (generate_tasks with same seed)
      - Same node population (generate_nodes with same seed)
      - Same failure injection (same node indices)
      - Same execution model (_execute_recovery_task)
      - Same pre-failure task progress

    Detection and recovery differ per strategy.
    """
    n_tasks = config.G8_N_TASKS

    # Shared scenario inputs
    task_rng = np.random.default_rng(seed)
    tasks = generate_tasks(n_tasks, task_rng, offered_load=1.0)

    assign_rng = np.random.default_rng(seed + 777)
    assignments = _assign_tasks_to_nodes(tasks, n_nodes, assign_rng)

    progress_rng = np.random.default_rng(seed + 555)
    progress = [float(progress_rng.uniform(0.1, 0.85)) for _ in tasks]

    fail_rng = np.random.default_rng(seed + 999)
    n_failures = max(1, int(n_nodes * failure_rate))
    failed_indices = fail_rng.choice(n_nodes, size=n_failures, replace=False)
    failed_set = set(int(i) for i in failed_indices)

    results: Dict = {}

    for strategy in STRATEGY_NAMES:
        if strategy == "No FT":
            results[strategy] = _simulate_no_ft(tasks, assignments, failed_set)
            continue

        # Fresh nodes and states per strategy (identical initial conditions)
        fog_nodes = generate_nodes(n_nodes, heterogeneous=True,
                                   rng=np.random.default_rng(seed))
        states = [FogNodeState(fog_node=fn) for fn in fog_nodes]
        for s in states:
            s.last_heartbeat_ms = 0.0

        strat_rng = np.random.default_rng(seed + hash(strategy) % 10000)

        # ── Phase 1: Heartbeat simulation + detection ──
        detection_time, detected_ids, fp_ids = _run_heartbeat_simulation(
            states, failed_set, strategy, strat_rng,
        )

        # After detection: mark detected nodes as non-alive for recovery
        for s in states:
            if s.node_id in failed_set:
                s.is_alive = False

        # ── Phase 2: Recovery ──
        completed, avg_recovery_lat, control_msgs = _recover_tasks(
            strategy, tasks, assignments, progress, failed_set,
            states, detection_time, fp_ids, strat_rng,
        )

        # ── Metrics ──
        n_alive_tasks = sum(1 for a in assignments if a not in failed_set)
        total_completed = n_alive_tasks + completed
        n_healthy = len(states) - len(failed_set)
        fp_rate = len(fp_ids) / max(1, n_healthy)

        results[strategy] = {
            "detection_time_ms": detection_time,
            "recovery_latency_ms": avg_recovery_lat,
            "task_completion_ratio": total_completed / len(tasks),
            "control_messages": control_msgs,
            "false_positive_rate": fp_rate,
        }

    return results


# ═══════════════════════════════════════════════════════════════════════
# Graph 8 entry point
# ═══════════════════════════════════════════════════════════════════════

def graph8_recovery_latency(rng: np.random.Generator, reps: int = None):
    """Graph 8: Recovery Latency vs Number of Fog Nodes.

    Excludes 'No FT' (0ms recovery is misleading).
    Graph 9 includes all 6 strategies.
    """
    if reps is None:
        reps = config.G8_REPS
    fog_counts = np.array(config.G8_FOG_COUNTS)
    failure_rate = config.G8_FAILURE_RATE

    recovery_names = [n for n in STRATEGY_NAMES if n != "No FT"]
    all_runs = {name: [] for name in recovery_names}

    for rep in range(reps):
        per_baseline = {name: [] for name in recovery_names}
        for n_nodes in fog_counts:
            seed = int(rng.integers(0, 2**31)) + rep * 1000
            scenario = _run_scenario(int(n_nodes), failure_rate, seed)
            for name in recovery_names:
                per_baseline[name].append(scenario[name]["recovery_latency_ms"])
        for name in recovery_names:
            all_runs[name].append(np.array(per_baseline[name]))

    data = {}
    plot_data = {}
    for name in recovery_names:
        mean, std = summarize_runs(all_runs[name])
        data[name] = mean
        plot_data[name] = (mean, std)

    save_csv(RAW_DIR / "graph8_recovery_latency.csv",
             "Number of Fog Nodes", fog_counts, data)
    plot_lines(
        fog_counts, plot_data,
        "Graph 8: Recovery Latency vs Fog Nodes",
        "Number of Fog Nodes",
        "Recovery Latency (ms)",
        "graph8_recovery_latency",
    )
    return data
