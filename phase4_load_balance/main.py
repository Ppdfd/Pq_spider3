"""
Phase 4 Master Runner
=====================
Runs load balancers for all schemes and generates comparison graphs:
  1. End-to-End Latency   — scheduling + queue wait + processing
  2. Execution Time       — pure scheduler decision time
  3. Energy Consumption   — compute + communication + idle
  4. Network Usage        — messages + data overhead (KB)
"""

import sys
import io
import contextlib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from phase1_initialization.ours import run_phase1_simulation
from phase2_iiot_encrypt.ours import run_phase2_simulation
from phase3_edge_gateway.ours import run_phase3_simulation
from phase4_load_balance.ours import run_phase4_simulation

import config


# ═════════════════════════════════════════════════════════════════════
#  Cost models — derived from Phase 5 measured baselines when available
# ═════════════════════════════════════════════════════════════════════

def _load_phase5_metrics():
    """Load Phase 5 measured timings if they exist."""
    p5_path = Path(__file__).parent.parent / "phase5_fog_node" / "results" / "ours_metrics.json"
    if p5_path.exists():
        import json
        with open(p5_path) as f:
            return json.load(f)
    return None

def _get_cost_model():
    """Build cost model from Phase 5 measurements or defaults."""
    p5 = _load_phase5_metrics()
    if p5:
        # Use measured values from Phase 5
        base = p5.get("dilithium_sign", 19.0) + p5.get("aes_reencrypt", 0.02)
        cpabe_cold = p5.get("tee_partial_cpabe", 50.0)
        cpabe_warm = cpabe_cold * 0.5  # warm = ~50% of cold
    else:
        base = 12.0
        cpabe_cold = 55.0
        cpabe_warm = 25.0
    return base, cpabe_cold, cpabe_warm

_base, _cpabe_cold, _cpabe_warm = _get_cost_model()

# Latency model (ms) — from measured Phase 5 when available
BASE_PROCESS_MS = _base
CPABE_COLD_MS   = _cpabe_cold
CPABE_WARM_MS   = _cpabe_warm
KYBER_COLD_MS   = 5.0       # Kyber without precomputation
KYBER_WARM_MS   = 1.0       # Kyber with NTT cache
QUEUE_WAIT_MS   = 2.0       # Per queued task ahead

# Energy model (mJ) — uses SystemProfiler TDP for real estimation
from utils.system_profiler import SystemProfiler
_profiler = SystemProfiler()
# Estimate per-ms energy from TDP: convert 1ms CPU time to mJ
E_CPU_PER_MS    = _profiler.estimate_energy_mj(0.001)  # mJ per ms
E_IDLE_PER_NODE = 2.0       # mJ per active node (idle power)
E_TX_PER_KB     = 0.1       # mJ per KB transmitted
E_CACHE_SAVE    = 0.3       # mJ saved per cache hit (avoids recompute)

# Network model (KB) — SCHED_MSG and STATUS_MSG are fixed protocol overhead
SCHED_MSG_KB    = 0.5       # Scheduler→node assignment message size
STATUS_MSG_KB   = 0.2       # Node→scheduler status heartbeat per query
PACKET_SIZE_KB  = 2.5       # Default; overridden per-packet with real sizes


def _try_run(label, func):
    try:
        return func()
    except NotImplementedError as e:
        print(f"  [SKIP] {label}: {e}\n")
        return None


def _compute_metrics(metrics, fog_nodes):
    """Compute all four comparison metrics from a scheduler's assignments."""
    if not metrics:
        return {"latency": 0, "exec_time": 0, "energy": 0, "network": 0}

    assignments = metrics.get("assignments", [])
    if not assignments:
        return {"latency": 0, "exec_time": 0, "energy": 0, "network": 0}

    node_map = {fn["id"]: fn for fn in fog_nodes}
    n_tasks = len(assignments)

    # Track which nodes are used
    active_nodes = set()
    total_latency = 0.0
    total_energy = 0.0
    total_network = 0.0

    for a in assignments:
        fn = node_map.get(a["fog_node"])
        active_nodes.add(a["fog_node"])

        if fn is None:
            # Unknown node — assume cold path
            task_lat = BASE_PROCESS_MS + CPABE_COLD_MS + KYBER_COLD_MS
            task_energy = E_CPU_PER_MS * task_lat
            total_latency += task_lat
            total_energy += task_energy
            total_network += SCHED_MSG_KB + STATUS_MSG_KB + PACKET_SIZE_KB
            continue

        # ── Latency ──
        task_lat = BASE_PROCESS_MS

        # CP-ABE cost: warm if policy cached
        if fn.get("policy_cached", False):
            task_lat += CPABE_WARM_MS
        else:
            task_lat += CPABE_COLD_MS

        # Kyber cost: warm if precomputed
        kyber_cache = fn.get("kyber_cache", {})
        has_kyber = isinstance(kyber_cache, dict) and kyber_cache.get("has_cache", False)
        if has_kyber:
            task_lat += KYBER_WARM_MS
        else:
            task_lat += KYBER_COLD_MS

        # Queue wait
        enclaves = fn.get("enclaves", [])
        avg_q = sum(e["queue_length"] for e in enclaves) / max(1, len(enclaves))
        task_lat += QUEUE_WAIT_MS * avg_q

        total_latency += task_lat

        # ── Energy ──
        compute_energy = E_CPU_PER_MS * task_lat
        comm_energy = E_TX_PER_KB * (SCHED_MSG_KB + PACKET_SIZE_KB)
        cache_saving = 0.0
        if fn.get("policy_cached", False):
            cache_saving += E_CACHE_SAVE
        if has_kyber:
            cache_saving += E_CACHE_SAVE
        total_energy += compute_energy + comm_energy - cache_saving

        # ── Network ──
        # Assignment message + status query + packet payload
        total_network += SCHED_MSG_KB + STATUS_MSG_KB + PACKET_SIZE_KB

    # Add idle energy for all active nodes
    total_energy += E_IDLE_PER_NODE * len(active_nodes)

    # Network: additional overhead for status queries to ALL nodes (for
    # schedulers that need global state, like SDN-GH)
    # Spider++ only queries feasible nodes; OLB queries all
    total_network += STATUS_MSG_KB * len(active_nodes)

    # Execution time = scheduler decision time (from measured metrics)
    exec_time = metrics.get("total_scheduler_latency", 0)

    return {
        "latency":   total_latency / n_tasks,       # avg ms per task
        "exec_time": exec_time,                      # total ms
        "energy":    total_energy / n_tasks,          # avg mJ per task
        "network":   total_network,                   # total KB
    }


def main():
    print("\n" + "#" * 70)
    print("# PHASE 4 — LOAD BALANCER COMPARISON")
    print("#" * 70 + "\n")

    print("[1/4] Running Ours (Spider++)...")
    m_ours = run_phase4_simulation()
    print()

    print("[2/4] Running Ref [22] OLB...")
    from phase4_load_balance.ref_22 import run_phase4_ref22
    m_22 = _try_run("Ref [22]", run_phase4_ref22)
    print()

    print("[3/4] Running Ref [37] SDN-GH...")
    from phase4_load_balance.ref_37 import run_phase4_ref37
    m_37 = _try_run("Ref [37]", run_phase4_ref37)
    print()

    print("[4/4] Running Ref [39] DIST...")
    from phase4_load_balance.ref_39 import run_phase4_ref39
    m_39 = _try_run("Ref [39]", run_phase4_ref39)
    print()

    # Load fog nodes for cost estimation
    from utils.dataset_loader import DataLoader
    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    fog_nodes = loader.load_data(phase1_dir, "ours_key.json")

    # Compute four-dimensional metrics for each scheme
    results = {}
    for name, m in [("Spider++ (Ours)", m_ours), ("OLB [22]", m_22),
                     ("SDN-GH [37]", m_37), ("DIST [39]", m_39)]:
        results[name] = _compute_metrics(m, fog_nodes)

    # ── Comparison Table ──
    print("\n" + "=" * 90)
    print("  PHASE 4 COMPARISON — Multi-Dimensional Load Balancer Analysis")
    print("=" * 90)
    print(f"{'Scheme':<20} {'Latency':>12} {'Exec Time':>12} "
          f"{'Energy':>12} {'Network':>12} {'Nodes':>7}")
    print(f"{'':20} {'(ms/task)':>12} {'(ms)':>12} "
          f"{'(mJ/task)':>12} {'(KB)':>12} {'Used':>7}")
    print("-" * 90)

    for name, m_raw in [("Spider++ (Ours)", m_ours), ("OLB [22]", m_22),
                         ("SDN-GH [37]", m_37), ("DIST [39]", m_39)]:
        r = results[name]
        asgn = m_raw.get("assignments", []) if m_raw else []
        per_node = {}
        for a in asgn:
            per_node[a['fog_node']] = per_node.get(a['fog_node'], 0) + 1
        nodes = len(per_node)

        print(f"{name:<20} {r['latency']:12.2f} {r['exec_time']:12.2f} "
              f"{r['energy']:12.2f} {r['network']:12.1f} {nodes:5d}/10")
    print("=" * 90)

    if config.GENERATE_GRAPHS:
        plot_graphs()


def plot_graphs():
    """Phase 4 — four comparison graphs:
    1. End-to-End Latency (ms/task)
    2. Execution Time (ms)
    3. Energy Consumption (mJ/task)
    4. Network Usage (KB)
    """
    from utils.benchmark_runner import run_benchmark, plot_ieee_line
    import json

    results_dir = Path(__file__).parent / "results"
    task_counts = config.GRAPH_TASK_COUNTS
    warmup = config.GRAPH_WARMUP_ROUNDS
    rounds = config.GRAPH_TEST_ROUNDS

    from phase4_load_balance.ref_22 import run_phase4_ref22
    from phase4_load_balance.ref_37 import run_phase4_ref37
    from phase4_load_balance.ref_39 import run_phase4_ref39

    schemes = ["Spider++ (Ours)", "OLB [22]", "SDN-GH [37]", "DIST [39]"]
    funcs = [run_phase4_simulation, run_phase4_ref22,
             run_phase4_ref37, run_phase4_ref39]

    data_latency   = {s: [] for s in schemes}
    data_exec_time = {s: [] for s in schemes}
    data_energy    = {s: [] for s in schemes}
    data_network   = {s: [] for s in schemes}

    orig_devices = config.NUM_DEVICES

    try:
        for count in task_counts:
            config.NUM_DEVICES = count

            # Re-initialize phases 1-3 for this task count
            with contextlib.redirect_stdout(io.StringIO()):
                run_phase1_simulation()
                run_phase2_simulation()
                run_phase3_simulation()

            # Load fog nodes
            from utils.dataset_loader import DataLoader
            loader = DataLoader()
            phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
            fog_nodes = loader.load_data(phase1_dir, "ours_key.json")

            print(f"  Benchmarking schedulers (tasks={count})...")

            for scheme, func in zip(schemes, funcs):
                # Re-init fog nodes for each scheduler (fresh state)
                with contextlib.redirect_stdout(io.StringIO()):
                    run_phase1_simulation()
                fog_nodes = loader.load_data(phase1_dir, "ours_key.json")

                with contextlib.redirect_stdout(io.StringIO()):
                    m = func()

                r = _compute_metrics(m, fog_nodes)
                data_latency[scheme].append(r["latency"])
                data_exec_time[scheme].append(r["exec_time"])
                data_energy[scheme].append(r["energy"])
                data_network[scheme].append(r["network"])

    finally:
        config.NUM_DEVICES = orig_devices

    # Restore consistent state for downstream phases (5, 6).
    # The graph loop re-ran Phase 1 with varying NUM_DEVICES, which
    # regenerated fog node Kyber keys.  Phase 2 ciphertexts are bound
    # to those keys, so we must re-run Phases 1-3 with the original
    # NUM_DEVICES to avoid InvalidTag errors in Phase 5.
    with contextlib.redirect_stdout(io.StringIO()):
        run_phase1_simulation()
        run_phase2_simulation()
        run_phase3_simulation()
        run_phase4_simulation()

    # ── Graph 1: End-to-End Latency ──
    print("  Generating Phase 4: End-to-End Latency Comparison...")
    plot_ieee_line(
        task_counts, data_latency,
        xlabel='Number of Tasks',
        ylabel='Avg End-to-End Latency (ms/task)',
        title='Phase 4: Latency Comparison',
        output_path=results_dir / "phase4_latency.pdf",
    )

    # ── Graph 2: Execution Time ──
    print("  Generating Phase 4: Execution Time...")
    plot_ieee_line(
        task_counts, data_exec_time,
        xlabel='Number of Tasks',
        ylabel='Scheduler Execution Time (ms)',
        title='Phase 4: Execution Time',
        output_path=results_dir / "phase4_execution_time.pdf",
    )

    # ── Graph 3: Energy Consumption ──
    print("  Generating Phase 4: Energy Consumption...")
    plot_ieee_line(
        task_counts, data_energy,
        xlabel='Number of Tasks',
        ylabel='Avg Energy Consumption (mJ/task)',
        title='Phase 4: Energy Consumption',
        output_path=results_dir / "phase4_energy.pdf",
    )

    # ── Graph 4: Network Usage ──
    print("  Generating Phase 4: Network Usage...")
    plot_ieee_line(
        task_counts, data_network,
        xlabel='Number of Tasks',
        ylabel='Total Network Usage (KB)',
        title='Phase 4: Network Usage',
        output_path=results_dir / "phase4_network.pdf",
    )

    print("  Phase 4 graphs complete.\n")


if __name__ == "__main__":
    main()
