#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.eval_utils import set_global_seed, ensure_dirs, configure_matplotlib, GLOBAL_SEED

from graphs.exp1a_internode_homogeneous import graph1_load_balancing
from graphs.exp1b_internode_heterogeneous import graph2_heterogeneous_fog
from graphs.exp2_intranode_enclave import graph3_intra_enclave, run_graph7_experiment
from graphs.exp3_recovery_latency import graph4_recovery_latency
from graphs.exp4_completion_ratio import graph5_task_completion
from graphs.exp5_cache_reuse import graph6_cache_reuse
from graphs.exp7a_decision_latency import graph7_decision_latency
from graphs.exp7b_enclave_aware import graph8_enclave_aware

def run_all_graphs():
    rng = set_global_seed(GLOBAL_SEED)
    ensure_dirs()
    configure_matplotlib()

    print("=" * 72)
    print("Spider Modular Evaluation Simulation")
    print("=" * 72)

    graph1_load_balancing(rng, graph_no=5, heterogeneous=False)
    print("  * Graph 1 (Homogeneous Fog Node) generated")
    
    graph2_heterogeneous_fog(rng)
    print("  * Graph 2 (Heterogeneous Fog Node) generated")

    graph3_intra_enclave(rng)
    print("  * Graph 3 (Intra-node Scheduling under Enclave Heterogeneity) generated")
    results, enclaves = run_graph7_experiment(rng)
    print("  * Graph 3 Diagnostic details complete")

    graph4_recovery_latency(rng)
    print("  * Graph 4 (Recovery Latency vs Fog Nodes) generated")

    graph5_task_completion(rng)
    print("  * Graph 5 (Task Completion Ratio vs Failure Rate) generated")
    
    graph6_cache_reuse(rng)
    print("  * Graph 6 (Cache/Reuse-Aware Scheduling) generated")

    graph7_decision_latency(rng)
    print("  * Graph 7 (Load-Balancing Decision Latency) generated")

    graph8_enclave_aware(rng)
    print("  * Graph 8 (Impact of Enclave-Aware Scheduling) generated")

    print("=" * 72)

if __name__ == "__main__":
    run_all_graphs()
