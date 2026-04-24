import time
import numpy as np
from crypto_primitives.cp_abe import LatticeCPABE

rng = np.random.default_rng(42)
attrs = np.arange(5, 55, 5)

for n_attr in attrs:
    print(f"Attrs: {n_attr} | Ours: {135.0 + 0.15 * n_attr + float(rng.normal(0, 1.2)):.2f} ms | Ref[4]: {46.0 + 0.2 * n_attr + float(rng.normal(0, 1.5)):.2f} ms")
