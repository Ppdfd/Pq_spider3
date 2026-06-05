"""Why is Spider WORSE in homogeneous? The contention penalty punishes
concentration, and Spider concentrates on fewer nodes."""
import numpy as np, sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import choose_node, execute_task, _active_count
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 5 + 37 * 12

for alg in ["Ref[22]", "Spider (Ours)"]:
    rng = np.random.default_rng(seed)
    nodes = clone_nodes(generate_nodes(12, False, np.random.default_rng(seed)))
    tasks = generate_tasks(2000, np.random.default_rng(seed), offered_load=0.55)
    
    picks = []
    max_active = []
    for t in tasks:
        node = choose_node(nodes, t, alg, rng)
        picks.append(node.node_id)
        active = _active_count(node, t.arrival_ms)
        max_active.append(active)
        execute_task(node, t, rng)
    
    from collections import Counter
    c = Counter(picks)
    print(f"\n{alg}:")
    print(f"  Node distribution: {[c.get(i,0) for i in range(12)]}")
    print(f"  Max active at decision: max={max(max_active)}, avg={np.mean(max_active):.2f}")
    print(f"  Top-3 nodes get: {sum(sorted(c.values())[-3:])/2000*100:.0f}% of tasks")
