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




if __name__ == "__main__":
    main()
