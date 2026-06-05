"""
THE KEY QUESTION: With 12 heterogeneous nodes and 10000 tasks, 
does the CHOICE of node actually matter for latency?

The simulation is a discrete-event queue: tasks arrive, queue up behind
previous tasks, and drain sequentially. With enough tasks, ALL nodes
become saturated and the system bottleneck shifts from "which node" to
"how fast can the shared queue drain."

Let's test: if we route ALL tasks to a random node vs. the best node,
what's the difference?
"""
import numpy as np
import sys
sys.path.insert(0, '.')
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import execute_task, simulate_load_balancing
from phase4_load_balance.generators import generate_tasks, generate_nodes
from phase4_load_balance.models import clone_nodes

seed = GLOBAL_SEED + 20000 * 6 + 37 * 12

# What does the simulation produce at different task counts?
for n_tasks in [100, 500, 1000, 2000, 5000, 10000]:
    results = {}
    for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]:
        results[alg] = simulate_load_balancing(12, alg, True, seed=seed, n_tasks=n_tasks)
    
    spider = results["Spider (Ours)"]
    worst = max(results[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
    best_ref = min(results[a] for a in ["Ref[22]", "Ref[37]", "Ref[39]"])
    
    print(f"\nn_tasks={n_tasks:5d}: Spider={spider:.1f}ms  BestRef={best_ref:.1f}ms  "
          f"WorstRef={worst:.1f}ms  Gap={best_ref-spider:.1f}ms  "
          f"SpiderAdvantage={(best_ref-spider)/best_ref*100:.1f}%")
    for alg, v in results.items():
        print(f"  {alg:20s}: {v:.2f}ms")

# Also test: how much queuing dominates
print("\n\n=== QUEUE SATURATION ANALYSIS ===")
for n_tasks in [100, 500, 2000, 10000]:
    base_rng = np.random.default_rng(seed)
    rng = np.random.default_rng(seed)
    tasks = generate_tasks(n_tasks, base_rng, offered_load=0.65)
    nodes = clone_nodes(generate_nodes(12, heterogeneous=True, rng=np.random.default_rng(seed)))
    
    queue_waits = []
    service_times = []
    for task in tasks:
        # Just pick round-robin to isolate queuing
        node = nodes[task.records % 12]  # deterministic spread
        
        net = max(0.5, node.network_ms + rng.normal(0.0, 0.12 * node.network_ms))
        arrival_at_node = task.arrival_ms + net
        
        tee_start = max(arrival_at_node, node.tee_available_ms)
        queue_wait = tee_start - arrival_at_node
        queue_waits.append(queue_wait)
        
        tee_service = (task.tee_work / node.tee_rate) * float(rng.lognormal(0.0, 0.055)) + 2.6
        ree_service = (task.ree_work / node.ree_rate) * float(rng.lognormal(0.0, 0.060)) + 1.8
        service_times.append(tee_service + ree_service)
        
        tee_finish = tee_start + tee_service
        ree_start = max(tee_finish, node.ree_available_ms)
        finish = ree_start + ree_service + max(0.3, rng.normal(3.6, 0.45))
        node.tee_available_ms = tee_finish
        node.ree_available_ms = finish
    
    qw = np.array(queue_waits)
    st = np.array(service_times)
    print(f"n_tasks={n_tasks:5d}: avg_queue_wait={qw.mean():.1f}ms  avg_service={st.mean():.1f}ms  "
          f"queue_fraction={qw.mean()/(qw.mean()+st.mean())*100:.1f}%  "
          f"max_queue_wait={qw.max():.0f}ms")
