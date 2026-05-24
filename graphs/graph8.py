from typing import Dict, List, Tuple

import numpy as np

from utils.eval_utils import (
    GLOBAL_SEED, summarize_runs, save_csv, plot_lines, RAW_DIR
)
from phase4_load_balance.params import SIMULATION_PARAMS
from phase4_load_balance.models import Enclave, WorkloadTask, clone_enclaves
from phase4_load_balance.generators import (
    generate_tasks, generate_enclaves, _load_phase5_service_ms,
)
from phase4_load_balance.intra_node import (
    choose_enclave, execute_on_enclave, _drain_queues,
    simulate_intra_node,
)


def simulate_intra_node_detailed(
    n_tasks: int,
    algorithm: str,
    base_enclaves: List[Enclave],
    seed: int,
) -> Dict[str, np.ndarray]:
    """
    Run one intra-node scheduling experiment and record PER-TASK snapshots
    of all enclave state.  Returns dict of arrays for diagnostic plotting.

    This is the SINGLE simulation function used by all graph8+ diagnostic
    views (9).  Running once and plotting multiple views
    guarantees all graphs reflect the exact same experiment.

    Tracked metrics (per task):
      avg_queue      <- mean(enc.queue_length)
      avg_epc_pct    <- mean(enc.epc_available / enc.epc_total)
      min_epc_pct    <- min(epc%) across enclaves
      queue_std      <- std(queue_lengths)
      avg_contention <- max(enc.contention)
      latency        <- finish - arrival
      enc_ids        <- chosen enclave ID
      epc_swaps      <- 1 if EPC swap triggered, 0 otherwise
      deadline_met   <- 1 if latency <= deadline, 0 otherwise
      cache_reuse    <- enc.recent_count at time of selection
      arrivals       <- task.arrival_ms
      deadlines      <- task.deadline_ms
    """
    import config

    alg_offset = {"Round-Robin": 7, "Least-Queue": 19, "Spider (Ours)": 41}[algorithm]
    base_rng = np.random.default_rng(seed)
    rng = np.random.default_rng(seed + alg_offset)

    tasks = generate_tasks(
        n_tasks, base_rng,
        offered_load=getattr(config, 'INTRA_NODE_OFFERED_LOAD', 0.70),
    )
    enclaves = clone_enclaves(base_enclaves)
    epc_req = config.PACKET_EPC_BYTES * 28

    # ---- Per-task tracking arrays ----
    q_hist: List[float] = []
    epc_hist: List[float] = []
    q_std_hist: List[float] = []
    cont_hist: List[float] = []
    lat_hist: List[float] = []
    min_epc_hist: List[float] = []
    enc_ids: List[int] = []
    epc_swaps: List[int] = []
    deadline_met: List[int] = []
    cache_reuse: List[int] = []
    arrival_hist: List[float] = []
    deadline_hist: List[float] = []

    for i, task in enumerate(tasks):
        _drain_queues(enclaves, task.arrival_ms, epc_per_task=epc_req)
        enc = choose_enclave(enclaves, i, task, epc_req, algorithm, rng)

        # Record pre-execution state
        will_swap = 1 if enc.epc_available < epc_req else 0
        epc_swaps.append(will_swap)
        enc_ids.append(enc.enc_id)
        cache_reuse.append(enc.recent_count)
        arrival_hist.append(task.arrival_ms)
        deadline_hist.append(task.deadline_ms)

        # Execute
        latency = execute_on_enclave(enc, task, epc_req, rng)
        lat_hist.append(latency)
        deadline_met.append(1 if latency <= task.deadline_ms else 0)

        # Post-execution state snapshot
        qs = [e.queue_length for e in enclaves]
        epcs = [(e.epc_available / max(1.0, e.epc_total)) * 100.0
                for e in enclaves]
        conts = [e.contention for e in enclaves]

        q_hist.append(float(np.mean(qs)))
        epc_hist.append(float(np.mean(epcs)))
        min_epc_hist.append(float(np.min(epcs)))
        q_std_hist.append(float(np.std(qs)))
        cont_hist.append(float(np.max(conts)))

    return {
        "avg_queue": np.array(q_hist),
        "avg_epc_pct": np.array(epc_hist),
        "min_epc_pct": np.array(min_epc_hist),
        "queue_std": np.array(q_std_hist),
        "avg_contention": np.array(cont_hist),
        "latency": np.array(lat_hist),
        "enc_ids": np.array(enc_ids),
        "epc_swaps": np.array(epc_swaps),
        "deadline_met": np.array(deadline_met),
        "cache_reuse": np.array(cache_reuse),
        "arrivals": np.array(arrival_hist),
        "deadlines": np.array(deadline_hist),
    }


def graph8_intra_enclave(rng: np.random.Generator, reps: int = 10) -> Dict[str, np.ndarray]:
    """
    Graph 8: Intra-node Multi-Enclave Scheduling -- Heterogeneity Sweep.
    """
    import config
    from phase4_load_balance.optee_bench.loader import load_measurements

    N_ENCLAVES = getattr(config, 'G8_NUM_TEES', 4)
    n_tasks = getattr(config, 'G8_NUM_TASKS', 500)

    spread_factors = np.array(getattr(config, 'G8_SPREAD_FACTORS', [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]))
    algorithms = ["Round-Robin", "Least-Queue", "Spider (Ours)"]

    measurements = load_measurements(config)
    raw_rate = float(measurements.get("service_rate", config.MEASURED_SERVICE_RATE))
    base_rate = raw_rate / 1000.0
    measured_epc = float(measurements.get("epc_free", 2_097_152))

    mean_series: Dict[str, np.ndarray] = {}
    std_series: Dict[str, np.ndarray] = {}

    for alg in algorithms:
        rep_values: List[np.ndarray] = []
        for rep in range(reps):
            vals = []
            for spread in spread_factors:
                enc_rng = np.random.default_rng(
                    GLOBAL_SEED + 70000 + rep * 1000 + int(spread * 100)
                )
                rate_lo = base_rate / max(1.0, spread)
                rate_hi = base_rate * 1.0
                rates = np.linspace(rate_lo, rate_hi, N_ENCLAVES)

                controlled_enclaves: List[Enclave] = []
                for idx_e, r in enumerate(rates):
                    epc_lo, epc_hi = SIMULATION_PARAMS["epc_multiplier_range"]
                    epc_mult = float(enc_rng.uniform(epc_lo, epc_hi))
                    epc_total = measured_epc * epc_mult
                    if idx_e % 3 == 0:
                        epc_avail = epc_total * 0.90
                    elif idx_e % 3 == 1:
                        epc_avail = epc_total * 0.65
                    else:
                        epc_avail = epc_total * 0.40
                    controlled_enclaves.append(
                        Enclave(
                            enc_id=idx_e,
                            service_rate=max(0.05, float(r)),
                            epc_total=epc_total,
                            epc_available=epc_avail,
                            contention=0.0,
                            queue_length=0,
                            available_ms=0.0,
                            recent_count=0,
                            _finish_times=[],
                        )
                    )

                seed = GLOBAL_SEED + 70000 + 1000 * rep + 43 * int(spread * 100)
                vals.append(simulate_intra_node(n_tasks, alg, controlled_enclaves, seed=seed))
            rep_values.append(np.array(vals))
        mean, std = summarize_runs(rep_values)
        mean_series[alg] = mean
        std_series[alg] = std

    save_csv(RAW_DIR / "graph8_intra_node_enclaves.csv",
             "Speed Spread (max/min rate ratio)", spread_factors, mean_series)
    plot_lines(
        spread_factors,
        {k: (mean_series[k], std_series[k]) for k in algorithms},
        "Graph 8: Intra-node Scheduling under Enclave Heterogeneity",
        "Speed Spread (max/min rate ratio)",
        "Average Task Latency (ms)",
        "graph8_intra_node_scheduling",
    )
    return mean_series


def run_graph8_experiment(
    rng: np.random.Generator,
    n_tasks: int = 300,
) -> Tuple[Dict[str, Dict[str, np.ndarray]], List[Enclave]]:
    """
    Run ONE simulation per algorithm with SHARED enclaves.
    Returns (results, enclaves).
    """
    import config
    algorithms = ["Round-Robin", "Least-Queue", "Spider (Ours)"]
    num_tees = getattr(config, 'G8_NUM_TEES', 4)
    num_tasks = getattr(config, 'G8_NUM_TASKS', n_tasks)
    enclaves = generate_enclaves(num_tees, rng)

    results: Dict[str, Dict[str, np.ndarray]] = {}
    for alg in algorithms:
        results[alg] = simulate_intra_node_detailed(
            num_tasks, alg, enclaves, GLOBAL_SEED
        )

    return results, enclaves
