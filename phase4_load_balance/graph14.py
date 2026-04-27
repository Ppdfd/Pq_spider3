from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import OUT_DIR
from phase4_load_balance.graph8 import Enclave


def graph14_cache_reuse(
    results: Dict[str, Dict[str, np.ndarray]],
    enclaves: List[Enclave],
) -> None:
    """Graph 14: Cache Affinity — Running Average of Enclave Reuse Count.

    When a task is assigned to an enclave that recently processed similar
    work, the enclave's caches are warm (Eq 45: A_affin). This graph shows
    the running average of enc.recent_count at time of selection.
    Spider++ should show higher reuse because Eq 45 explicitly rewards
    affinity; RR and LQ ignore cache state.

    Uses pre-computed results from run_graph8_experiment().
    """
    colors = {"Round-Robin": "#E8734A", "Least-Queue": "#4CAF50", "Spider++ (Ours)": "#2196F3"}

    fig, ax = plt.subplots(figsize=(8, 5))

    for alg, res in results.items():
        reuse = res["cache_reuse"].astype(float)
        # Compute running average with window=20 for smoothing
        window = min(20, len(reuse))
        running_avg = np.convolve(reuse, np.ones(window) / window, mode="valid")
        x_axis = np.arange(window, len(reuse) + 1)
        ax.plot(x_axis, running_avg, linewidth=2, label=alg, color=colors[alg])

    ax.set_title("Graph 14: Cache Affinity — Enclave Reuse at Selection", fontsize=14)
    ax.set_xlabel("Task Index", fontsize=12)
    ax.set_ylabel("Running Avg. Recent Count (window=20)", fontsize=12)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "graph14_cache_reuse.png", dpi=300)
    plt.close(fig)
