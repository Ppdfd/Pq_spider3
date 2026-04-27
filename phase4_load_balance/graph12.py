from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import OUT_DIR
from phase4_load_balance.graph8 import Enclave


def graph12_load_imbalance(
    results: Dict[str, Dict[str, np.ndarray]],
    enclaves: List[Enclave],
) -> None:
    """Graph 12: Latency CDF — Cumulative Distribution of Per-Task Latency.

    Shows the FULL distribution of task completion times. A steeper CDF
    (further left) means more tasks finish quickly. Spider++ should have
    the steepest curve, demonstrating consistently low latency.

    Uses pre-computed results from run_graph8_experiment().
    """
    colors = {"Round-Robin": "#E8734A", "Least-Queue": "#4CAF50", "Spider++ (Ours)": "#2196F3"}

    fig, ax = plt.subplots(figsize=(8, 5))

    for alg, res in results.items():
        latencies = np.sort(res["latency"])
        cdf = np.arange(1, len(latencies) + 1) / len(latencies)
        ax.plot(latencies, cdf, linewidth=2, label=alg, color=colors[alg])

    ax.set_title("Graph 12: Latency CDF — Per-Task Completion Time", fontsize=14)
    ax.set_xlabel("Task Completion Latency (ms)", fontsize=12)
    ax.set_ylabel("Cumulative Fraction of Tasks", fontsize=12)
    ax.set_xlim(left=0)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(fontsize=11, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "graph12_load_imbalance.png", dpi=300)
    plt.close(fig)
