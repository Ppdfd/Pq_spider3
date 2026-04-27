from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import GLOBAL_SEED, OUT_DIR, RAW_DIR, save_csv
from phase4_load_balance.graph8 import (
    SIMULATION_PARAMS, generate_enclaves, simulate_intra_node,
)


def graph10_sensitivity(rng: np.random.Generator) -> None:
    """Graph 10: Parameter Sensitivity Analysis (2-panel).

    Sweeps the two most influential simulation parameters independently
    to demonstrate that Spider's advantage is robust and not an artifact
    of specific parameter choices.

    Panel A: Varies EPC swap cost from 0ms to 20ms (holding contention fixed)
    Panel B: Varies contention cost from 0ms to 3ms (holding EPC swap fixed)

    This graph is the primary defense against the reviewer critique:
    "The authors tuned their parameters to guarantee their algorithm wins."
    """
    import config
    from phase4_load_balance.optee_bench.loader import load_measurements

    n_tasks = config.STRESS_DIAGNOSTIC_N_TASKS
    algorithms = ["Round-Robin", "Least-Queue", "Spider (Ours)"]
    colors = {"Round-Robin": "#E8734A", "Least-Queue": "#4CAF50", "Spider (Ours)": "#2196F3"}

    base_enclaves = generate_enclaves(4, rng)

    # Save original params so we can restore after sweeps
    orig_epc_range = SIMULATION_PARAMS["epc_swap_range"]
    orig_epc_base = SIMULATION_PARAMS["epc_swap_base_ms"]
    orig_cont = SIMULATION_PARAMS["contention_per_unit_ms"]

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14, 5))

    # ── Panel A: Sweep EPC Swap Cost ──
    epc_sweep = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 20.0, 24.0]
    panel_a: Dict[str, List[float]] = {alg: [] for alg in algorithms}

    for epc_cost in epc_sweep:
        # Set symmetric range around the sweep value
        half_spread = max(0.5, epc_cost * 0.4)
        SIMULATION_PARAMS["epc_swap_range"] = (
            max(0.0, epc_cost - half_spread),
            epc_cost + half_spread,
        )
        SIMULATION_PARAMS["epc_swap_base_ms"] = epc_cost

        for alg in algorithms:
            lat = simulate_intra_node(n_tasks, alg, base_enclaves, GLOBAL_SEED)
            panel_a[alg].append(lat)

    # Restore
    SIMULATION_PARAMS["epc_swap_range"] = orig_epc_range
    SIMULATION_PARAMS["epc_swap_base_ms"] = orig_epc_base

    for alg in algorithms:
        ax_a.plot(epc_sweep, panel_a[alg], linewidth=2, marker="o",
                  markersize=5, label=alg, color=colors[alg])

    # Mark the cited value
    cited_epc = orig_epc_base
    ax_a.axvline(x=cited_epc, color="gray", linestyle="--", alpha=0.5,
                 label=f"Cited value ({cited_epc}ms)")
    ax_a.set_title("Panel A: Sensitivity to EPC Swap Cost", fontsize=13)
    ax_a.set_xlabel("EPC Swap Penalty (ms)", fontsize=11)
    ax_a.set_ylabel("Average Task Latency (ms)", fontsize=11)
    ax_a.legend(fontsize=9)
    ax_a.grid(True, linestyle="--", alpha=0.3)

    # ── Panel B: Sweep Contention Cost ──
    cont_sweep = [0.0, 0.25, 0.5, 0.75, 1.0, 1.13, 1.5, 2.0, 3.0]
    panel_b: Dict[str, List[float]] = {alg: [] for alg in algorithms}

    for cont_cost in cont_sweep:
        SIMULATION_PARAMS["contention_per_unit_ms"] = cont_cost

        for alg in algorithms:
            lat = simulate_intra_node(n_tasks, alg, base_enclaves, GLOBAL_SEED)
            panel_b[alg].append(lat)

    # Restore
    SIMULATION_PARAMS["contention_per_unit_ms"] = orig_cont

    for alg in algorithms:
        ax_b.plot(cont_sweep, panel_b[alg], linewidth=2, marker="s",
                  markersize=5, label=alg, color=colors[alg])

    # Mark the cited value
    ax_b.axvline(x=orig_cont, color="gray", linestyle="--", alpha=0.5,
                 label=f"Cited value ({orig_cont}ms)")
    ax_b.set_title("Panel B: Sensitivity to Contention Cost", fontsize=13)
    ax_b.set_xlabel("Contention Penalty per Unit Load (ms)", fontsize=11)
    ax_b.set_ylabel("Average Task Latency (ms)", fontsize=11)
    ax_b.legend(fontsize=9)
    ax_b.grid(True, linestyle="--", alpha=0.3)

    fig.suptitle("Graph 10: Parameter Sensitivity Analysis", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "graph10_sensitivity.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # Also save raw data
    save_csv(
        RAW_DIR / "graph10_epc_sensitivity.csv",
        "EPC_Swap_Cost_ms", epc_sweep,
        {alg: np.array(panel_a[alg]) for alg in algorithms},
    )
    save_csv(
        RAW_DIR / "graph10_contention_sensitivity.csv",
        "Contention_Per_Unit_ms", cont_sweep,
        {alg: np.array(panel_b[alg]) for alg in algorithms},
    )
