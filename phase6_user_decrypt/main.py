"""
Phase 6 Master Runner
=====================
Runs User Decryption for all schemes.
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
from phase6_user_decrypt.ours   import run_phase6_simulation
from phase6_user_decrypt.ref_4  import run_phase6_ref4
from phase6_user_decrypt.ref_35 import run_phase6_ref35
from phase6_user_decrypt.ref_36 import run_phase6_ref36

from utils.dataset_loader import DataLoader
import config


def main():
    phase_dir = Path(__file__).parent
    print("\n" + "#" * 70)
    print("# PHASE 6 — USER DECRYPTION  ·  Full Comparison")
    print("#" * 70 + "\n")

    run_phase6_simulation()
    print()
    run_phase6_ref4()
    print()
    run_phase6_ref35()
    print()
    run_phase6_ref36()
    print()

    loader = DataLoader()
    ours = loader.load_metrics(phase_dir, "ours_metrics.json")
    r4   = loader.load_metrics(phase_dir, "ref4_metrics.json")
    r35  = loader.load_metrics(phase_dir, "ref35_metrics.json")
    r36  = loader.load_metrics(phase_dir, "ref36_metrics.json")

    print("\n" + "=" * 78)
    print("  PHASE 6 COMPARISON — Total user-side latency (ms)")
    print("=" * 78)
    print(f"{'Scheme':<20}{'User Latency (ms)':>22}{'Decrypt Approach':>34}")
    print("-" * 78)
    rows = [
        ("Ours",            ours, "Dilithium + CP-ABE + AES"),
        ("Ref[4] Poomekum", r4,   "Poly1305 + noise cancel + AES"),
        ("Ref[35] Zaheer",  r35,  "Dilithium + Kyber decap + AES"),
        ("Ref[36] Man",     r36,  "INTT poly + reverse Z-order"),
    ]
    for name, m, descr in rows:
        val = m.get("total_user_latency", 0)
        print(f"{name:<20}{val:>22.2f}{descr:>34}")
    print("=" * 78)
    print()

    if config.GENERATE_GRAPHS:
        plot_graphs()


def plot_graphs():
    """
    Phase 6 graph. AUDIT FIX preserved:
    - Ref[36] chain includes Phase 5
    - No O(1) Batch tag on Ours label
    - Structural asymmetry caption (batch vs per-packet)
    """
    from utils.benchmark_runner import run_benchmark_chain, plot_ieee_line

    results_dir = Path(__file__).parent / "results"
    attr_counts = config.GRAPH_ATTR_COUNTS
    warmup = config.GRAPH_WARMUP_ROUNDS
    rounds = config.GRAPH_TEST_ROUNDS

    print("\n  Generating Phase 6: User Decryption vs Attributes...")
    results = {"Ours": [], "Ref [4]": [], "Ref [35]": [], "Ref [36]": []}
    orig_univ = config.CP_ABE_UNIVERSE
    orig_user = config.USER_ATTRIBUTES
    extract_user = lambda m: m["total_user_latency"]

    # AUDIT FIX: Ref[36] chain now includes phase5 (was missing in original)
    chains = {
        "Ours":     [run_phase1_simulation, run_phase2_simulation,
                     run_phase3_simulation, run_phase5_simulation,
                     run_phase6_simulation],
        "Ref [4]":  [run_phase1_ref4, run_phase2_ref4,
                     run_phase5_ref4, run_phase6_ref4],
        "Ref [35]": [run_phase1_ref35, run_phase2_ref35,
                     run_phase5_ref35, run_phase6_ref35],
        "Ref [36]": [run_phase1_ref36, run_phase2_ref36,
                     run_phase5_ref36, run_phase6_ref36],
    }

    try:
        for count in attr_counts:
            config.CP_ABE_UNIVERSE = [f"A{i}" for i in range(count)]
            config.USER_ATTRIBUTES = config.CP_ABE_UNIVERSE[:max(1, count // 2)]
            for name, chain in chains.items():
                avg = run_benchmark_chain(chain, rounds, warmup, extract_user)
                results[name].append(avg)
    finally:
        config.CP_ABE_UNIVERSE = orig_univ
        config.USER_ATTRIBUTES = orig_user

    # AUDIT FIX: no "(O(1) Batch)" on Ours label; structural asymmetry caption
    plot_ieee_line(
        attr_counts, results,
        xlabel='Number of Attributes',
        ylabel='User Decryption Latency (ms)',
        title='Phase 6: User Decryption vs Attribute Depth',
        output_path=results_dir / "phase6_attr_latency.pdf",
        caption="Structural note: Ours does ONE batch-level decrypt (fog-side "
                "aggregation in Phase 5).\nRefs do per-packet decrypt × N packets.  "
                "The attribute axis only applies to Ours and Ref [4];\nit is shown "
                "for Refs [35]/[36] to expose the scale-invariance of their designs.",
    )
    print("  Phase 6 graphs complete.\n")


if __name__ == "__main__":
    main()
