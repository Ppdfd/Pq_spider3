"""
Phase 1 Master Runner
=====================
Runs the System Initialization phase for:
  - Ours (PQ-SPIDER)
  - Ref [4]  Poomekum et al.  — Ring-LWE CP-ABE
  - Ref [35] Zaheer et al.    — Kyber + Dilithium
  - Ref [36] Man et al.       — MLWE + 4DCCM

Prints a side-by-side comparison of latencies.
Optionally generates scalability PDF graphs (controlled by config.GENERATE_GRAPHS).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from phase1_initialization.ours import run_phase1_simulation
from phase1_initialization.ref_4 import run_phase1_ref4
from phase1_initialization.ref_35 import run_phase1_ref35
from phase1_initialization.ref_36 import run_phase1_ref36

from utils.dataset_loader import DataLoader

import config


def _avg(lst):
    return sum(lst) / len(lst) if lst else 0.0


def main():
    phase_dir = Path(__file__).parent
    print("\n" + "#" * 70)
    print("# PHASE 1 — SYSTEM INITIALIZATION  ·  Full Comparison")
    print("#" * 70 + "\n")

    run_phase1_simulation()
    print()
    run_phase1_ref4()
    print()
    run_phase1_ref35()
    print()
    run_phase1_ref36()
    print()

    loader = DataLoader()
    ours   = loader.load_metrics(phase_dir, "ours_metrics.json")
    ref4   = loader.load_metrics(phase_dir, "ref4_metrics.json")
    ref35  = loader.load_metrics(phase_dir, "ref35_metrics.json")
    ref36  = loader.load_metrics(phase_dir, "ref36_metrics.json")

    print("\n" + "=" * 78)
    print("  PHASE 1 COMPARISON — All times in milliseconds")
    print("=" * 78)
    hdr = f"{'Metric':<25}{'Ours':>12}{'Ref[4]':>12}{'Ref[35]':>12}{'Ref[36]':>12}"
    print(hdr)
    print("-" * 78)

    rows = [
        ("AA / TA Setup",     "aa_setup"),
        ("User KeyGen",       "user_keygen"),
        ("Avg Fog/Edge Init", "fog_node_init"),
        ("Total Latency",     "total_init"),
    ]
    for label, key in rows:
        vals = []
        for m in (ours, ref4, ref35, ref36):
            v = m.get(key)
            if isinstance(v, list):
                v = _avg(v)
            vals.append(v)
        print(f"{label:<25}" + "".join(f"{v:>12.2f}" for v in vals))

    print("=" * 78)
    print("\nNotes:")
    print("  Ref [35]: No CP-ABE setup — TA Setup and User KeyGen are no-ops (0 ms).")
    print("  Ref [36]: No CP-ABE setup — same as Ref [35].")
    print("  Only Ours and Ref [4] perform CP-ABE attribute setup + user keygen.\n")

    if config.GENERATE_GRAPHS:
        plot_graphs()


def plot_graphs():
    """
    Generate Phase 1 scalability graphs (IEEE-style PDFs).

    Graph 1: CP-ABE Latency vs Number of Attributes  (Ours vs Ref[4])
             AUDIT FIX: caption discloses Refs[35]/[36] omission.
    Graph 2: Init Latency vs Number of Fog Nodes     (all 4 schemes)
    """
    from utils.benchmark_runner import run_benchmark, plot_ieee_line

    results_dir = Path(__file__).parent / "results"
    attr_counts = config.GRAPH_ATTR_COUNTS
    fog_nodes = config.GRAPH_FOG_NODES
    warmup = config.GRAPH_WARMUP_ROUNDS
    rounds = config.GRAPH_TEST_ROUNDS

    # ── Graph 1: CP-ABE Latency vs Attributes ──
    print("\n  Generating Phase 1: CP-ABE Latency vs Attributes...")
    results_attr = {"Ours": [], "Ref [4]": []}
    orig_universe = config.CP_ABE_UNIVERSE
    orig_user = config.USER_ATTRIBUTES

    try:
        for count in attr_counts:
            config.CP_ABE_UNIVERSE = [f"Attr{i}" for i in range(count)]
            config.USER_ATTRIBUTES = config.CP_ABE_UNIVERSE[:max(1, count // 2)]
            funcs = {
                "Ours": run_phase1_simulation,
                "Ref [4]": run_phase1_ref4,
            }
            for name, func in funcs.items():
                avg = run_benchmark(
                    func, rounds, warmup,
                    extract_metric=lambda m: m["aa_setup"] + m["user_keygen"],
                )
                results_attr[name].append(avg)
    finally:
        config.CP_ABE_UNIVERSE = orig_universe
        config.USER_ATTRIBUTES = orig_user

    plot_ieee_line(
        attr_counts, results_attr,
        xlabel='Number of Attributes in Universe',
        ylabel='CP-ABE Setup Latency (ms)',
        title='Phase 1: CP-ABE Latency vs Number of Attributes',
        output_path=results_dir / "phase1_attr_latency.pdf",
        # AUDIT FIX: disclose why [35]/[36] are absent
        caption="Refs [35] and [36] omitted: neither defines attribute-based "
                "access control.\nOurs and Ref [4] both use ring dimension n=256.",
    )

    # ── Graph 2: Init Latency vs Fog Nodes ──
    print("  Generating Phase 1: Init Latency vs Fog Nodes...")
    results_fog = {"Ours": [], "Ref [4]": [], "Ref [35]": [], "Ref [36]": []}
    orig_nodes = config.NUM_GLOBAL_NODES

    try:
        for num_nodes in fog_nodes:
            config.NUM_GLOBAL_NODES = num_nodes
            funcs = {
                "Ours": run_phase1_simulation,
                "Ref [4]": run_phase1_ref4,
                "Ref [35]": run_phase1_ref35,
                "Ref [36]": run_phase1_ref36,
            }
            for name, func in funcs.items():
                avg = run_benchmark(
                    func, rounds, warmup,
                    extract_metric=lambda m: m["total_init"],
                )
                results_fog[name].append(avg)
    finally:
        config.NUM_GLOBAL_NODES = orig_nodes

    plot_ieee_line(
        fog_nodes, results_fog,
        xlabel='Number of Fog Nodes',
        ylabel='Initialization Latency (ms)',
        title='Phase 1: Latency vs Number of Fog Nodes',
        output_path=results_dir / "phase1_fog_latency.pdf",
    )
    print("  Phase 1 graphs complete.\n")


if __name__ == "__main__":
    main()
