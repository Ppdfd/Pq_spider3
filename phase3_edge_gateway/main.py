"""
Phase 3 Master Runner
=====================
Runs Edge Gateway Validation (Ours only — competitor schemes do
not have an analogous gateway-validation phase).

Optionally generates scalability PDF graphs (controlled by config.GENERATE_GRAPHS).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from phase1_initialization.ours import run_phase1_simulation
from phase2_iiot_encrypt.ours import run_phase2_simulation
from phase3_edge_gateway.ours import run_phase3_simulation

import config


def main():
    print("\n" + "#" * 70)
    print("# PHASE 3 — EDGE GATEWAY VALIDATION  (Ours only)")
    print("#" * 70 + "\n")
    run_phase3_simulation()

    if config.GENERATE_GRAPHS:
        plot_graphs()


def plot_graphs():
    """
    Generate Phase 3 scalability graph (IEEE-style PDF).

    Graph: Gateway Latency vs Batch Task Count (Ours only)
    """
    from utils.benchmark_runner import run_benchmark, plot_ieee_line

    results_dir = Path(__file__).parent / "results"
    task_counts = config.GRAPH_TASK_COUNTS
    warmup = config.GRAPH_WARMUP_ROUNDS
    rounds = config.GRAPH_TEST_ROUNDS

    print("\n  Generating Phase 3: Gateway Latency vs Task Count...")
    results = []
    orig_devices = config.NUM_DEVICES

    try:
        for count in task_counts:
            config.NUM_DEVICES = count

            def setup():
                run_phase1_simulation()
                run_phase2_simulation()

            avg = run_benchmark(
                run_phase3_simulation, rounds, warmup,
                extract_metric=lambda m: m["total_gateway_latency"],
                setup_fn=setup,
            )
            results.append(avg)
    finally:
        config.NUM_DEVICES = orig_devices

    plot_ieee_line(
        task_counts, {"Gateway Processing (Ours)": results},
        xlabel='Number of Batch Tasks (Device Density)',
        ylabel='Total Gateway Proxy Latency (ms)',
        title='Phase 3: Proxy Scale Latency vs Density Loads',
        output_path=results_dir / "phase3_task_latency.pdf",
    )
    print("  Phase 3 graphs complete.\n")


if __name__ == "__main__":
    main()
