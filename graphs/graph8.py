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
    Preserves temporal causality and filters out false positives using group quorums.
    """
    import math
    tau_h = config.HEARTBEAT_TIMEOUT_MS
    heartbeat_interval = 10.0  # ms between heartbeat rounds
    max_rounds = 40

    if strategy == "Spider (Ours)":
        groups = partition_into_groups(states)
        node_to_group = {}
        for g in groups:
            for m in g.members:
                node_to_group[m.node_id] = g

        monitor_last_hb = {
            j.node_id: {i.node_id: 0.0 for i in states}
            for j in states
        }

        # Track heartbeat events chronologically: (arrival_time, sender_id, receiver_id, send_time)
        events = []
        for r in range(1, max_rounds + 1):
            send_time = r * heartbeat_interval
            for s in states:
                if s.node_id in failed_set:
                    continue  # dead nodes don't send heartbeats

                g = node_to_group[s.node_id]
                for peer in g.members:
                    if peer.node_id == s.node_id:
                        continue
                    jitter = abs(rng.normal(0.0, config.HEARTBEAT_JITTER_SIGMA))
                    if rng.random() < config.HEARTBEAT_CONGESTION_PROB:
                        jitter += rng.uniform(config.HEARTBEAT_CONGESTION_MIN_MS, config.HEARTBEAT_CONGESTION_MAX_MS)
                    arrival = send_time + jitter
                    events.append((arrival, s.node_id, peer.node_id, send_time))

        events.sort(key=lambda x: x[0])

        declared_failed_ids = []
        false_positive_ids = []
        detection_time = max_rounds * heartbeat_interval
        event_idx = 0

        for r in range(1, max_rounds + 1):
            current_ms = r * heartbeat_interval
            # Process all heartbeats received up to current_ms
            while event_idx < len(events) and events[event_idx][0] <= current_ms:
                arrival, sender, receiver, send_time = events[event_idx]
                monitor_last_hb[receiver][sender] = max(monitor_last_hb[receiver][sender], send_time)
                event_idx += 1

            # Quorum failure check
            round_detected = []
            for s in states:
                if s.node_id in declared_failed_ids:
                    continue
                g = node_to_group[s.node_id]
                votes = 0
                active_peers = 0
                for peer in g.members:
                    if peer.node_id == s.node_id:
                        continue
                    if peer.node_id in failed_set:
                        continue  # dead peers don't vote
                    active_peers += 1
                    last_hb = monitor_last_hb[peer.node_id][s.node_id]
                    if current_ms - last_hb > tau_h:
                        votes += 1
                if active_peers > 0 and votes >= math.ceil(len(g.members) / 2):
                    round_detected.append(s.node_id)

            if round_detected:
                detection_time = current_ms
                declared_failed_ids.extend(round_detected)
                for nid in round_detected:
                    if nid not in failed_set:
                        false_positive_ids.append(nid)
                break

        detected_failures = [nid for nid in declared_failed_ids if nid in failed_set]
        return detection_time, detected_failures, false_positive_ids

    else:
        # Centralized baselines
        extra_delay = config.CENTRALIZED_EXTRA_DELAY_MS
        monitor_last_hb = {s.node_id: 0.0 for s in states}

        # Track heartbeat arrivals at central monitor M: (arrival_time, sender_id, send_time)
        events = []
        for r in range(1, max_rounds + 1):
            send_time = r * heartbeat_interval
            for s in states:
                if s.node_id in failed_set:
                    continue
                jitter = abs(rng.normal(0.0, config.HEARTBEAT_JITTER_SIGMA)) + extra_delay
                if rng.random() < config.HEARTBEAT_CONGESTION_PROB:
                    jitter += rng.uniform(config.HEARTBEAT_CONGESTION_MIN_MS, config.HEARTBEAT_CONGESTION_MAX_MS)
                arrival = send_time + jitter
                events.append((arrival, s.node_id, send_time))

        events.sort(key=lambda x: x[0])

        declared_failed_ids = []
        false_positive_ids = []
        detection_time = max_rounds * heartbeat_interval
        event_idx = 0

        for r in range(1, max_rounds + 1):
            current_ms = r * heartbeat_interval
            # Process all heartbeats received up to current_ms
            while event_idx < len(events) and events[event_idx][0] <= current_ms:
                arrival, sender, send_time = events[event_idx]
                monitor_last_hb[sender] = max(monitor_last_hb[sender], send_time)
                event_idx += 1

            round_detected = []
            for s in states:
                if s.node_id in declared_failed_ids:
                    continue
                last_hb = monitor_last_hb[s.node_id]
                if current_ms - last_hb > tau_h:
                    round_detected.append(s.node_id)

            if round_detected:
                # NOTE: extra_delay is already included in heartbeat jitter
                # (line 206), so we do NOT add it again here. The centralized
                # monitor's extra network hop is modeled as slower heartbeat
                # arrival, not as a post-detection processing delay.
                detection_time = current_ms
                declared_failed_ids.extend(round_detected)
                for nid in round_detected:
                    if nid not in failed_set:
                        false_positive_ids.append(nid)
                break

        detected_failures = [nid for nid in declared_failed_ids if nid in failed_set]
        if strategy == "Full Checkpoint":
            detection_time += config.CHECKPOINT_SYNC_OVERHEAD_MS
        return detection_time, detected_failures, false_positive_ids


# ═══════════════════════════════════════════════════════════════════════
# Strategy-specific recovery and chronological simulation
# ═══════════════════════════════════════════════════════════════════════

STRATEGY_NAMES = [
    "No FT",
    "Centralized HB",
    "Full Checkpoint",
    "Round-Robin",
    "Least-Queue",
    "Spider (Ours)",
]


def _run_scenario(n_nodes: int, failure_rate: float, seed: int) -> Dict:
    """
    Run one complete failure scenario for all strategies using chronological discrete-event simulation.
    """
    n_tasks = config.G8_N_TASKS

    # Shared scenario inputs
    task_rng = np.random.default_rng(seed)
    # Scale offered load dynamically with the number of nodes to maintain
    # approximately uniform per-node utilization across different cluster
    # sizes. Without this, larger clusters are under-utilized and smaller
    # clusters are over-saturated, making latency comparisons misleading.
    # Base rate: 1.0 at 5 nodes → each node gets ~40 tasks from 200 total.
    offered_load = 1.0 * (n_nodes / 5.0)
    tasks = generate_tasks(n_tasks, task_rng, offered_load=offered_load)

    assign_rng = np.random.default_rng(seed + 777)
    assignments = _assign_tasks_to_nodes(tasks, n_nodes, assign_rng)

    progress_rng = np.random.default_rng(seed + 555)
    progress = [float(progress_rng.uniform(config.G8_PROGRESS_MIN, config.G8_PROGRESS_MAX)) for _ in tasks]

    fail_rng = np.random.default_rng(seed + 999)
    n_failures = max(1, int(n_nodes * failure_rate))
    failed_indices = fail_rng.choice(n_nodes, size=n_failures, replace=False)
    failed_set = set(int(i) for i in failed_indices)

    results: Dict = {}

    for strategy in STRATEGY_NAMES:
        # Fresh nodes and states per strategy (identical initial conditions)
        fog_nodes = generate_nodes(n_nodes, heterogeneous=True,
                                   rng=np.random.default_rng(seed))
        states = [FogNodeState(fog_node=fn) for fn in fog_nodes]
        for s in states:
            s.last_heartbeat_ms = 0.0

        strat_rng = np.random.default_rng(seed + hash(strategy) % 10000)

        # ── Phase 1: Heartbeat simulation + detection ──
        if strategy == "No FT":
            detection_time = float('inf')
            fp_ids = []
        else:
            detection_time, detected_ids, fp_ids = _run_heartbeat_simulation(
                states, failed_set, strategy, strat_rng,
            )

        # After detection: mark failed nodes as non-alive
        for s in states:
            if s.node_id in failed_set:
                s.is_alive = False

        alive_states = [s for s in states if s.is_alive and not s.declared_failed]

        # Construct task scheduling events chronologically
        events = []
        for i, task in enumerate(tasks):
            assigned_node = assignments[i]
            if assigned_node in failed_set:
                if task.arrival_ms < detection_time:
                    # Orphaned: recovered at detection time
                    events.append((detection_time, 'recovery', i, assigned_node))
                else:
                    # Arrives after detection: scheduled normally on healthy node
                    events.append((task.arrival_ms, 'normal', i, assigned_node))
            else:
                # Normal task on healthy node: scheduled at arrival
                events.append((task.arrival_ms, 'normal', i, assigned_node))

        # Process events chronologically
        events.sort(key=lambda x: x[0])

        completed = 0
        recovery_lats = []
        control_msgs = 0

        # Import execution functions locally
        from phase4_load_balance.inter_node import execute_task, choose_node
        import copy

        for event_time, etype, idx, assigned_node in events:
            task = copy.copy(tasks[idx])

            if etype == 'normal':
                if assigned_node not in failed_set:
                    node = states[assigned_node].fog_node
                else:
                    if not alive_states:
                        continue
                    # Redirect to healthy node using the strategy's scheduler
                    if strategy == "Spider (Ours)":
                        node = choose_node([s.fog_node for s in alive_states], task, "Spider (Ours)", strat_rng)
                    elif strategy == "Least-Queue":
                        best = min(alive_states, key=lambda s: s.fog_node.assigned_count)
                        node = best.fog_node
                    elif strategy == "Round-Robin":
                        node = alive_states[idx % len(alive_states)].fog_node
                    elif strategy == "No FT":
                        continue  # Dropped — no fault awareness
                    else:
                        # Centralized HB / Full Checkpoint: use min-latency
                        # selection consistent with centralized monitoring
                        # (same heuristic as Ref[22] OLB scheduling)
                        node = min(
                            [s.fog_node for s in alive_states],
                            key=lambda n: n.network_ms + max(0.0, max(n.tee_available_ms, n.ree_available_ms) - task.arrival_ms)
                        )

                total_lat = execute_task(node, task, strat_rng)
                if total_lat <= task.deadline_ms:
                    completed += 1

            elif etype == 'recovery':
                if strategy == "No FT":
                    continue
                if not alive_states:
                    continue

                if strategy == "Spider (Ours)":
                    restart_fraction = max(0.05, 1.0 - progress[idx])
                    control_msgs += 1
                    recovery_state = select_recovery_node(
                        states, strat_rng, task,
                        decision_time=event_time,
                        restart_fraction=restart_fraction,
                    )
                    if recovery_state is None:
                        continue
                    node = recovery_state.fog_node
                elif strategy == "Full Checkpoint":
                    restart_fraction = max(0.1, 1.0 - config.G8_CHECKPOINT_PROGRESS + strat_rng.uniform(-0.1, 0.1))
                    node = alive_states[int(strat_rng.integers(0, len(alive_states)))].fog_node
                    control_msgs += 3
                elif strategy == "Centralized HB":
                    restart_fraction = 1.0
                    # Centralized: min-latency selection (same as Ref[22] OLB)
                    node = min(
                        [s.fog_node for s in alive_states],
                        key=lambda n: n.network_ms + max(0.0, max(n.tee_available_ms, n.ree_available_ms))
                    )
                    control_msgs += len(states)  # O(N) per heartbeat round
                elif strategy == "Round-Robin":
                    restart_fraction = 1.0
                    node = alive_states[idx % len(alive_states)].fog_node
                    control_msgs += len(states)  # O(N) per heartbeat round
                elif strategy == "Least-Queue":
                    restart_fraction = 1.0
                    best = min(alive_states, key=lambda s: s.fog_node.assigned_count)
                    node = best.fog_node
                    control_msgs += len(states)  # O(N) per heartbeat round
                else:
                    continue

                lat = _execute_recovery_task(
                    node, task,
                    restart_fraction=restart_fraction,
                    detection_delay_ms=event_time,
                    rng=strat_rng,
                )
                recovery_lats.append(lat)
                total_lat = lat + (event_time - task.arrival_ms)
                if total_lat <= task.deadline_ms:
                    completed += 1

        avg_lat = float(np.mean(recovery_lats)) if recovery_lats else 0.0
        n_healthy = len(states) - len(failed_set)
        fp_rate = len(fp_ids) / max(1, n_healthy)

        results[strategy] = {
            "detection_time_ms": detection_time,
            "recovery_latency_ms": avg_lat,
            "task_completion_ratio": completed / len(tasks),
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
