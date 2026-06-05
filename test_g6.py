import numpy as np
from utils.eval_utils import GLOBAL_SEED
from graphs.graph6 import graph_load_balancing
import config

rng = np.random.default_rng(GLOBAL_SEED)
means = graph_load_balancing(rng, graph_no=6, heterogeneous=True, reps=1)
for alg, mean in means.items():
    print(f"{alg}: {mean}")
