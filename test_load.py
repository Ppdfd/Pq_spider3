import numpy as np, sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
import phase4_load_balance.inter_node as inter_node
from phase4_load_balance.inter_node import simulate_load_balancing
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 6 + 37 * 12

# Temporarily patch offered_load and test
orig = inter_node.simulate_load_balancing

def test_load(load_homo, load_hetero):
    # Graph 6 (heterogeneous, 12 nodes)
    old_code = inter_node.simulate_load_balancing.__code__
    
    # Manual simulation with custom load
    base_rng = np.random.default_rng(seed)
    rng = np.random.default_rng(seed)
    tasks = generate_tasks(2000, base_rng, offered_load=load_hetero)
    nodes = clone_nodes(generate_nodes(12, heterogeneous=True, rng=np.random.default_rng(seed)))
    
    from phase4_load_balance.inter_node import choose_node, execute_task
    
    results = {}
    for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
        rng_alg = np.random.default_rng(seed)
        alg_nodes = clone_nodes(generate_nodes(12, heterogeneous=True, rng=np.random.default_rng(seed)))
        lats = []
        for task in generate_tasks(2000, np.random.default_rng(seed), offered_load=load_hetero):
            node = choose_node(alg_nodes, task, alg, rng_alg)
            lats.append(execute_task(node, task, rng_alg))
        arr = np.array(lats)
        lo, hi = np.percentile(arr, [2, 98])
        results[alg] = float(arr[(arr >= lo) & (arr <= hi)].mean())
    
    spider = results["Spider (Ours)"]
    best_ref = min(results[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
    worst_ref = max(results[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
    
    print(f"  load={load_hetero:.1f}: Spider={spider:.1f}ms  BestRef={best_ref:.1f}ms  "
          f"WorstRef={worst_ref:.1f}ms  Gap={best_ref-spider:.1f}ms ({(best_ref-spider)/best_ref*100:.0f}%)")

print("=== HETEROGENEOUS (Graph 6) ===")
for load in [0.65, 0.80, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0]:
    test_load(load, load)
