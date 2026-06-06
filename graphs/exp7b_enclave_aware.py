"""
Experiment 7 — Scenario 2: Impact of Enclave-Aware Scheduling
================================================================

Paper: "To isolate the contribution of enclave awareness, the
infrastructure is fixed to 20 fog nodes with four enclaves per node,
while the workload intensity is gradually increased to create different
levels of enclave contention."

Compares three Spider variants:
  - Spider-FogOnly:      inter-node Spider + random enclave
  - Spider-Heuristic:    inter-node Spider + least-queue enclave
  - Spider-EnclaveAware: inter-node Spider + full Eq 46 enclave scoring

X-axis: Workload intensity (offered load), increasing enclave contention.
Y-axis: Secure task-completion latency (ms).
Fixed: 20 fog nodes × 4 enclaves per node.

Expected: EnclaveAware < Heuristic < FogOnly, gap grows with contention.
"""

from typing import Dict

import numpy as np

import config
from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR,
)
from phase4_load_balance.exp7_simulation import simulate_two_level


# Map display names to enclave_strategy parameter
VARIANTS = {
    "Spider-FogOnly":      "random",
    "Spider-Heuristic":    "least-queue",
    "Spider-EnclaveAware": "spider",
}


def graph8_enclave_aware(rng: np.random.Generator) -> Dict[str, np.ndarray]:
    """Scenario 2: Enclave-aware scheduling under increasing contention."""

    num_fogs = config.EXP7_SC2_NUM_FOGS
    n_enclaves = config.EXP7_SC2_ENCLAVES_PER_FOG
    offered_loads = config.EXP7_SC2_OFFERED_LOADS
    n_tasks = config.EXP7_SC2_N_TASKS
    reps = config.EXP7_SC2_REPS
    variant_names = list(VARIANTS.keys())

    x = np.array(offered_loads)
    mean_series: Dict[str, np.ndarray] = {}
    std_series: Dict[str, np.ndarray] = {}

    for name, strategy in VARIANTS.items():
        rep_values = []
        for rep in range(reps):
            vals = []
            for li, load in enumerate(offered_loads):
                seed = GLOBAL_SEED + 77000 + 1000 * rep + 137 * li
                lat = simulate_two_level(
                    node_count=num_fogs,
                    n_enclaves_per_node=n_enclaves,
                    enclave_strategy=strategy,
                    seed=seed,
                    n_tasks=n_tasks,
                    offered_load=load,
                )
                vals.append(lat)
            rep_values.append(np.array(vals))
        mean, std = summarize_runs(rep_values)
        mean_series[name] = mean
        std_series[name] = std

    # Save raw data
    save_csv(
        RAW_DIR / "graph8_enclave_aware.csv",
        "Offered Load", x, mean_series,
    )

    # Plot
    plot_lines(
        x,
        {k: (mean_series[k], std_series[k]) for k in variant_names},
        "Graph 8: Impact of Enclave-Aware Scheduling",
        "Workload Intensity (Offered Load)",
        "Secure Task-Completion Latency (ms)",
        "graph8_enclave_aware",
        ylim_bottom=0.0,
    )

    print("  → Scenario 2 latency summary (ms at max load):")
    for name in variant_names:
        print(f"    {name:22s}: {mean_series[name][-1]:.1f} ms")

    return mean_series
