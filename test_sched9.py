import numpy as np
import time

def run_test():
    from evaluation.spiderpp_full_evaluation import simulate_load_balancing, GLOBAL_SEED
    node_counts = [2, 4, 6, 8, 10, 12]
    for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider++ (Ours)"]:
        vals = []
        for n in node_counts:
            val = simulate_load_balancing(n, alg, heterogeneous=False, seed=GLOBAL_SEED)
            vals.append(f"{val:.1f}")
        print(f"{alg:15} | " + " | ".join(vals))

run_test()
