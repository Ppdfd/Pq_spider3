"""
Phase 6 (Ref [36]) — AUDIT FIX NOTES
===================================================================
CHANGES vs original:
  [FAIRNESS] The loop now decrypts each packet's REAL ciphertext
             (different (u, v) per packet), not a single pre-
             encrypted ct_sample reused N times.  The old code's
             cache-warm decryption of the same ciphertext was
             artificially fast and structurally inconsistent with
             how Ours' Phase 6 works (one batch decrypt of real
             data).
  [FAIRNESS] The MLWE secret key is now loaded from Phase 2's
             saved ref36_sk.json (the sk that matches the pk used
             to encrypt).  The old code generated a fresh, mis-
             matched keypair, which could pass cache-local decrypt
             but not produce anything related to the ciphertext.
  [HONESTY] Paper [36]'s MLWE-PKE does not cleanly round-trip bytes
             (see mlwe_pke.py); this is a property of the paper's
             construction, not this re-implementation.  We measure
             decryption TIMING only; recovered bytes are not
             verified.

AUDIT DISCLAIMER (Graph 4):
  When Ref [36] appears in Graph 4 (decryption latency), the reported
  times reflect the COMPUTATIONAL COST of the MLWE polynomial
  operations (Algorithm 2), but the decrypted output is NOT verified
  for correctness.  The graph caption should disclose this.
"""

import sys
import config
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives import mlwe_pke, zorder
from utils.dataset_loader import DataLoader


def run_phase6_ref36():
    print("=" * 60)
    print("PQ-SPIDER Phase 6 Simulation: User Decryption (Ref [36] Man)")
    print("=" * 60)

    metrics = {
        "poly_decrypt":        [],
        "morton_reverse":      [],
        "total_user_latency":  0,
    }

    loader = DataLoader()
    phase2_dir = Path(__file__).parent.parent / "phase2_iiot_encrypt"

    try:
        packets = loader.load_data(phase2_dir, "ref36_packets.json")
        sk_blob = loader.load_data(phase2_dir, "ref36_sk.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        print("  ! Run phase2/ref_36.py first.")
        return

    print(f"  -> Loaded {len(packets)} packets.")
    sk = {"s": sk_blob["s"]}

    start_total = time.perf_counter()

    for p in packets:
        # AUDIT FIX: build the per-packet ciphertext from persisted
        # (u, v).  Every packet's decryption is cold-cache and
        # operates on its own data.
        ct = {"u": p["ct_u"], "v": p["ct_v"]}
        payload_len = p["payload_len"]

        # Step 1-3: Polynomial decryption (Algorithm 2)
        t0 = time.perf_counter()
        decoded_bytes = mlwe_pke.decrypt(sk, ct, payload_len)
        t_dec = (time.perf_counter() - t0) * 1000
        metrics["poly_decrypt"].append(t_dec)

        # Step 4: Reverse Morton / Z-order encoding
        t0 = time.perf_counter()
        _ = zorder.morton_decode_bytes(decoded_bytes, len(decoded_bytes))
        t_morton = (time.perf_counter() - t0) * 1000
        metrics["morton_reverse"].append(t_morton)

    total_dec = sum(metrics["poly_decrypt"])
    total_morton = sum(metrics["morton_reverse"])
    print(f"[1-3] Polynomial decrypt × {len(packets)}: {total_dec:.2f} ms")
    print(f"[4]   Reverse Morton    × {len(packets)}: {total_morton:.2f} ms")

    metrics["total_user_latency"] = (time.perf_counter() - start_total) * 1000

    loader.save_metrics(Path(__file__).parent, metrics,
                        filename="ref36_metrics.json")

    print("\n" + "=" * 60)
    print("Phase 6 (Ref [36]) Finished.")
    print(f"Total User Latency: {metrics['total_user_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase6_ref36()
