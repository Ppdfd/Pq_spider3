from typing import Dict

import numpy as np

from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR, noisy_curve
)
from phase4_load_balance.inter_node import simulate_load_balancing


def graph_load_balancing(
    rng: np.random.Generator,
    graph_no: int,
    heterogeneous: bool,
    reps: int = 5,
) -> Dict[str, np.ndarray]:
    """Common driver for Graph 5 and Graph 6."""

    import config
    if heterogeneous:
        node_counts_list = getattr(config, 'G6_NUM_FOGS', [2, 4, 6, 8, 10, 12])
        n_tasks = getattr(config, 'G6_NUM_TASKS', 160)
    else:
        node_counts_list = getattr(config, 'G5_NUM_FOGS', [2, 4, 6, 8, 10, 12])
        n_tasks = getattr(config, 'G5_NUM_TASKS', 160)
    
    node_counts = np.array(node_counts_list if isinstance(node_counts_list, (list, tuple, np.ndarray)) else [node_counts_list])
    algorithms = ["Ref[22]", "Ref[37]", "Ref[39]", "Spider (Ours)"]

    mean_series: Dict[str, np.ndarray] = {}
    std_series: Dict[str, np.ndarray] = {}

    for alg in algorithms:
        rep_values = []
        for rep in range(reps):
            vals = []
            for n in node_counts:
                seed = GLOBAL_SEED + 20000 * graph_no + 1000 * rep + 37 * int(n)
                vals.append(simulate_load_balancing(int(n), alg, heterogeneous, seed=seed, n_tasks=n_tasks))
            rep_values.append(np.array(vals))
        mean, std = summarize_runs(rep_values)
        mean_series[alg] = mean
        std_series[alg] = std

    # AUDIT FIX: Post-hoc override removed.  All algorithms are now
    # evaluated on identical task streams, node populations, and noise
    # sequences.  Reference algorithms faithfully implement their paper
    # formulations:
    #   Ref[22] — OLB (Eq 4-11): traffic + computing load density model
    #   Ref[37] — SDN-GH (Eq 8): binary offloading with hierarchical capacity
    #   Ref[39] — DIST (Eq 16-17): reward-based with energy and reliability
    # All weights are configurable via config.py (Section 9).

    if heterogeneous:
        title = "Graph 6: Heterogeneous Fog Nodes"
        filename = "graph6_heterogeneous_fog_nodes"
        raw_file = "graph6_heterogeneous_fog_nodes.csv"
    else:
        title = "Graph 5: Homogeneous Fog Nodes"
        filename = "graph5_homogeneous_fog_nodes"
        raw_file = "graph5_homogeneous_fog_nodes.csv"

    save_csv(RAW_DIR / raw_file, "Number of Fog Nodes", node_counts, mean_series)
    plot_lines(
        node_counts,
        {k: (mean_series[k], std_series[k]) for k in algorithms},
        title,
        "Number of Fog Nodes",
        "Average Task Completion Latency (ms)",
        filename,
    )
    return mean_series
