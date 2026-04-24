"""
Phase 5 Master Runner
=====================
Runs Fog/Edge-Node Processing for all schemes.
Optionally generates scalability PDF graphs (controlled by config.GENERATE_GRAPHS).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from phase1_initialization.ours   import run_phase1_simulation
from phase1_initialization.ref_4  import run_phase1_ref4
from phase1_initialization.ref_35 import run_phase1_ref35
from phase1_initialization.ref_36 import run_phase1_ref36
from phase2_iiot_encrypt.ours   import run_phase2_simulation
from phase2_iiot_encrypt.ref_4  import run_phase2_ref4
from phase2_iiot_encrypt.ref_35 import run_phase2_ref35
from phase2_iiot_encrypt.ref_36 import run_phase2_ref36
from phase3_edge_gateway.ours import run_phase3_simulation
from phase5_fog_node.ours   import run_phase5_simulation
from phase5_fog_node.ref_4  import run_phase5_ref4
from phase5_fog_node.ref_35 import run_phase5_ref35
from phase5_fog_node.ref_36 import run_phase5_ref36

from utils.dataset_loader import DataLoader
import config


def main():
    phase_dir = Path(__file__).parent
    print("\n" + "#" * 70)
    print("# PHASE 5 — FOG NODE PROCESSING  ·  Full Comparison")
    print("#" * 70 + "\n")

    run_phase5_simulation()
    print()
    run_phase5_ref4()
    print()
    run_phase5_ref35()
    print()
    run_phase5_ref36()
    print()

    loader = DataLoader()
    ours = loader.load_metrics(phase_dir, "ours_metrics.json")
    r4   = loader.load_metrics(phase_dir, "ref4_metrics.json")
    r35  = loader.load_metrics(phase_dir, "ref35_metrics.json")
    r36  = loader.load_metrics(phase_dir, "ref36_metrics.json")

    print("\n" + "=" * 78)
    print("  PHASE 5 COMPARISON — Total fog-side latency per batch (ms)")
    print("=" * 78)
    print(f"{'Scheme':<20}{'Fog Latency (ms)':>20}{'Key Features':>36}")
    print("-" * 78)
    rows = [
        ("Ours",            ours, "Batch + CP-ABE + Dilithium"),
        ("Ref[4] Poomekum", r4,   "β augment + Dilithium"),
        ("Ref[35] Zaheer",  r35,  "Kyber decap + Dilithium"),
        ("Ref[36] Man",     r36,  "Passthrough only"),
    ]
    for name, m, descr in rows:
        val = m.get("total_fog_latency", 0)
        print(f"{name:<20}{val:>20.2f}{descr:>36}")
    print("=" * 78)
    print()

    if config.GENERATE_GRAPHS:
        plot_graphs()


def plot_graphs():
    """
    Phase 5 graphs. AUDIT FIX preserved:
    - plot_phase5_fog: fixed Ours chain (no duplicate p1), asymmetry caption
    - plot_phase5_attr: n=256 caption
    - plot_phase5_tee: REMOVED per audit (fake parallelism)
    """
    from utils.benchmark_runner import run_benchmark_chain, plot_ieee_line

    results_dir = Path(__file__).parent / "results"
    fog_nodes = config.GRAPH_FOG_NODES
    attr_counts = config.GRAPH_ATTR_COUNTS
    warmup = config.GRAPH_WARMUP_ROUNDS
    rounds = config.GRAPH_TEST_ROUNDS
    extract_fog = lambda m: m["total_fog_latency"]

    # ── Graph 1: Fog Latency vs Fog Nodes ──
    print("\n  Generating Phase 5: Fog Latency vs Fog Nodes...")
    results_fog = {"Ours": [], "Ref [4]": [], "Ref [35]": [], "Ref [36]": []}
    orig_nodes = config.NUM_GLOBAL_NODES

    # AUDIT FIX: Ours chain has no duplicate ours_p1
    chains = {
        "Ours":     [run_phase1_simulation, run_phase2_simulation,
                     run_phase3_simulation, run_phase5_simulation],
        "Ref [4]":  [run_phase1_ref4, run_phase2_ref4, run_phase5_ref4],
        "Ref [35]": [run_phase1_ref35, run_phase2_ref35, run_phase5_ref35],
        "Ref [36]": [run_phase1_ref36, run_phase2_ref36, run_phase5_ref36],
    }
    try:
        for num in fog_nodes:
            config.NUM_GLOBAL_NODES = num
            for name, chain in chains.items():
                avg = run_benchmark_chain(chain, rounds, warmup, extract_fog)
                results_fog[name].append(avg)
    finally:
        config.NUM_GLOBAL_NODES = orig_nodes

    plot_ieee_line(
        fog_nodes, results_fog,
        xlabel='Number of Fog Nodes',
        ylabel='Fog Latency (ms)',
        title='Phase 5: Fog Latency vs Network Scale',
        output_path=results_dir / "phase5_fog_latency.png",
        caption="Architectural note: Ours performs Kyber decap + AES-GCM + CP-ABE "
                "partial + Dilithium sign.\nRef [35] does Kyber relay + Dilithium "
                "sign.  Ref [4] does Poly1305 verify + beta augmentation +\nDilithium "
                "sign.  Ref [36] has NO fog re-encryption — only a passthrough hash.",
    )

    # ── Graph 2: Fog Latency vs Attributes ──
    print("  Generating Phase 5: Fog Latency vs Attributes...")
    results_attr = {"Ours": [], "Ref [4]": []}
    orig_univ = config.CP_ABE_UNIVERSE
    orig_user = config.USER_ATTRIBUTES

    attr_chains = {
        "Ours":    [run_phase1_simulation, run_phase2_simulation,
                    run_phase3_simulation, run_phase5_simulation],
        "Ref [4]": [run_phase1_ref4, run_phase2_ref4, run_phase5_ref4],
    }
    try:
        for count in attr_counts:
            config.CP_ABE_UNIVERSE = [f"A{i}" for i in range(count)]
            config.USER_ATTRIBUTES = config.CP_ABE_UNIVERSE[:max(1, count // 2)]
            for name, chain in attr_chains.items():
                avg = run_benchmark_chain(chain, rounds, warmup, extract_fog)
                results_attr[name].append(avg)
    finally:
        config.CP_ABE_UNIVERSE = orig_univ
        config.USER_ATTRIBUTES = orig_user

    plot_ieee_line(
        attr_counts, results_attr,
        xlabel='Number of Attributes',
        ylabel='Fog Latency (ms)',
        title='Phase 5: Fog Latency vs Attribute Density',
        output_path=results_dir / "phase5_attr_latency.png",
        caption="Refs [35] and [36] omitted: neither uses attribute-based "
                "access control.\nOurs and Ref [4] both use ring dimension n=256.",
    )

    # NOTE: plot_phase5_tee REMOVED per audit — fake-parallelism graph retired.
    print("  Phase 5 graphs complete.\n")


if __name__ == "__main__":
    main()
