"""
Phase 2 (Ref [35]): Zaheer et al. — Device-Side PQC Encryption
=================================================================
Implements the device-side encryption phase of:
  A. N. Zaheer et al., "Quantum-Resilient Cryptographic Frameworks,"
  IEEE TCE, Nov 2025.

Paper operations (Sec III-C, III-D):
  The paper uses a hybrid design:
    1. Kyber encap of a session key to the edge node's public key
       (c_kem, k_kem) ← Kyber.Encap(pk)
    2. Symmetric encryption of payload with k_kem (AES-GCM)

  There is NO PUF, NO attribute hashing, NO Ring-LWE CP-ABE.
  No access policy is carried in the ciphertext.

Reported measured timings (Table II, ARM Cortex-A72):
  - Kyber encap: 1.2 ms
  - Kyber decap: 1.0 ms
  - Key size:    1568 B
  - Ciphertext:  1568 B
"""

import os
import sys
import config
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.kyber import SecureKyber
from crypto_primitives.aes_gcm import SecureAESGCM
from utils.dataset_loader import DataLoader


def run_phase2_ref35():
    print("=" * 60)
    print("PQ-SPIDER Phase 2 Simulation: Device Enc (Ref [35] Zaheer et al.)")
    print("=" * 60)

    num_devices = config.NUM_DEVICES
    metrics = {
        "kyber_encap":        [],
        "aes_gcm_encrypt":    [],
        "total_device_latency": [],
    }
    packets = []

    # Load the edge node's Kyber public key from Phase 1 ref_35.
    # In the original draft a fresh edge keypair was generated here
    # every run, which was wrong: the edge's key is long-lived.
    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    try:
        setup = loader.load_data(phase1_dir, "ref35_setup.json")
    except FileNotFoundError:
        print("  ! Run phase1/ref_35.py first.")
        return
    pk_edge = bytes.fromhex(setup["edge0_kyber_pk"])

    for i in range(num_devices):
        device_id = f"IoT-DEV-{i:03d}"
        base_payload = f"Telemetry from {device_id} at {time.time()}".encode()
        pad_len = max(0, config.PAYLOAD_SIZE_BYTES - len(base_payload))
        payload = base_payload + b'\0' * pad_len

        start = time.perf_counter()

        # ── Step 1: Kyber encapsulation to edge node ──
        t0 = time.perf_counter()
        kyber = SecureKyber()
        c_kem, k_kem = kyber.encap(pk_edge)
        t_kyber = (time.perf_counter() - t0) * 1000
        metrics["kyber_encap"].append(t_kyber)

        # ── Step 2: AES-GCM encrypt payload with k_kem ──
        t0 = time.perf_counter()
        aes = SecureAESGCM(key=k_kem)
        c_data, nonce = aes.encrypt(payload, associated_data=None)
        t_aes = (time.perf_counter() - t0) * 1000
        metrics["aes_gcm_encrypt"].append(t_aes)

        t_total = (time.perf_counter() - start) * 1000
        metrics["total_device_latency"].append(t_total)

        packets.append({
            "device_id": device_id,
            "c_kem": c_kem.hex(),
            "c_data": c_data.hex(),
            "nonce": nonce.hex(),
        })
        print(f"  -> Device {i} Packet Generated ({t_total:.2f} ms)")

    phase_dir = Path(__file__).parent
    loader.save_metrics(phase_dir, metrics, filename="ref35_metrics.json")
    loader.save_data(phase_dir, "ref35_packets.json", packets)

    print("\n" + "=" * 60)
    print("Phase 2 (Ref [35]) Finished.")
    avg = sum(metrics["total_device_latency"]) / num_devices
    print(f"Avg Device Latency: {avg:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase2_ref35()
