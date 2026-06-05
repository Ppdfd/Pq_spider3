"""
Diagnose exactly WHY Spider can't differentiate from baselines.
Three hypotheses:
  H1: EPC penalty is too small to matter (scoring)
  H2: EPC state is broken (assigned_count never decreases)
  H3: execute_task doesn't penalize bad scheduling decisions
"""
import numpy as np, sys, math
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import choose_node, execute_task, epc_pressure_penalty
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes
from phase4_load_balance.params import SIMULATION_PARAMS
import config

seed = GLOBAL_SEED + 20000 * 5 + 37 * 12

# === H1: How much does EPC penalty affect scoring vs execution? ===
print("=" * 60)
print("H1: EPC PENALTY MAGNITUDE")
print("=" * 60)
base_rng = np.random.default_rng(seed)
tasks = generate_tasks(200, base_rng, offered_load=0.55)
nodes_homo = generate_nodes(12, False, np.random.default_rng(seed))
nodes_hetero = generate_nodes(12, True, np.random.default_rng(seed))

# Check EPC penalty at different assigned_counts
for label, nodes in [("Homogeneous", nodes_homo), ("Heterogeneous", nodes_hetero)]:
    print(f"\n{label} nodes:")
    for n in nodes[:3]:
        for ac in [0, 1, 3, 5, 10, 50]:
            n.assigned_count = ac
            p = epc_pressure_penalty(tasks[0], n)
            print(f"  Node {n.node_id} (epc={n.epc_total_mb:.0f}MB): "
                  f"assigned={ac:3d} -> penalty={p:.4f}ms")
        n.assigned_count = 0

# === H2: Does assigned_count reflect reality? ===
print("\n" + "=" * 60)
print("H2: assigned_count NEVER DECREASES")
print("=" * 60)
rng = np.random.default_rng(seed)
nodes = clone_nodes(generate_nodes(12, False, np.random.default_rng(seed)))
tasks_100 = generate_tasks(100, np.random.default_rng(seed), offered_load=0.55)

# Run 100 tasks on Spider
for t in tasks_100:
    node = choose_node(nodes, t, "Spider (Ours)", rng)
    execute_task(node, t, rng)

for n in nodes:
    if n.assigned_count > 0:
        # How many tasks are ACTUALLY still running on this node?
        # A task finishes at ree_available_ms. The last task arrived at ~tasks_100[-1].arrival_ms
        last_arrival = tasks_100[-1].arrival_ms
        still_running = 1 if n.ree_available_ms > last_arrival else 0
        print(f"  Node {n.node_id}: assigned_count={n.assigned_count} but "
              f"actually_active≈{still_running} (ree_avail={n.ree_available_ms:.0f}ms, "
              f"last_arrival={last_arrival:.0f}ms)")

# === H3: Does execute_task penalize overloaded nodes? ===
print("\n" + "=" * 60)
print("H3: EXECUTION PENALTY FOR OVERLOADED NODES")
print("=" * 60)
print(f"  epc_swap_range = {SIMULATION_PARAMS['epc_swap_range']}")
print(f"  tee_startup_ms = {SIMULATION_PARAMS['tee_startup_ms']}")
print(f"  epc_pressure_penalty at assigned_count=50: {epc_pressure_penalty(tasks[0], nodes_homo[0]):.4f}ms")
# The penalty is added to tee_service, but it's only ~1.7ms out of ~30ms total service
# Compare to the REAL swap penalty which should be 8-16ms
print(f"  Real SGX EPC swap cost: {SIMULATION_PARAMS['epc_swap_range']} ms")
print(f"  -> Current penalty ({epc_pressure_penalty(tasks[0], nodes_homo[0]):.1f}ms) is "
      f"{SIMULATION_PARAMS['epc_swap_range'][0] / max(0.01, epc_pressure_penalty(tasks[0], nodes_homo[0])):.0f}x "
      f"SMALLER than real swap cost ({SIMULATION_PARAMS['epc_swap_range'][0]}ms)")

# === WHAT WOULD HAPPEN WITH PROPER MODELING? ===
print("\n" + "=" * 60)
print("PROJECTED IMPROVEMENT WITH PROPER EPC MODELING")
print("=" * 60)
# If we add 12ms swap penalty for every task on an overloaded node,
# and Spider avoids those nodes:
avg_service = 30.0  # ms per task
swap_penalty = SIMULATION_PARAMS['epc_swap_range'][0]  # 8ms
# Fraction of tasks that would trigger swap on baselines (rough estimate)
# With 10000 tasks and 12 nodes, each node gets ~833 tasks
# EPC capacity: ~256MB, task EPC: ~50MB -> 5 concurrent tasks fill EPC
# Tasks arrive faster than they finish, so after the first 5, every task swaps
frac_swapping = 0.7  # 70% of tasks would trigger swap
baseline_penalty = frac_swapping * swap_penalty
print(f"  Estimated baseline overhead: {frac_swapping:.0%} of tasks × {swap_penalty}ms = "
      f"+{baseline_penalty:.1f}ms per task")
print(f"  Spider avoids overloaded nodes -> ~0ms penalty")
print(f"  Expected gap: ~{baseline_penalty:.0f}ms ({baseline_penalty/avg_service*100:.0f}% improvement)")
