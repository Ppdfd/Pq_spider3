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




if __name__ == "__main__":
    main()
