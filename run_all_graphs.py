#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.eval_utils import set_global_seed, ensure_dirs, configure_matplotlib, GLOBAL_SEED

from graphs.graph1 import graph1_setup_phase
from graphs.graph2 import graph2_cache_reuse
from graphs.graph3 import graph3_cpabe_encryption
from graphs.graph4 import graph4_cpabe_decryption
from graphs.graph5 import graph_load_balancing
from graphs.graph6 import graph6_heterogeneous_fog
from graphs.graph7 import graph7_intra_enclave, run_graph7_experiment
from graphs.graph8 import graph8_recovery_latency
from graphs.graph9 import graph9_task_completion

def run_all_graphs():
    rng = set_global_seed(GLOBAL_SEED)
    ensure_dirs()
    configure_matplotlib()

    print("=" * 72)
    print("Spider Modular Evaluation Simulation")
    print("=" * 72)

    #graph1_setup_phase(rng)
    print("  * Graph 1 generated (phase1)")

    #graph2_cache_reuse(rng)
    print("  * Graph 2 generated (phase3)")

    #graph3_cpabe_encryption(rng)
    print("  * Graph 3 generated (phase5)")

    #graph4_cpabe_decryption(rng)
    print("  * Graph 4 generated (phase6)")

    graph_load_balancing(rng, graph_no=5, heterogeneous=False)
    print("  * Graph 5 generated (phase4)")

    graph6_heterogeneous_fog(rng)
    print("  * Graph 6 generated (phase4)")

    # Graph 7: task-count sweep (runs its own simulations)
    graph7_intra_enclave(rng)
    print("  * Graph 7 generated (phase4)")

    # ── Single experiment for all diagnostic views (7, 11, 12, 13, 14) ──
    results, enclaves = run_graph7_experiment(rng)
    print("  * Graph 7 experiment complete (1 run x 3 algorithms)")

    graph8_recovery_latency(rng)
    print("  * Graph 8 generated (fault-tolerance)")

    graph9_task_completion(rng)
    print("  * Graph 9 generated (fault-tolerance)")

    print("=" * 72)

if __name__ == "__main__":
    run_all_graphs()
