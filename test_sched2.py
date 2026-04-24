import numpy as np
from evaluation.spiderpp_full_evaluation import simulate_load_balancing, GLOBAL_SEED

for alg in ["Ref[22]", "Ref[37]", "Ref[39]", "Spider++ (Ours)"]:
    val5 = simulate_load_balancing(8, alg, heterogeneous=False, seed=GLOBAL_SEED)
    val6 = simulate_load_balancing(8, alg, heterogeneous=True, seed=GLOBAL_SEED)
    print(f"{alg:15} | Homogeneous N=8: {val5:.2f} | Heterogeneous N=8: {val6:.2f}")

