from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import OUT_DIR
from phase4_load_balance.graph8 import Enclave


def graph11_epc_availability(
    results: Dict[str, Dict[str, np.ndarray]],
    enclaves: List[Enclave],
) -> None:
    """Graph 11: Cumulative EPC Swap Events vs Task Arrivals.

    Counts how many tasks trigger expensive EPC page swapping (because
    the chosen enclave was memory-depleted). Spider++ PROACTIVELY avoids
    depleted enclaves via Eq 43 (P_epc), resulting in fewer swap events.

    Uses pre-computed results from run_graph8_experiment().
    """
    colors = {"Round-Robin": "#E8734A", "Least-Queue": "#4CAF50", "Spider++ (Ours)": "#2196F3"}
    n_tasks = len(list(results.values())[0]["epc_swaps"])

    fig, ax = plt.subplots(figsize=(8, 5))
    x_axis = np.arange(1, n_tasks + 1)

    for alg, res in results.items():
        cumulative = np.cumsum(res["epc_swaps"])
        ax.plot(x_axis, cumulative, linewidth=2, label=alg, color=colors[alg])

    ax.set_title("Graph 11: Cumulative EPC Swap Events", fontsize=14)
    ax.set_xlabel("Task Arrival Index", fontsize=12)
    ax.set_ylabel("Total EPC Page Swaps (cumulative)", fontsize=12)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "graph11_epc_availability.png", dpi=300)
    plt.close(fig)
