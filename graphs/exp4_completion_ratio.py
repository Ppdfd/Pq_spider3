"""
Graph 9: Task Completion Ratio vs Failure Rate
===============================================
PQ-SPIDER2 Section VII-C: Fault-Tolerance and Secure Recovery Evaluation

Sweeps failure rate [5%, 10%, 15%, 20%, 25%] and measures the percentage
of tasks that complete successfully. All metrics emerge from the dynamic
heartbeat simulation in graph8._run_scenario().
"""

from typing import Dict

import numpy as np

import config
from utils.eval_utils import summarize_runs, save_csv, plot_lines, RAW_DIR

from graphs.exp3_recovery_latency import STRATEGY_NAMES, _run_scenario


def graph5_task_completion(rng: np.random.Generator, reps: int = None):
    """Graph 9: Task Completion Ratio vs Failure Rate.

    Includes all 6 strategies (including 'No FT' as lower bound).
    """
    if reps is None:
        reps = config.G9_REPS
    failure_rates = np.array(config.G9_FAILURE_RATES)
    n_fogs = config.G9_NUM_FOGS

    all_runs = {name: [] for name in STRATEGY_NAMES}

    for rep in range(reps):
        per_baseline = {name: [] for name in STRATEGY_NAMES}
        for fr in failure_rates:
            seed = int(rng.integers(0, 2**31)) + rep * 1000
            scenario = _run_scenario(n_fogs, float(fr), seed)
            for name in STRATEGY_NAMES:
                per_baseline[name].append(
                    scenario[name]["task_completion_ratio"] * 100.0
                )
        for name in STRATEGY_NAMES:
            all_runs[name].append(np.array(per_baseline[name]))

    data = {}
    plot_data = {}
    for name in STRATEGY_NAMES:
        mean, std = summarize_runs(all_runs[name])
        data[name] = mean
        plot_data[name] = (mean, std)

    x_labels = (failure_rates * 100).astype(int)

    save_csv(RAW_DIR / "graph5_task_completion.csv",
             "Failure Rate (%)", x_labels, data)
    plot_lines(
        x_labels, plot_data,
        "Graph 5: Task Completion Ratio vs Failure Rate",
        "Failure Rate (%)",
        "Task Completion Ratio (%)",
        "graph5_task_completion",
        ylim_bottom=50.0,
        ylim_top=100.0,
    )
    return data
