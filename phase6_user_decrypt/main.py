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
from phase2_iiot_encrypt.ours   import run_phase2_simulation
from phase2_iiot_encrypt.ref_4  import run_phase2_ref4
from phase3_edge_gateway.ours import run_phase3_simulation
from phase5_fog_node.ours   import run_phase5_simulation
from phase5_fog_node.ref_4  import run_phase5_ref4
from phase6_user_decrypt.ours   import run_phase6_simulation
from phase6_user_decrypt.ref_4  import run_phase6_ref4

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


    loader = DataLoader()
    ours = loader.load_metrics(phase_dir, "ours_metrics.json")
    r4   = loader.load_metrics(phase_dir, "ref4_metrics.json")


    print("\n" + "=" * 78)
    print("  PHASE 6 COMPARISON — Total user-side latency (ms)")
    print("=" * 78)
    print(f"{'Scheme':<20}{'User Latency (ms)':>22}{'Decrypt Approach':>34}")
    print("-" * 78)
    rows = [
        ("Ours",            ours, "Dilithium + CP-ABE + AES"),
        ("Ref[4] Poomekum", r4,   "Poly1305 + noise cancel + AES"),
    ]
    for name, m, descr in rows:
        val = m.get("total_user_latency", 0)
        print(f"{name:<20}{val:>22.2f}{descr:>34}")
    print("=" * 78)
    print()




if __name__ == "__main__":
    main()
