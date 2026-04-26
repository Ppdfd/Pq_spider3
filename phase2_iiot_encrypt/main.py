"""
Phase 2 Master Runner
=====================
Runs the IoT Device Encryption phase for:
  - Ours      (PQ-SPIDER: PUF + Kyber + ChaCha20-Poly1305 + HMAC)
  - Ref [4]   Poomekum et al. (AES-GCM + Ring-LWE encap + Poly1305)
  - Ref [35]  Zaheer et al.   (Kyber encap + AES-GCM)
  - Ref [36]  Man et al.      (Z-order + 4DCCM + MLWE encrypt)

Optionally generates scalability PDF graphs (controlled by config.GENERATE_GRAPHS).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from phase1_initialization.ours import run_phase1_simulation
from phase1_initialization.ref_4 import run_phase1_ref4
from phase1_initialization.ref_35 import run_phase1_ref35
from phase1_initialization.ref_36 import run_phase1_ref36

from phase2_iiot_encrypt.ours import run_phase2_simulation
from phase2_iiot_encrypt.ref_4 import run_phase2_ref4
from phase2_iiot_encrypt.ref_35 import run_phase2_ref35
from phase2_iiot_encrypt.ref_36 import run_phase2_ref36

from utils.dataset_loader import DataLoader

import config


def _avg(lst):
    return sum(lst) / len(lst) if lst else 0.0


def main():
    phase_dir = Path(__file__).parent
    print("\n" + "#" * 70)
    print("# PHASE 2 — IoT DEVICE ENCRYPTION  ·  Full Comparison")
    print("#" * 70 + "\n")

    run_phase2_simulation()
    print()
    run_phase2_ref4()
    print()
    run_phase2_ref35()
    print()
    run_phase2_ref36()
    print()

    loader = DataLoader()
    ours = loader.load_metrics(phase_dir, "ours_metrics.json")
    r4   = loader.load_metrics(phase_dir, "ref4_metrics.json")
    r35  = loader.load_metrics(phase_dir, "ref35_metrics.json")
    r36  = loader.load_metrics(phase_dir, "ref36_metrics.json")

    print("\n" + "=" * 78)
    print("  PHASE 2 COMPARISON — Avg latency per device (ms)")
    print("=" * 78)
    print(f"{'Scheme':<20}{'Total/Device':>20}{'Key Encap':>18}{'Sym Enc':>18}")
    print("-" * 78)

    print(f"{'Ours':<20}"
          f"{_avg(ours['total_device_latency']):>20.3f}"
          f"{_avg(ours['kyber_encap']):>18.3f}"
          f"{_avg(ours['chacha_encrypt']):>18.3f}")
    print(f"{'Ref[4] Poomekum':<20}"
          f"{_avg(r4['total_device_latency']):>20.3f}"
          f"{_avg(r4['ringlwe_encap']):>18.3f}"
          f"{_avg(r4['aes_gcm_encrypt']):>18.3f}")
    print(f"{'Ref[35] Zaheer':<20}"
          f"{_avg(r35['total_device_latency']):>20.3f}"
          f"{_avg(r35['kyber_encap']):>18.3f}"
          f"{_avg(r35['aes_gcm_encrypt']):>18.3f}")
    print(f"{'Ref[36] Man':<20}"
          f"{_avg(r36['total_device_latency']):>20.3f}"
          f"{'(MLWE enc)':>18}"
          f"{_avg(r36['mlwe_encrypt']):>18.3f}")

    print("=" * 78)
    print("\nNotes:")
    print("  Ref [4]:  Ring-LWE encap runs per-attribute poly mults (n=256, q=8192)")
    print("  Ref [35]: Plain Kyber encap + AES-GCM — no access control")
    print("  Ref [36]: MLWE encryption integrates key and payload (no separate encap)")
    print()




if __name__ == "__main__":
    main()
