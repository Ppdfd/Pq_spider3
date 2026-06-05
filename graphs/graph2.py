import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR
)

@dataclass
class CacheNode:
    """Fog node properties for the cache/reuse-aware encryption simulation."""

    node_id: int
    speed: float
    tee_overhead_ms: float
    network_ms: float
    cache_capacity: int
    available_ms: float = 0.0


def make_cache_nodes(mode: str, rng: np.random.Generator) -> List[CacheNode]:
    """Create a fog cluster with slightly variable speed/network behavior."""

    import config
    num_fogs = getattr(config, 'G2_NUM_FOGS', 5)
    nodes: List[CacheNode] = []
    for node_id in range(num_fogs):
        speed = float(rng.normal(1.0, 0.07))
        tee_overhead = float(rng.normal(3.2, 0.35))
        network = float(rng.normal(7.0, 1.1))
        cap = 0 if mode == "no_cache" else 4

        nodes.append(CacheNode(node_id, speed, tee_overhead, network, cap))
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
    Simulate encryption tasks with ACTUAL in-memory CP-ABE execution.

    Caching uses collections.OrderedDict as an LRU cache per node, matching
    the paper's Cpolicy(T_ID) = (M, ρ_ID) from Eq 3-4 and Rreuse in Eq 39.
    On cache hit, the LSSS matrix is returned instantly; on miss, the full
    Lewko-Waters construction runs and is timed.

    A fixed deterministic key is used for encryption because the AES key
    value does not affect the cost of lattice operations.
    """
    from collections import OrderedDict
    import time as _time
    from crypto_primitives.cp_abe import LatticeCPABE

    rng = np.random.default_rng(seed)
    random.seed(seed)
    nodes = make_cache_nodes(mode, rng)

    SIM_N = 32
    FIXED_KEY = b'\x42' * 32

    # Pre-generate a pool of distinct policies (Zipf-distributed reuse)
    n_policies = 50
    all_attrs: set = set()
    policy_pool: List[Dict] = []
    for pid in range(n_policies):
        n_attr = int(rng.integers(5, 20))
        attrs = [f"Attr{i}" for i in range(n_attr)]
        all_attrs.update(attrs)
        policy_pool.append({"type": "AND", "attributes": attrs})

    # Per-node AA instances
    node_aa: List[LatticeCPABE] = []
    for _ in nodes:
        aa = LatticeCPABE(n=SIM_N, q=3329)
        aa.setup()
        for a in all_attrs:
            aa.hash_attribute(a)
            aa._ensure_attr(a)
        aa._get_A_float()
        node_aa.append(aa)

    # Per-node LRU cache using OrderedDict (standard library)
    # maxsize = node.cache_capacity (typically 4)
    node_caches: List[OrderedDict] = [OrderedDict() for _ in nodes]

    arrivals = np.sort(rng.uniform(0, 700.0, task_count))

    latencies: List[float] = []
    hits = 0

    for arrival in arrivals:
        policy_id = select_policy(rng)

        if mode == "no_cache":
            node_idx = int(np.argmin([
                max(0.0, n.available_ms - arrival) + n.network_ms
                for n in nodes
            ]))
        elif mode == "random_cache":
            scores = [max(0.0, n.available_ms - arrival) + n.network_ms + rng.normal(0.0, 1.0)
                      for n in nodes]
            node_idx = int(np.argmin(scores))
        else:  # spider_cache
            scores = []
            for ni, n in enumerate(nodes):
                q_delay = max(0.0, n.available_ms - arrival)
                # O(1) lookup — no side effects, no cache mutation
                import config
                penalty_ms = getattr(config, 'MEASURED_MARSHALING_MS', 5.0)
                miss_penalty = penalty_ms if policy_id not in node_caches[ni] else 0.0
                scores.append(q_delay + n.network_ms + miss_penalty + rng.normal(0.0, 1.0))
            node_idx = int(np.argmin(scores))

        node = nodes[node_idx]
        aa = node_aa[node_idx]
        cache = node_caches[node_idx]

        # Check cache hit/miss
        cache_hit = policy_id in cache

        t0 = _time.perf_counter()
        if mode == "no_cache" or not cache_hit:
            # COLD: build policy from scratch (timed)
            policy_pkg = aa.ree_build_policy(policy_pool[policy_id])
        else:
            # WARM: retrieve from OrderedDict LRU (instant)
            policy_pkg = cache[policy_id]
            cache.move_to_end(policy_id)  # mark as recently used

        tee_out = aa.tee_partial_encrypt(FIXED_KEY, policy_pkg)
        aa.ree_finalize_ct(policy_pkg, tee_out)
        elapsed_ms = (_time.perf_counter() - t0) * 1000.0

        hits += int(cache_hit)

        # Update LRU cache (for cache-enabled modes)
        if mode != "no_cache":
            cache[policy_id] = policy_pkg
            cache.move_to_end(policy_id)
            while len(cache) > node.cache_capacity:
                cache.popitem(last=False)  # evict LRU entry

        service_ms = (elapsed_ms / node.speed) * float(rng.lognormal(0.0, 0.06)) + node.tee_overhead_ms
        net_ms = max(0.2, node.network_ms + rng.normal(0.0, 0.9))

        start = max(arrival + net_ms, node.available_ms)
        finish = start + service_ms
        node.available_ms = finish
        latencies.append(float(finish - arrival))

    return float(np.mean(latencies)), float(hits / task_count)


def graph2_cache_reuse(rng: np.random.Generator, reps: int = 3) -> Dict[str, np.ndarray]:
    """Graph 2: reuse-aware cache scheduling latency vs. number of tasks."""

    import config
    tasks = getattr(config, 'G2_NUM_TASKS', np.arange(100, 1300, 100))
    if isinstance(tasks, int):
        tasks = [tasks]
    elif not isinstance(tasks, (list, np.ndarray)):
        tasks = list(tasks)
    modes = {
        "No Cache-Aware Scheduling": "no_cache",
        "Random Cache Placement": "random_cache",
        "Spider (Ours)": "spider_cache",
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

