import numpy as np
import copy
import config
import math
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.failure_detection import FogNodeState, partition_into_groups, select_recovery_node
from phase4_load_balance.inter_node import execute_task, choose_node
from graphs.graph8 import STRATEGY_NAMES, _assign_tasks_to_nodes, _execute_recovery_task

def run_causality_heartbeat_sim(states, failed_set, strategy, rng):
    tau_h = config.HEARTBEAT_TIMEOUT_MS
    heartbeat_interval = 10.0
    max_rounds = 40
    
    n_nodes = len(states)
    
    if strategy == "Spider-FT (Ours)":
        groups = partition_into_groups(states)
        node_to_group = {}
        for g in groups:
            for m in g.members:
                node_to_group[m.node_id] = g
                
        monitor_last_hb = {
            j.node_id: {i.node_id: 0.0 for i in states}
            for j in states
        }
        
        events = []
        for r in range(1, max_rounds + 1):
            send_time = r * heartbeat_interval
            for s in states:
                if s.node_id in failed_set:
                    continue
                
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
            while event_idx < len(events) and events[event_idx][0] <= current_ms:
                arrival, sender, receiver, send_time = events[event_idx]
                monitor_last_hb[receiver][sender] = max(monitor_last_hb[receiver][sender], send_time)
                event_idx += 1
                
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
                        continue
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
        extra_delay = config.CENTRALIZED_EXTRA_DELAY_MS
        monitor_last_hb = {s.node_id: 0.0 for s in states}
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
                detection_time = current_ms + extra_delay
                declared_failed_ids.extend(round_detected)
                for nid in round_detected:
                    if nid not in failed_set:
                        false_positive_ids.append(nid)
                break
                
        detected_failures = [nid for nid in declared_failed_ids if nid in failed_set]
        if strategy == "Full Checkpoint":
            detection_time += config.CHECKPOINT_SYNC_OVERHEAD_MS
        return detection_time, detected_failures, false_positive_ids

def test_scenario(n_nodes, failure_rate, seed):
    n_tasks = config.G8_N_TASKS
    task_rng = np.random.default_rng(seed)
    
    offered_load = 1.0 * (n_nodes / 5.0)
    tasks = generate_tasks(n_tasks, task_rng, offered_load=offered_load)
    
    assign_rng = np.random.default_rng(seed + 777)
    assignments = _assign_tasks_to_nodes(tasks, n_nodes, assign_rng)
    progress_rng = np.random.default_rng(seed + 555)
    progress = [float(progress_rng.uniform(0.1, 0.85)) for _ in tasks]

    fail_rng = np.random.default_rng(seed + 999)
    n_failures = max(1, int(n_nodes * failure_rate))
    failed_indices = fail_rng.choice(n_nodes, size=n_failures, replace=False)
    failed_set = set(int(i) for i in failed_indices)

    results = {}

    for strategy in STRATEGY_NAMES:
        fog_nodes = generate_nodes(n_nodes, heterogeneous=True, rng=np.random.default_rng(seed))
        states = [FogNodeState(fog_node=fn) for fn in fog_nodes]
        for s in states:
            s.last_heartbeat_ms = 0.0

        strat_rng = np.random.default_rng(seed + hash(strategy) % 10000)

        if strategy == "No FT":
            detection_time = float('inf')
            fp_ids = []
        else:
            detection_time, detected_ids, fp_ids = run_causality_heartbeat_sim(
                states, failed_set, strategy, strat_rng
            )

        for s in states:
            if s.node_id in failed_set:
                s.is_alive = False

        alive_states = [s for s in states if s.is_alive and not s.declared_failed]

        events = []
        for i, task in enumerate(tasks):
            assigned_node = assignments[i]
            if assigned_node in failed_set:
                if task.arrival_ms < detection_time:
                    events.append((detection_time, 'recovery', i, assigned_node))
                else:
                    events.append((task.arrival_ms, 'normal', i, assigned_node))
            else:
                events.append((task.arrival_ms, 'normal', i, assigned_node))

        events.sort(key=lambda x: x[0])

        completed = 0
        recovery_lats = []

        for event_time, etype, idx, assigned_node in events:
            task = copy.copy(tasks[idx])
            
            if etype == 'normal':
                if assigned_node not in failed_set:
                    node = states[assigned_node].fog_node
                else:
                    if not alive_states:
                        continue
                    if strategy == "Spider-FT (Ours)":
                        node = choose_node([s.fog_node for s in alive_states], task, "Spider (Ours)", strat_rng)
                    elif strategy == "Least-Queue":
                        best = min(alive_states, key=lambda s: s.fog_node.assigned_count)
                        node = best.fog_node
                    elif strategy == "Round-Robin":
                        node = alive_states[idx % len(alive_states)].fog_node
                    else:
                        if strategy == "No FT":
                            continue
                        node = alive_states[int(strat_rng.integers(0, len(alive_states)))].fog_node

                total_lat = execute_task(node, task, strat_rng)
                if total_lat <= task.deadline_ms:
                    completed += 1

            elif etype == 'recovery':
                if strategy == "No FT":
                    continue
                if not alive_states:
                    continue

                if strategy == "Spider-FT (Ours)":
                    restart_fraction = max(0.05, 1.0 - progress[idx])
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
                elif strategy == "Centralized HB":
                    restart_fraction = 1.0
                    node = alive_states[int(strat_rng.integers(0, len(alive_states)))].fog_node
                elif strategy == "Round-Robin":
                    restart_fraction = 1.0
                    node = alive_states[idx % len(alive_states)].fog_node
                elif strategy == "Least-Queue":
                    restart_fraction = 1.0
                    best = min(alive_states, key=lambda s: s.fog_node.assigned_count)
                    node = best.fog_node
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
        results[strategy] = {
            "detection_time": detection_time,
            "recovery_latency": avg_lat,
            "completion_ratio": completed / len(tasks),
            "num_recovered": len(recovery_lats),
        }

    return results

print("Sweeping failure rates for Graph 9...")
rates = [0.05, 0.10, 0.15, 0.20, 0.25]
for rate in rates:
    print(f"\n--- Failure Rate: {rate * 100:.0f}% ---")
    res = test_scenario(30, rate, 42)
    for k, v in res.items():
        print(f"  {k:20s}: det={v['detection_time']:.1f}ms, rec={v['recovery_latency']:.1f}ms, comp={v['completion_ratio']:.2%}")
