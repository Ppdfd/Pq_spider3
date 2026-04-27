from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import OUT_DIR
from phase4_load_balance.graph8 import Enclave


def graph13_deadline(
    results: Dict[str, Dict[str, np.ndarray]],
    enclaves: List[Enclave],
) -> None:
    """Graph 13: Deadline Compliance — % of Tasks Meeting Deadline.

    Each task has a randomly assigned deadline (85–230ms). This graph shows
    what fraction of tasks each algorithm completes within the deadline.
    Spider++ should achieve the highest compliance rate because its
    completion-time estimates (Eq 46) actively minimize latency.

    Uses pre-computed results from run_graph8_experiment().
    """
    colors = {"Round-Robin": "#E8734A", "Least-Queue": "#4CAF50", "Spider++ (Ours)": "#2196F3"}
    algorithms = list(results.keys())

    met_pcts = []
    for alg in algorithms:
        met = results[alg]["deadline_met"]
        met_pcts.append(float(np.mean(met) * 100.0))

    fig, ax = plt.subplots(figsize=(7, 5))
    x = np.arange(len(algorithms))
    bar_colors = [colors[a] for a in algorithms]
    bars = ax.bar(x, met_pcts, color=bar_colors, width=0.5, edgecolor="white", linewidth=0.5)

    for bar, pct in zip(bars, met_pcts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{pct:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_title("Graph 13: Deadline Compliance Rate", fontsize=14)
    ax.set_ylabel("Tasks Meeting Deadline (%)", fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(algorithms, fontsize=11)
    ax.set_ylim(0, 105)
    ax.axhline(y=100, color="gray", linestyle="--", alpha=0.3)
    ax.grid(True, axis="y", linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "graph13_deadline.png", dpi=300)
    plt.close(fig)
