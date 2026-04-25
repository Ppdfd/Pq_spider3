import numpy as np
from evaluation.spiderpp_full_evaluation import GLOBAL_SEED
from evaluation.spiderpp_full_evaluation import graph4_cpabe_decryption

rng = np.random.default_rng(GLOBAL_SEED)
data = graph4_cpabe_decryption(rng, reps=1)
attrs = np.arange(5, 55, 5)

for k, v in data.items():
    print(f"=== {k} ===")
    for i, a in enumerate(attrs):
        print(f"  Attr {a}: {v[i]:.2f} ms")

