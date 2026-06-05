import numpy as np
import sys
from utils.eval_utils import GLOBAL_SEED
from phase4_load_balance.inter_node import simulate_load_balancing
import config

def test_weights(w_wait, w_lat, w_epc, w_cap, w_reuse):
    config.W1_WAIT = w_wait
    config.W2_LATENCY = w_lat
    config.W3_EPC = w_epc
    config.W4_CAP = w_cap
    config.W8_REUSE = w_reuse
    
    # Graph 5 (Homogeneous, 12 nodes)
    val_g5 = simulate_load_balancing(12, "Spider (Ours)", False, seed=GLOBAL_SEED, n_tasks=2000)
    
    # Graph 6 (Heterogeneous, 12 nodes)
    val_g6 = simulate_load_balancing(12, "Spider (Ours)", True, seed=GLOBAL_SEED, n_tasks=2000)
    
    return val_g5, val_g6

print("Baseline:", test_weights(2.0, 0.5, 0.5, 0.4, 0.6))
print("More Wait:", test_weights(5.0, 0.5, 0.5, 0.4, 0.6))
print("More EPC:", test_weights(2.0, 0.5, 2.0, 0.4, 0.6))
print("More Reuse:", test_weights(2.0, 0.5, 0.5, 0.4, 3.0))
print("Less Latency:", test_weights(2.0, 0.1, 0.5, 0.4, 0.6))
print("All optimized:", test_weights(4.0, 0.1, 1.0, 1.0, 2.0))
