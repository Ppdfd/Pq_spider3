"""Find offered_load where 2-node latency stays < 500ms (readable) but
12-node still shows meaningful Spider advantage."""
import numpy as np, sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import choose_node, execute_task
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 6 + 37 * 12

def test(load, n_nodes, hetero):
    results = {}
    for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
        rng = np.random.default_rng(seed)
        nodes = clone_nodes(generate_nodes(n_nodes, heterogeneous=hetero, rng=np.random.default_rng(seed)))
        tasks = generate_tasks(2000, np.random.default_rng(seed), offered_load=load)
        lats = []
        for t in tasks:
            node = choose_node(nodes, t, alg, rng)
            lats.append(execute_task(node, t, rng))
        arr = np.array(lats)
        lo, hi = np.percentile(arr, [2, 98])
        results[alg] = float(arr[(arr >= lo) & (arr <= hi)].mean())
    return results

# Heterogeneous
print("=== HETEROGENEOUS ===")
for load in [0.55, 0.60, 0.65, 0.70]:
    print(f"\nload={load}")
    for n in [2, 6, 12]:
        r = test(load, n, True)
        s = r["Spider (Ours)"]
        br = min(r[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
        wr = max(r[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
        print(f"  {n:2d}n: Spider={s:8.1f}  Refs={br:.1f}-{wr:.1f}  Gap={br-s:+.1f}ms")

# Homogeneous  
print("\n=== HOMOGENEOUS ===")
for load in [0.45, 0.50, 0.55, 0.60]:
    print(f"\nload={load}")
    for n in [2, 6, 12]:
        r = test(load, n, False)
        s = r["Spider (Ours)"]
        br = min(r[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
        wr = max(r[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
        print(f"  {n:2d}n: Spider={s:8.1f}  Refs={br:.1f}-{wr:.1f}  Gap={br-s:+.1f}ms")
