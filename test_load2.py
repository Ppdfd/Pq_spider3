import numpy as np, sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import choose_node, execute_task
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 6 + 37 * 12

def test_load(load, n_nodes, heterogeneous):
    results = {}
    for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
        rng_alg = np.random.default_rng(seed)
        alg_nodes = clone_nodes(generate_nodes(n_nodes, heterogeneous=heterogeneous, rng=np.random.default_rng(seed)))
        base_rng = np.random.default_rng(seed)
        tasks = generate_tasks(2000, base_rng, offered_load=load)
        lats = []
        for task in tasks:
            node = choose_node(alg_nodes, task, alg, rng_alg)
            lats.append(execute_task(node, task, rng_alg))
        arr = np.array(lats)
        lo, hi = np.percentile(arr, [2, 98])
        results[alg] = float(arr[(arr >= lo) & (arr <= hi)].mean())
    
    spider = results["Spider (Ours)"]
    best_ref = min(results[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
    worst_ref = max(results[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
    
    return spider, best_ref, worst_ref

# Test across multiple node counts (as graph sweeps them)
print("=== HETEROGENEOUS (Graph 6) — Sweep node counts at different loads ===")
for load in [0.65, 0.80, 1.0, 1.2]:
    print(f"\noffered_load = {load}")
    for n in [2, 4, 6, 8, 10, 12]:
        s, br, wr = test_load(load, n, True)
        print(f"  {n:2d} nodes: Spider={s:7.1f}ms  BestRef={br:7.1f}ms  WorstRef={wr:7.1f}ms  Gap={br-s:+6.1f}ms ({(br-s)/br*100:+5.1f}%)")

print("\n=== HOMOGENEOUS (Graph 5) — Sweep node counts at different loads ===")
for load in [0.55, 0.70, 0.85, 1.0]:
    print(f"\noffered_load = {load}")
    for n in [2, 4, 6, 8, 10, 12]:
        s, br, wr = test_load(load, n, False)
        print(f"  {n:2d} nodes: Spider={s:7.1f}ms  BestRef={br:7.1f}ms  WorstRef={wr:7.1f}ms  Gap={br-s:+6.1f}ms ({(br-s)/br*100:+5.1f}%)")
