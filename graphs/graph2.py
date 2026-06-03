import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR
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

    import config
    num_fogs = getattr(config, 'G2_NUM_FOGS', 5)
    nodes: List[CacheNode] = []
    for node_id in range(num_fogs):
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

# ── Pre-measured CP-ABE encryption cost table ──
# Derived from actual LatticeCPABE.encrypt() calls, NOT hardcoded.
# generate_graphs.md: "Never assume the runtime...
# the code must run logic to get the runtime."
_CPABE_COST_TABLE: dict | None = None

# ── Measured cache speedup factor ──
_CACHE_FACTOR: float | None = None


def _measure_cache_factor() -> float:
    """Measure actual speedup from cached LSSS policy vs cold-start encrypt.

    Returns the ratio warm_time / cold_time (< 1.0 means cache is faster).
    """
    import os
    import time as _time
    from crypto_primitives.cp_abe import LatticeCPABE

    global _CACHE_FACTOR
    if _CACHE_FACTOR is not None:
        return _CACHE_FACTOR

    n_attr = 20
    universe = [f"Attr{i}" for i in range(n_attr)]
    policy = {"type": "AND", "attributes": universe}
    aa = LatticeCPABE(n=256, q=3329)
    aa.setup()
    for a in universe:
        aa.hash_attribute(a)
    aa.keygen({}, universe)

    n_warmup, n_measure = 2, 5

    # Cold: clear all caches each time (Ref[4] stateless model)
    for _ in range(n_warmup):
        aa._A_float = None; aa._sec.clear(); aa._pub.clear()
        aa.encrypt(os.urandom(32), policy)
    cold_times = []
    for _ in range(n_measure):
        aa._A_float = None; aa._sec.clear(); aa._pub.clear()
        t0 = _time.perf_counter()
        aa.encrypt(os.urandom(32), policy)
        cold_times.append(_time.perf_counter() - t0)

    # Warm: caches populated (Spider persistent enclave model)
    policy_pkg = aa.ree_build_policy(policy)
    aa._get_A_float()
    for _ in range(n_warmup):
        tee_out = aa.tee_partial_encrypt(os.urandom(32), policy_pkg)
        aa.ree_finalize_ct(policy_pkg, tee_out)
    warm_times = []
    for _ in range(n_measure):
        t0 = _time.perf_counter()
        tee_out = aa.tee_partial_encrypt(os.urandom(32), policy_pkg)
        aa.ree_finalize_ct(policy_pkg, tee_out)
        warm_times.append(_time.perf_counter() - t0)

    _CACHE_FACTOR = float(np.median(warm_times) / max(1e-9, np.median(cold_times)))
    print(f"  [graph2] Measured cache_factor = {_CACHE_FACTOR:.3f}")
    return _CACHE_FACTOR


def _measure_cpabe_costs() -> Tuple[np.ndarray, np.ndarray]:
    """
    Pre-measure actual CP-ABE encryption cost for representative
    attribute counts.  Results are cached for the lifetime of the
    process so the simulation can interpolate without re-running
    crypto for every task.
    """
    import os
    import time as _time
    from crypto_primitives.cp_abe import LatticeCPABE

    global _CPABE_COST_TABLE
    if _CPABE_COST_TABLE is not None:
        return _CPABE_COST_TABLE["attrs"], _CPABE_COST_TABLE["times"]

    sample_attrs = np.array([5, 10, 15, 20, 25, 30, 35, 40, 45, 50])
    measured_times = np.zeros(len(sample_attrs))
    n_warmup = 1
    n_measure = 3

    for idx, n_attr in enumerate(sample_attrs):
        universe = [f"Attr{i}" for i in range(int(n_attr))]
        policy = {"type": "AND", "attributes": universe}
        aa = LatticeCPABE(n=256, q=3329)
        aa.setup()
        for a in universe:
            aa.hash_attribute(a)
        aa.keygen({}, universe)

        # Warm up CPU caches
        for _ in range(n_warmup):
            aa.encrypt(os.urandom(32), policy)

        # Measure
        times = []
        for _ in range(n_measure):
            k = os.urandom(32)
            t0 = _time.perf_counter()
            aa.encrypt(k, policy)
            times.append((_time.perf_counter() - t0) * 1000)
        measured_times[idx] = float(np.median(times))

    _CPABE_COST_TABLE = {"attrs": sample_attrs, "times": measured_times}
    return sample_attrs, measured_times


def simulate_cache_latency(task_count: int, mode: str, seed: int) -> Tuple[float, float]:
    """
    Simulate encryption tasks under no-cache, random-cache, and Spider reuse-aware
    cache placement.  Increasing task_count raises offered load and queue buildup.
    """

    rng = np.random.default_rng(seed)
    random.seed(seed)
    nodes = make_cache_nodes(mode, rng)
    arrivals = np.sort(rng.uniform(0, 700.0, task_count))

    # Derive service time from measured CP-ABE crypto (not hardcoded)
    ref_attrs, ref_times = _measure_cpabe_costs()

    latencies: List[float] = []
    hits = 0

    for arrival in arrivals:
        attrs = int(rng.integers(8, 46))
        policy_id = select_policy(rng)
        cpabe_base = float(np.interp(attrs, ref_attrs, ref_times))

        if mode == "no_cache":
            node = min(nodes, key=lambda n: max(0.0, n.available_ms - arrival) + n.network_ms)
            cache_hit = False
        elif mode == "random_cache":
            scores = [max(0.0, n.available_ms - arrival) + n.network_ms + rng.normal(0.0, 1.0) for n in nodes]
            node = nodes[int(np.argmin(scores))]
            cache_hit = node.has_policy(policy_id)
        else:
            def spider_score(n: CacheNode) -> float:
                q_delay = max(0.0, n.available_ms - arrival)
                miss_penalty = 10.5 if not n.has_policy(policy_id) else 0.0
                return q_delay + n.network_ms + miss_penalty + rng.normal(0.0, 1.0)

            node = min(nodes, key=spider_score)
            cache_hit = node.has_policy(policy_id)

        hits += int(cache_hit)

        cache_factor = _measure_cache_factor() if cache_hit else 1.00
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

