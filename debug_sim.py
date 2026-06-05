"""
Deep diagnostic: trace exactly what each algorithm does differently
in the simulation loop for Graph 6 (heterogeneous, 12 nodes).
"""
import numpy as np
import sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import (
    choose_node, execute_task, epc_pressure_penalty,
    _score_ref22, _score_ref37, _score_ref39, _score_spider,
    simulate_load_balancing
)
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 6 + 37 * 12
n_tasks = 500  # enough to see patterns

# Generate the shared task stream and nodes
base_rng = np.random.default_rng(seed)
tasks = generate_tasks(n_tasks, base_rng, offered_load=0.65)
base_nodes = generate_nodes(12, heterogeneous=True, rng=np.random.default_rng(seed))

print("=== NODE PROPERTIES ===")
for n in base_nodes:
    print(f"  Node {n.node_id}: tee={n.tee_rate:.2f} ree={n.ree_rate:.2f} "
          f"net={n.network_ms:.1f}ms epc={n.epc_total_mb:.0f}MB "
          f"trust={n.trust:.3f} cached={n.policy_cached}/{n.kyber_cached}")

print(f"\n=== TASK PROPERTIES (first 5) ===")
for t in tasks[:5]:
    print(f"  arr={t.arrival_ms:.1f} tee_work={t.tee_work:.1f} ree_work={t.ree_work:.1f} "
          f"epc_req={t.epc_req_mb:.1f}MB risk={t.risk:.2f} deadline={t.deadline_ms:.0f}ms")

# Run each algorithm and track node selections
for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
    rng = np.random.default_rng(seed)
    nodes = clone_nodes(base_nodes)
    
    node_selections = [0] * 12
    latencies = []
    
    for task in tasks:
        node = choose_node(nodes, task, alg, rng)
        node_selections[node.node_id] += 1
        lat = execute_task(node, task, rng)
        latencies.append(lat)
    
    arr = np.array(latencies)
    lo, hi = np.percentile(arr, [2, 98])
    trimmed = arr[(arr >= lo) & (arr <= hi)]
    
    print(f"\n=== {alg} ===")
    print(f"  Mean latency: {trimmed.mean():.2f}ms  (median: {np.median(arr):.2f}ms)")
    print(f"  Node selections: {node_selections}")
    print(f"  Selection entropy: {-sum(c/n_tasks * np.log2(c/n_tasks) for c in node_selections if c > 0):.3f} bits")
    
    # Show what the node state looks like after all tasks
    print(f"  Final node states:")
    for n in nodes:
        epc_penalty = epc_pressure_penalty(tasks[0], n)
        print(f"    Node {n.node_id}: assigned={n.assigned_count} "
              f"tee_avail={n.tee_available_ms:.0f} ree_avail={n.ree_available_ms:.0f} "
              f"epc_penalty={epc_penalty:.4f}")
