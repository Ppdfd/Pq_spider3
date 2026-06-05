#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.eval_utils import set_global_seed, ensure_dirs, configure_matplotlib, GLOBAL_SEED

from graphs.exp5_cache_reuse import graph2_cache_reuse
from graphs.exp1a_internode_homogeneous import graph_load_balancing
from graphs.exp1b_internode_heterogeneous import graph6_heterogeneous_fog
from graphs.exp2_intranode_enclave import graph7_intra_enclave, run_graph7_experiment
from graphs.exp3_recovery_latency import graph8_recovery_latency
from graphs.exp4_completion_ratio import graph9_task_completion

def run_all_graphs():
    rng = set_global_seed(GLOBAL_SEED)
    ensure_dirs()
    configure_matplotlib()

    print("=" * 72)
    print("Spider Modular Evaluation Simulation")
    print("=" * 72)

    #graph_load_balancing(rng, graph_no=5, heterogeneous=False)
    print("  * Experiment 1a (Homogeneous Internode Scheduling) generated")
    
    #graph6_heterogeneous_fog(rng)
    print("  * Experiment 1b (Heterogeneous Internode Scheduling) generated")

    print("  * Experiment 2 (Intra-Node Enclave Scheduling) generated")
    #graph7_intra_enclave(rng)
    #results, enclaves = run_graph7_experiment(rng)
    print("  * Experiment 2 Diagnostic details complete")

    #graph8_recovery_latency(rng)
    print("  * Experiment 3 (Fault-Tolerant Recovery Latency) generated")

    #graph9_task_completion(rng)
    print("  * Experiment 4 (Task Completion under Failures) generated")
    
    graph2_cache_reuse(rng)
    print("  * Experiment 5/6 (Cache- and Reuse-Aware Scheduling) generated")

    print("=" * 72)

if __name__ == "__main__":
    run_all_graphs()
