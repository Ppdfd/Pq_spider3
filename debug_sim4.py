"""
Compare node selection patterns. 
Spider picks DIFFERENT nodes than the baselines - but does the graph
show this? The issue is the TRIMMED MEAN at line 400 in simulate_load_balancing.
"""
import numpy as np
import sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import choose_node, execute_task
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 6 + 37 * 12
n_tasks = 10000

for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
    base_rng = np.random.default_rng(seed)
    rng = np.random.default_rng(seed)
    
    tasks = generate_tasks(n_tasks, base_rng, offered_load=0.65)
    nodes = clone_nodes(generate_nodes(12, heterogeneous=True, rng=np.random.default_rng(seed)))
    
    node_picks = []
    latencies = []
    for task in tasks:
        node = choose_node(nodes, task, alg, rng)
        node_picks.append(node.node_id)
        lat = execute_task(node, task, rng)
        latencies.append(lat)
    
    arr = np.array(latencies)
    picks = np.array(node_picks)
    
    # Show percentiles and distribution
    lo, hi = np.percentile(arr, [2, 98])
    trimmed = arr[(arr >= lo) & (arr <= hi)]
    
    print(f"\n=== {alg} ===")
    print(f"  Raw mean: {arr.mean():.2f}  Trimmed mean: {trimmed.mean():.2f}")
    print(f"  P5={np.percentile(arr,5):.1f}  P25={np.percentile(arr,25):.1f}  "
          f"P50={np.percentile(arr,50):.1f}  P75={np.percentile(arr,75):.1f}  "
          f"P95={np.percentile(arr,95):.1f}  P99={np.percentile(arr,99):.1f}")
    print(f"  Node distribution: {np.bincount(picks, minlength=12).tolist()}")
    
    # Per-node average latency
    for nid in range(12):
        mask = picks == nid
        if mask.sum() > 0:
            print(f"    Node {nid}: {mask.sum()} tasks, avg_lat={arr[mask].mean():.1f}ms, "
                  f"tee_rate={nodes[nid].tee_rate:.2f}, ree_rate={nodes[nid].ree_rate:.2f}")
