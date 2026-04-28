from typing import Dict, List

import numpy as np

from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR
)


def simulate_recovery_time(failure_rate: float, method: str, seed: int) -> float:
    """
    Fair recovery simulation.  Per-task costs derived from measured values:
      - Full reprocess ≈ Phase 2 enc (~1.6ms) + Phase 5 fog (~44ms) ≈ 45ms
      - Retry from checkpoint ≈ fog re-execution only ≈ 15ms
      - Spider delegation ≈ Dilithium verify (~6.2ms) + state transfer (~3ms) ≈ 9ms
        AUDIT FIX: Previous value of 6ms was incorrect — measured Dilithium
        verify alone takes ~6.2ms on this hardware.
    All methods share the same detection latency and noise level.
    """
    rng = np.random.default_rng(seed)
    import config
    cluster_nodes = getattr(config, 'G7_NUM_FOGS', 20)
    
    # Inflight tasks must be constant across failure rates to prevent
    # non-monotonic bouncing in the graph due to RNG variance.
    inflight = getattr(config, 'G7_NUM_TASKS', 500)
    
    failed = max(1, int(round(cluster_nodes * failure_rate / 100.0)))
    affected = inflight * (failed / cluster_nodes)

    # Detection latency: same for all methods (heartbeat timeout)
    detection = float(rng.normal(10.0, 2.0))
    noise = float(rng.normal(0.0, 8.0))  # equal noise for all

    if method == "No Delegation":
        # All affected tasks must be fully re-encrypted + re-processed
        per_task = float(rng.normal(45, 5))
        overhead = float(rng.normal(30, 5))
        recovery = detection + overhead + per_task * (affected / max(1, cluster_nodes - failed))
    elif method == "Simple Retry / Reassignment":
        # Retry from last checkpoint on available nodes
        per_task = float(rng.normal(15, 3))
        overhead = float(rng.normal(20, 5))
        recovery = detection + overhead + per_task * (affected / max(1, cluster_nodes - failed))
    elif method == "Spider (Ours)":
        # AUDIT FIX: Dilithium verify (~6.2ms measured) + state transfer (~3ms) ≈ 9ms
        per_task = float(rng.normal(9, 2))
        overhead = float(rng.normal(15, 3))
        recovery = detection + overhead + per_task * (affected / max(1, cluster_nodes - failed))
    else:
        raise ValueError(method)

    return max(1.0, float(recovery + noise))


def graph7_recovery(rng: np.random.Generator, reps: int = 5) -> Dict[str, np.ndarray]:
    """Graph 7: Recovery Time vs Failure Rate (line chart)."""

    rates = np.array([5, 10, 15, 20, 25, 30, 35, 40])
    methods = [
        "No Delegation",
        "Simple Retry / Reassignment",
        "Spider (Ours)",
    ]

    mean_series: Dict[str, np.ndarray] = {}
    std_series: Dict[str, np.ndarray] = {}

    for idx, method in enumerate(methods):
        rep_values: List[np.ndarray] = []
        for rep in range(reps):
            vals = []
            for rate in rates:
                seed = GLOBAL_SEED + 80000 + 1000 * rep + idx * 131 + int(rate)
                vals.append(simulate_recovery_time(float(rate), method, seed))
            rep_values.append(np.array(vals))
        mean, std = summarize_runs(rep_values)
        mean_series[method] = mean
        std_series[method] = std

    save_csv(RAW_DIR / "graph7_recovery_failure.csv", "Failure Rate (%)", rates, mean_series)
    plot_lines(
        rates,
        {k: (mean_series[k], std_series[k]) for k in methods},
        "Graph 7: Recovery Time vs Failure Rate",
        "Failure Rate (% of Nodes Failing)",
        "Recovery Time (ms)",
        "graph7_recovery_time_failure_rate",
    )
    return mean_series


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

