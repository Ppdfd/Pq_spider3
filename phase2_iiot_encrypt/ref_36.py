"""
Phase 2 (Ref [36]) — AUDIT FIX NOTES
===================================================================
CHANGES vs original:
  [FAIRNESS] The 4DCCM chaos state is now initialised ONCE and
             warmed up (800 iterations) ONCE outside the per-device
             loop.  Only the per-packet perturbation (Eq. 13) stays
             inside the timer.  Paper [36]'s Fig. 1 makes it clear
             the chaotic state is shared across a batch; the
             original code re-warmed 800 iterations per packet,
             inflating device latency ~800x.
  [FAIRNESS] Real ciphertexts (u, v) are now persisted in
             ref36_packets.json so Phase 5 and Phase 6 can operate
             on actual data.  Previously only (u_len, v_len) were
             saved, forcing Phase 5 to fabricate inputs with
             os.urandom and Phase 6 to decrypt a single ct_sample
             N times from a cache-warm loop.
"""

import hashlib
import sys
import config
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives import mlwe_pke, chaotic_4dccm, zorder
from utils.dataset_loader import DataLoader


def run_phase2_ref36():
    print("=" * 60)
    print("PQ-SPIDER Phase 2 Simulation: Device Enc (Ref [36] Man et al.)")
    print("=" * 60)

    num_devices = config.NUM_DEVICES
    metrics = {
        "morton_encode":        [],
        "chaos_iteration":      [],
        "mlwe_encrypt":         [],
        "total_device_latency": [],
    }
    packets = []

    # Edge-node public key — shared across batch
    pk, sk = mlwe_pke.keygen()

    # AUDIT FIX: Batch-shared chaos state.  Initialised and warmed
    # up ONCE, outside the per-device timer.  This matches paper
    # [36]'s batch-oriented Fig. 1 flow.  Only the per-packet
    # perturbation (Eq. 13) stays inside the timer.
    chaos_shared = chaotic_4dccm.init_state()
    chaos_shared = chaotic_4dccm.iterate(chaos_shared, rounds=800)

    for i in range(num_devices):
        device_id = f"IoT-DEV-{i:03d}"
        base_payload = f"Telemetry from {device_id} at {time.time()}".encode()
        pad_len = max(0, config.PAYLOAD_SIZE_BYTES - len(base_payload))
        payload = base_payload + b'\0' * pad_len

        start = time.perf_counter()

        # Step 1-5: Real Morton / Z-order encoding (Eq. 10-11)
        t0 = time.perf_counter()
        encoded = zorder.morton_encode_bytes(payload)
        t_morton = (time.perf_counter() - t0) * 1000
        metrics["morton_encode"].append(t_morton)

        # Step 2: 4DCCM perturbation only (Eq. 13).
        # Warmup (Eq. 9) was done once outside the loop.
        t0 = time.perf_counter()
        chaos = chaotic_4dccm.perturb_state(chaos_shared, encoded)
        t_chaos = (time.perf_counter() - t0) * 1000
        metrics["chaos_iteration"].append(t_chaos)

        # Step 3: MLWE encryption (Algorithm 1)
        t0 = time.perf_counter()
        ct = mlwe_pke.encrypt(pk, encoded)
        t_mlwe = (time.perf_counter() - t0) * 1000
        metrics["mlwe_encrypt"].append(t_mlwe)

        t_total = (time.perf_counter() - start) * 1000
        metrics["total_device_latency"].append(t_total)

        # AUDIT FIX: Persist the real ciphertext.  Old version only
        # stored u_len / v_len, forcing Phase 5 to os.urandom-
        # fabricate inputs.
        packets.append({
            "device_id":   device_id,
            "ct_u":        ct["u"],   # list of K polynomials (K x N ints)
            "ct_v":        ct["v"],   # polynomial (N ints)
            "payload_len": len(encoded),
            "chaos_final": chaos,
        })
        print(f"  -> Device {i} Packet Generated ({t_total:.2f} ms)")

    loader = DataLoader()
    phase_dir = Path(__file__).parent
    loader.save_metrics(phase_dir, metrics, filename="ref36_metrics.json")
    loader.save_data(phase_dir, "ref36_packets.json", packets)
    # Persist the matching sk so phase6/ref_36.py can decrypt with
    # the key that was used to encrypt.
    loader.save_data(phase_dir, "ref36_sk.json", {"s": sk["s"]})

    print("\n" + "=" * 60)
    print("Phase 2 (Ref [36]) Finished.")
    avg = sum(metrics["total_device_latency"]) / num_devices
    print(f"Avg Device Latency:     {avg:.2f} ms")
    print(f"  Morton (real):        "
          f"{sum(metrics['morton_encode']) / num_devices:.3f} ms avg")
    print(f"  4DCCM (perturb only): "
          f"{sum(metrics['chaos_iteration']) / num_devices:.3f} ms avg")
    print(f"  MLWE-PKE (Eq. 14-15): "
          f"{sum(metrics['mlwe_encrypt']) / num_devices:.3f} ms avg")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase2_ref36()
