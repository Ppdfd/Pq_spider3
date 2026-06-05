import numpy as np
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import simulate_load_balancing
from phase4_load_balance.params import SIMULATION_PARAMS
import phase4_load_balance.inter_node as inter_node

# Monkeypatch execute_task
orig_execute = inter_node.execute_task

def execute_task_with_swap(node, task, rng):
    net = max(0.5, node.network_ms + rng.normal(0.0, 0.12 * node.network_ms))
    arrival_at_node = task.arrival_ms + net

    # Ensure list exists
    if not hasattr(node, '_finish_times'):
        node._finish_times = []
    
    # Drain completed tasks
    node._finish_times = [t for t in node._finish_times if t > task.arrival_ms]
    active_count = len(node._finish_times)

    tee_service = (task.tee_work / max(0.1, node.tee_rate)) * float(rng.lognormal(0.0, 0.055)) + SIMULATION_PARAMS["tee_startup_ms"]
    
    # ADD ACTUAL SWAP PENALTY
    M_free = node.epc_total_mb - task.epc_req_mb * active_count
    if M_free < task.epc_req_mb:
        swap_penalty = float(rng.uniform(*SIMULATION_PARAMS["epc_swap_range"]))
        tee_service += swap_penalty

    ree_service = (task.ree_work / max(0.1, node.ree_rate)) * float(rng.lognormal(0.0, 0.060)) + SIMULATION_PARAMS["ree_startup_ms"]

    tee_start = max(arrival_at_node, node.tee_available_ms)
    tee_finish = tee_start + tee_service
    ree_start = max(tee_finish, node.ree_available_ms)
    finish = ree_start + ree_service + max(0.3, rng.normal(SIMULATION_PARAMS["finalization_ms"], 0.45))

    node._finish_times.append(finish)
    node.tee_available_ms = tee_finish
    node.ree_available_ms = finish
    node.assigned_count += 1

    capacity = max(0.1, node.tee_rate + node.ree_rate)
    node.traffic_load = min(0.99, node.traffic_load + task.payload_kb / (capacity * 100.0))
    node.computing_load = min(0.99, node.computing_load + task.total_work / (capacity * 100.0))
    
    proc_time = tee_service + ree_service
    node.cumulative_energy += node.energy_factor * proc_time
    node.tasks_completed += 1

    return float(finish - task.arrival_ms)

inter_node.execute_task = execute_task_with_swap

# Also monkeypatch epc_pressure_penalty to use active_count!
def epc_pressure_penalty_fixed(task, node):
    import math
    import config
    active_count = len(getattr(node, '_finish_times', []))
    M_free = max(0.01, node.epc_total_mb - task.epc_req_mb * active_count)
    epsilon_j = M_free / max(0.01, node.epc_total_mb)
    rho_epc = 1.0 / (1.0 + math.exp(-config.EPC_KAPPA * (epsilon_j - config.EPC_PRESSURE_TAU)))
    return rho_epc * (task.epc_req_mb / max(0.01, M_free))

inter_node.epc_pressure_penalty = epc_pressure_penalty_fixed

def test():
    rng = np.random.default_rng(GLOBAL_SEED)
    print("Graph 6 (Heterogeneous, 12 nodes):")
    for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
        mean = simulate_load_balancing(12, alg, True, seed=GLOBAL_SEED, n_tasks=2000)
        print(f"  {alg}: {mean}")
    
    print("\nGraph 5 (Homogeneous, 12 nodes):")
    for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
        mean = simulate_load_balancing(12, alg, False, seed=GLOBAL_SEED, n_tasks=2000)
        print(f"  {alg}: {mean}")

test()
