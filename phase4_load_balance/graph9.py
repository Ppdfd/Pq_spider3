from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import OUT_DIR
from phase4_load_balance.graph8 import Enclave


def graph9_queue_state(
    results: Dict[str, Dict[str, np.ndarray]],
    enclaves: List[Enclave],
) -> None:
    """Graph 9: Routing Intelligence — Task Distribution by Enclave Speed.

    Shows WHAT PERCENTAGE of tasks each algorithm routes to each enclave,
    with enclaves sorted by service rate (speed). Spider intelligently
    concentrates work on fast enclaves; LQ distributes based on queue count
    alone and wastes capacity on slow enclaves; RR is blind.

    Uses pre-computed results from run_graph8_experiment().
    """
    # Sort enclaves by service rate for labeling
    sorted_encs = sorted(enclaves, key=lambda e: e.service_rate)
    speed_labels = []
    for e in sorted_encs:
        speed_labels.append(f"Enc {e.enc_id}\n(rate={e.service_rate:.2f})")

    fig, ax = plt.subplots(figsize=(9, 5))
    n_enc = len(enclaves)
    bar_width = 0.22
    x_pos = np.arange(n_enc)
    colors = {"Round-Robin": "#E8734A", "Least-Queue": "#4CAF50", "Spider (Ours)": "#2196F3"}
    algorithms = list(results.keys())
    n_tasks = len(list(results.values())[0]["enc_ids"])

    for j, alg in enumerate(algorithms):
        enc_ids = results[alg]["enc_ids"]
        counts = []
        for e in sorted_encs:
            counts.append(np.sum(enc_ids == e.enc_id))
        pcts = np.array(counts) / n_tasks * 100.0
        offset = (j - 1) * bar_width
        ax.bar(x_pos + offset, pcts, bar_width, label=alg,
               color=colors[alg], alpha=0.85, edgecolor="white", linewidth=0.5)

    ax.set_title("Graph 9: Routing Intelligence — Task Distribution by Enclave Speed", fontsize=13)
    ax.set_xlabel("Enclave (sorted by service rate, slow → fast)", fontsize=11)
    ax.set_ylabel("Tasks Routed (%)", fontsize=11)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(speed_labels, fontsize=9)
    ax.axhline(y=25.0, color="gray", linestyle="--", alpha=0.4, label="Uniform (25%)")
    ax.legend(fontsize=10)
    ax.grid(True, axis="y", linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "graph9_queue_state.png", dpi=300)
    plt.close(fig)
