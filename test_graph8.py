import numpy as np
from evaluation.spiderpp_full_evaluation import simulate_recovery_time

rates = np.array([5, 10, 15, 20, 25, 30, 35, 40])
methods = ["No Delegation", "Simple Retry / Reassignment", "Spider++ Secure Task Delegation (Ours)"]

for method in methods:
    print(f"=== {method} ===")
    for rate in rates:
        vals = [simulate_recovery_time(rate, method, seed) for seed in range(42, 47)]
        print(f"  Rate {rate}%: {np.mean(vals):.1f} ms")

