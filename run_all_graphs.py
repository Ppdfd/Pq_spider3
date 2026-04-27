#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.eval_utils import set_global_seed, ensure_dirs, configure_matplotlib, GLOBAL_SEED

from phase1_initialization.graph1 import graph1_setup_phase
from phase3_edge_gateway.graph2 import graph2_cache_reuse
from phase5_fog_node.graph3 import graph3_cpabe_encryption
from phase6_user_decrypt.graph4 import graph4_cpabe_decryption
from phase4_load_balance.graph5 import graph_load_balancing
from phase4_load_balance.graph6 import graph6_heterogeneous_fog
from phase4_load_balance.graph7 import (
    graph7_intra_enclave,
    run_graph7_experiment,
    graph7a_queue_state, graph7b_epc_availability,
    graph7c_load_imbalance, graph7f_deadline, graph7g_cache_reuse,
    graph7d_contention, graph7e_sensitivity,
    graph7h_enclave_scaling,
)
from phase5_fog_node.graph8 import graph8_recovery

def run_all_graphs():
    rng = set_global_seed(GLOBAL_SEED)
    ensure_dirs()
    configure_matplotlib()

    print("=" * 72)
    print("Spider++ Modular Evaluation Simulation")
    print("=" * 72)

    graph1_setup_phase(rng)
    print("  ✓ Graph 1 generated (phase1)")

    graph2_cache_reuse(rng)
    print("  ✓ Graph 2 generated (phase3)")

    graph3_cpabe_encryption(rng)
    #print("  ✓ Graph 3 generated (phase5)")

    graph4_cpabe_decryption(rng)
    #print("  ✓ Graph 4 generated (phase6)")

    graph_load_balancing(rng, graph_no=5, heterogeneous=False)
    print("  ✓ Graph 5 generated (phase4)")

    graph6_heterogeneous_fog()
    print("  ✓ Graph 6 generated (phase4)")

    # Graph 7: task-count sweep (runs its own simulations)
    graph7_intra_enclave(rng)
    print("  ✓ Graph 7 generated (phase4)")

    # ── Single experiment for all diagnostic views (7a-7c, 7f, 7g) ──
    results, enclaves = run_graph7_experiment(rng)
    print("  ✓ Graph 7 experiment complete (1 run × 3 algorithms)")

    graph7a_queue_state(results, enclaves)
    print("  ✓ Graph 7a generated (routing intelligence)")
    graph7b_epc_availability(results, enclaves)
    print("  ✓ Graph 7b generated (EPC swap events)")
    graph7c_load_imbalance(results, enclaves)
    print("  ✓ Graph 7c generated (latency CDF)")
    graph7f_deadline(results, enclaves)
    print("  ✓ Graph 7f generated (deadline compliance)")
    graph7g_cache_reuse(results, enclaves)
    print("  ✓ Graph 7g generated (cache affinity)")

    # Parameter sweep graphs (run their own simulations)
    graph7d_contention(rng)
    print("  ✓ Graph 7d generated (heterogeneity sweep)")
    graph7e_sensitivity(rng)
    print("  ✓ Graph 7e generated (sensitivity analysis)")
    graph7h_enclave_scaling(rng)
    print("  ✓ Graph 7h generated (enclave scaling)")

    graph8_recovery(rng)
    print("  ✓ Graph 8 generated (phase5)")

    print("=" * 72)

if __name__ == "__main__":
    run_all_graphs()

