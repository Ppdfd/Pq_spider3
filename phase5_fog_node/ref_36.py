"""
Phase 5 (Ref [36]) — AUDIT FIX NOTES
===================================================================
CHANGES vs original:
  [FAIRNESS] The passthrough hash now operates on the REAL
             ciphertext (serialised ct_u || ct_v) from Phase 2,
             not on an os.urandom-fabricated buffer.  The old code
             charged Ref [36] for entropy-syscall overhead that has
             nothing to do with a real edge node's memcpy+hash.
  [ARCH NOTE] Paper [36] has no fog-layer re-encryption.  The
             "passthrough hash" is the minimal edge operation the
             paper implies.  Graphs that plot this alongside Ours'
             full CP-ABE + Dilithium Phase 5 must disclose the
             architectural asymmetry in the caption.
"""

import sys
import time
import hashlib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from utils.dataset_loader import DataLoader


def run_phase5_ref36():
    print("=" * 60)
    print("PQ-SPIDER Phase 5 Simulation: Edge Passthrough (Ref [36] Man)")
    print("=" * 60)

    metrics = {
        "passthrough_hash":  [],
        "total_fog_latency": 0,
        "paper_note": "No fog re-encryption or signing in [36]; "
                      "only passthrough hash on real ciphertext.",
    }

    loader = DataLoader()
    phase2_dir = Path(__file__).parent.parent / "phase2_iiot_encrypt"

    try:
        packets = loader.load_data(phase2_dir, "ref36_packets.json")
    except FileNotFoundError:
        print("  ! Run phase2/ref_36.py first.")
        return

    print(f"  -> Loaded {len(packets)} packets.")

    # AUDIT FIX: pre-serialise each ciphertext OUTSIDE the timer.
    # Phase 2 now persists the real u, v polynomials, so we can
    # hash them directly instead of fabricating bytes.
    ct_bufs = []
    for p in packets:
        buf = b""
        for poly in p["ct_u"]:
            buf += b"".join(int(c).to_bytes(2, "little", signed=False)
                            for c in poly)
        buf += b"".join(int(c).to_bytes(2, "little", signed=False)
                        for c in p["ct_v"])
        ct_bufs.append(buf)

    start_total = time.perf_counter()

    for buf in ct_bufs:
        t0 = time.perf_counter()
        _ = hashlib.sha256(buf).digest()
        metrics["passthrough_hash"].append(
            (time.perf_counter() - t0) * 1000)

    metrics["total_fog_latency"] = (time.perf_counter() - start_total) * 1000

    loader.save_metrics(Path(__file__).parent, metrics,
                        filename="ref36_metrics.json")

    print("\n" + "=" * 60)
    print("Phase 5 (Ref [36]) Finished.")
    print(f"Total Fog Latency : {metrics['total_fog_latency']:.3f} ms "
          f"(passthrough only — paper [36] has no fog re-encryption)")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase5_ref36()
