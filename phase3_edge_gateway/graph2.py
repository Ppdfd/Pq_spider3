import os
import csv
import hashlib as _hashlib
import json
import math
import random
import sys as _sys
import tempfile
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import (
    GLOBAL_SEED, PLOT, MARKERS, SCHEME_STYLES, OUT_DIR, RAW_DIR, ROOT_DIR,
    set_global_seed, ensure_dirs, configure_matplotlib, summarize_runs,
    save_csv, plot_lines, plot_bar, save_csv_simple, noisy_curve, ar1_noise
)

@dataclass
class CacheNode:
    """Fog node used in the cache/reuse-aware encryption simulation."""

    node_id: int
    speed: float
    tee_overhead_ms: float
    network_ms: float
    cache_capacity: int
    cache: List[int] = field(default_factory=list)
    available_ms: float = 0.0

    def has_policy(self, policy_id: int) -> bool:
        return policy_id in self.cache

    def touch_policy(self, policy_id: int) -> None:
        """LRU-style policy-cache update."""

        if self.cache_capacity <= 0:
            return
        if policy_id in self.cache:
            self.cache.remove(policy_id)
        self.cache.append(policy_id)
        while len(self.cache) > self.cache_capacity:
            self.cache.pop(0)


def make_cache_nodes(mode: str, rng: np.random.Generator) -> List[CacheNode]:
    """Create a fog cluster with slightly variable speed/network behavior."""

    nodes: List[CacheNode] = []
    for node_id in range(5):
        speed = float(rng.normal(1.0, 0.07))
        tee_overhead = float(rng.normal(3.2, 0.35))
        network = float(rng.normal(7.0, 1.1))

        if mode == "no_cache":
            cap, preload = 0, []
        elif mode == "random_cache":
            cap, preload = 4, random.sample(range(50), 4)
        elif mode == "spider_cache":
            cap = 4
            preload = random.sample(range(50), 4)
        else:
            raise ValueError(mode)

        nodes.append(CacheNode(node_id, speed, tee_overhead, network, cap, preload))
    return nodes


def select_policy(rng: np.random.Generator) -> int:
    """Zipf-like policy locality: a few policies are reused frequently."""
    n_policies = 50
    policies = np.arange(n_policies)
    # Zipf distribution: P(x) ~ 1 / x^s
    s = 1.05
    weights = 1.0 / (np.arange(1, n_policies + 1) ** s)
    return int(rng.choice(policies, p=weights / weights.sum()))


MODE_SEED_OFFSET = {
    "no_cache": 101,
    "random_cache": 211,
    "spider_cache": 307,
}


def simulate_cache_latency(task_count: int, mode: str, seed: int) -> Tuple[float, float]:
    """
    Simulate encryption tasks under no-cache, random-cache, and Spider++ reuse-aware
    cache placement.  Increasing task_count raises offered load and queue buildup.
    """

    rng = np.random.default_rng(seed)
    random.seed(seed)
    nodes = make_cache_nodes(mode, rng)
    arrivals = np.sort(rng.uniform(0, 700.0, task_count))

    latencies: List[float] = []
    hits = 0

    for arrival in arrivals:
        attrs = int(rng.integers(8, 46))
        policy_id = select_policy(rng)
        cpabe_base = 8.5 + 0.34 * attrs + 0.0065 * (attrs ** 2)

        if mode == "no_cache":
            node = min(nodes, key=lambda n: max(0.0, n.available_ms - arrival) + n.network_ms)
            cache_hit = False
        elif mode == "random_cache":
            scores = [max(0.0, n.available_ms - arrival) + n.network_ms + rng.normal(0.0, 1.8) for n in nodes]
            node = nodes[int(np.argmin(scores))]
            cache_hit = node.has_policy(policy_id)
        else:
            def spider_score(n: CacheNode) -> float:
                q_delay = max(0.0, n.available_ms - arrival)
                miss_penalty = 10.5 if not n.has_policy(policy_id) else 0.0
                return q_delay + n.network_ms + miss_penalty + rng.normal(0.0, 0.7)

            node = min(nodes, key=spider_score)
            cache_hit = node.has_policy(policy_id)

        hits += int(cache_hit)

        cache_factor = 0.68 if cache_hit else 1.00
        service_ms = (cpabe_base * cache_factor / node.speed) * float(rng.lognormal(0.0, 0.06)) + node.tee_overhead_ms
        net_ms = max(0.2, node.network_ms + rng.normal(0.0, 0.9))

        start = max(arrival + net_ms, node.available_ms)
        finish = start + service_ms
        node.available_ms = finish
        if mode in ("spider_cache", "random_cache"):
            node.touch_policy(policy_id)
        latencies.append(float(finish - arrival))

    return float(np.mean(latencies)), float(hits / task_count)


def graph2_cache_reuse(rng: np.random.Generator, reps: int = 3) -> Dict[str, np.ndarray]:
    """Graph 2: reuse-aware cache scheduling latency vs. number of tasks."""

    tasks = np.arange(100, 1300, 100)
    modes = {
        "No Cache-Aware Scheduling": "no_cache",
        "Random Cache Placement": "random_cache",
        "Spider++ (Ours)": "spider_cache",
    }

    mean_series: Dict[str, np.ndarray] = {}
    std_series: Dict[str, np.ndarray] = {}
    hit_series: Dict[str, np.ndarray] = {}

    for label, mode in modes.items():
        values: List[np.ndarray] = []
        hits: List[np.ndarray] = []
        for rep in range(reps):
            vals, hit_vals = [], []
            for task_count in tasks:
                avg, hit = simulate_cache_latency(
                    int(task_count),
                    mode,
                    seed=GLOBAL_SEED + MODE_SEED_OFFSET[mode] + 1000 * rep + int(task_count),
                )
                vals.append(avg)
                hit_vals.append(hit)
            values.append(np.array(vals))
            hits.append(np.array(hit_vals))

        mean, std = summarize_runs(values)
        hit_mean, _ = summarize_runs(hits)
        mean_series[label] = mean
        std_series[label] = std
        hit_series[label] = hit_mean

    save_csv(RAW_DIR / "graph2_cache_reuse_latency.csv", "Number of Tasks", tasks, mean_series)
    save_csv(RAW_DIR / "graph2_cache_hit_rate_auxiliary.csv", "Number of Tasks", tasks, hit_series)
    plot_lines(
        tasks,
        {k: (mean_series[k], std_series[k]) for k in modes.keys()},
        "Graph 2: Cache / Reuse-Aware Scheduling",
        "Number of Tasks",
        "Average Encryption Latency per Task (ms)",
        "graph2_cache_reuse_scheduling",
    )
    return mean_series

