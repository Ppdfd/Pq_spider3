"""
Test: scale offered_load with node_count so each node sees ~60-70% utilization
regardless of cluster size. This creates congestion at EVERY data point.
"""
import numpy as np, sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import choose_node, execute_task
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 6 + 37 * 12

def test_load(base_load, n_nodes, heterogeneous, scale_with_nodes=False):
    if scale_with_nodes:
        load = base_load * (n_nodes / 6.0)  # normalize to 6 nodes
    else:
        load = base_load
    
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
    return spider, best_ref, worst_ref, load

print("=== HETEROGENEOUS — Scale load with nodes (base=0.65) ===")
for n in [2, 4, 6, 8, 10, 12]:
    s, br, wr, load = test_load(0.65, n, True, scale_with_nodes=True)
    print(f"  {n:2d} nodes (load={load:.2f}): Spider={s:7.1f}  BestRef={br:7.1f}  Gap={br-s:+6.1f}ms ({(br-s)/br*100:+5.1f}%)")

print("\n=== HETEROGENEOUS — Scale load with nodes (base=0.80) ===")
for n in [2, 4, 6, 8, 10, 12]:
    s, br, wr, load = test_load(0.80, n, True, scale_with_nodes=True)
    print(f"  {n:2d} nodes (load={load:.2f}): Spider={s:7.1f}  BestRef={br:7.1f}  Gap={br-s:+6.1f}ms ({(br-s)/br*100:+5.1f}%)")

print("\n=== HOMOGENEOUS — Scale load with nodes (base=0.55) ===")
for n in [2, 4, 6, 8, 10, 12]:
    s, br, wr, load = test_load(0.55, n, False, scale_with_nodes=True)
    print(f"  {n:2d} nodes (load={load:.2f}): Spider={s:7.1f}  BestRef={br:7.1f}  Gap={br-s:+6.1f}ms ({(br-s)/br*100:+5.1f}%)")

print("\n=== HOMOGENEOUS — Scale load with nodes (base=0.70) ===")
for n in [2, 4, 6, 8, 10, 12]:
    s, br, wr, load = test_load(0.70, n, False, scale_with_nodes=True)
    print(f"  {n:2d} nodes (load={load:.2f}): Spider={s:7.1f}  BestRef={br:7.1f}  Gap={br-s:+6.1f}ms ({(br-s)/br*100:+5.1f}%)")
