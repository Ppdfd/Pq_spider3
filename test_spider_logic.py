import numpy as np
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import simulate_load_balancing
import config

def test_spider():
    val_g5 = simulate_load_balancing(12, "Spider (Ours)", False, seed=GLOBAL_SEED, n_tasks=2000)
    val_g6 = simulate_load_balancing(12, "Spider (Ours)", True, seed=GLOBAL_SEED, n_tasks=2000)
    return val_g5, val_g6

print("Baseline:", test_spider())
