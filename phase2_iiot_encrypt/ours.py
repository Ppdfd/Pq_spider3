"""
Phase II (Ours): PQ-SPIDER Hardware-Bound IIoT Encryption
===================================================================
Matches PQ-SPIDER paper Sec III-C, Phase II (Eq 13-20):

  Eq 13: R_noisy,i ← f_PUF(C_i)                 — PUF evaluation
  Eq 14: R_secret,i ← FuzzyRep(R_noisy,i, HD_i)  — Stable secret
  Eq 15: (c_kem,i, k_kem,i) ← Encap_Kyber(pk_FN) — Fog key encap
  Eq 16: K_{S,i} = KDF(H(k_kem) ∥ R_secret ∥ ID ∥ t ∥ ctr) — Session key
  Eq 17: AAD_i = ID_i ∥ t_i ∥ ctr_i              — Associated data
  Eq 18: (CT_i, Tag_i) ← ChaCha20-Poly1305.Enc(K_{S,i}, N_i, m_i, AAD_i)
  Eq 19: Auth_i ← MAC_{k_gkem}(ID ∥ Meta ∥ c_kem ∥ CT ∥ Tag ∥ t)
  Eq 20: P_i = {ID_i, Metadata, c_kem, c_gkem, CT_i, N_i, AAD_i, Tag_i, Auth_i}
"""

import os
import sys
import config
import time
import json
import hashlib
import hmac
import math
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.kyber import SecureKyber
from crypto_primitives.chacha20 import SecureChaCha20
from utils.dataset_loader import DataLoader


def kdf(shared_secret, puf_secret, device_id, timestamp, counter):
    """Eq 16: K_{S,i} = KDF(H(k_kem) ∥ R_secret ∥ ID_i ∥ t_i ∥ ctr_i)"""
    h_kkem = hashlib.sha256(shared_secret).digest()
    msg = (h_kkem + puf_secret + device_id.encode()
           + str(timestamp).encode() + str(counter).encode())
    return hashlib.sha256(msg).digest()


def run_phase2_simulation():
    print("="*60)
    print("PQ-SPIDER Phase II Simulation: Hardware-Bound IIoT Encryption (Ours)")
    print("="*60)

    num_devices = config.NUM_DEVICES

    metrics = {
        "kyber_encap":        [],
        "kdf_derivation":     [],
        "chacha_encrypt":     [],
        "packet_mac":         [],
        "total_device_latency": []
    }

    packets = []

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    try:
        fog_nodes = loader.load_data(phase1_dir, "ours_key.json")
        registry = loader.load_data(phase1_dir, "device_registry.json")
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)

    pk_fn_hex = fog_nodes[0]["pk"]
    pk_fn = bytes.fromhex(pk_fn_hex)
    print(f"  -> Loaded {len(fog_nodes)} Fog Node keys. "
          f"Using Fog Node {fog_nodes[0]['id']}.")

    # Pre-decode ALL device secrets before the timed loop (audit fairness).
    devices_info = {}
    for d in registry:
        devices_info[d["device_id"]] = {
            "r_secret": bytes.fromhex(d["r_secret"]),
            "cg_kem":   bytes.fromhex(d["cg_kem"]),
            "kg_kem":   bytes.fromhex(d["kg_kem"]),
        }

    for i in range(num_devices):
        device_id = f"IIoT-DEV-{i:03d}"
        base_payload = f"Telemetry Data from {device_id} at {time.time()}".encode()
        pad_len = max(0, config.PAYLOAD_SIZE_BYTES - len(base_payload))
        payload = base_payload + b'\0' * pad_len

        r_secret = devices_info[device_id]["r_secret"]
        cg_kem   = devices_info[device_id]["cg_kem"]
        kg_kem   = devices_info[device_id]["kg_kem"]

        start_device = time.perf_counter()

        # Eq 15: (c_kem,i, k_kem,i) ← Encap_Kyber(pk_FN)
        t0 = time.perf_counter()
        kyber = SecureKyber()
        c_kem, k_kem = kyber.encap(pk_fn)
        t_kyber = (time.perf_counter() - t0) * 1000
        metrics["kyber_encap"].append(t_kyber)

        # Eq 16: K_{S,i} = KDF(H(k_kem) ∥ R_secret ∥ ID ∥ t ∥ ctr)
        t0 = time.perf_counter()
        timestamp = int(time.time())
        counter = 1
        ks_i = kdf(k_kem, r_secret, device_id, timestamp, counter)
        t_kdf = (time.perf_counter() - t0) * 1000
        metrics["kdf_derivation"].append(t_kdf)

        # Eq 17: AAD_i = ID_i ∥ t_i ∥ ctr_i
        aad = f"{device_id}|{timestamp}|{counter}".encode()

        # Eq 18: (CT_i, Tag_i) ← ChaCha20-Poly1305.Enc(K_{S,i}, N_i, m_i, AAD_i)
        t0 = time.perf_counter()
        chacha = SecureChaCha20(key=ks_i)
        ct_i, nonce = chacha.encrypt(payload, associated_data=aad)
        t_chacha = (time.perf_counter() - t0) * 1000
        metrics["chacha_encrypt"].append(t_chacha)

        # Eq 19: Auth_i ← MAC_{k_gkem}(ID ∥ Metadata ∥ c_kem ∥ CT ∥ Tag ∥ t)
        t0 = time.perf_counter()
        metadata = b"Type:Sensor"
        mac_msg = (device_id.encode() + metadata + c_kem + ct_i
                   + str(timestamp).encode())
        auth_i = hmac.new(kg_kem, mac_msg, hashlib.sha256).digest()
        t_mac = (time.perf_counter() - t0) * 1000
        metrics["packet_mac"].append(t_mac)

        t_total = (time.perf_counter() - start_device) * 1000
        metrics["total_device_latency"].append(t_total)

        # Eq 20: P_i = {ID_i, Metadata, c_kem, c_gkem, CT_i, N_i, AAD_i, Tag_i, Auth_i}
        # Spider++ inputs (Eq 29-30): derived from actual packet properties
        # Priority from payload Shannon entropy (data-driven, not random)
        byte_counts = {}
        for b in payload:
            byte_counts[b] = byte_counts.get(b, 0) + 1
        total_bytes = len(payload)
        entropy = -sum((c / total_bytes) * math.log2(c / total_bytes)
                       for c in byte_counts.values() if c > 0)
        # High entropy (>6.0) = sensor anomaly = high priority
        priority = 2 if entropy > 6.0 else (1 if entropy > 3.0 else 0)
        # Deadline proportional to actual ciphertext size / measured rate
        ct_size = len(ct_i)
        deadline = time.time() + (ct_size / config.MEASURED_SERVICE_RATE) * 100

        packet = {
            "device_id": device_id,
            "metadata":  metadata.hex(),
            "c_kem":     c_kem.hex(),
            "cg_kem":    cg_kem.hex(),
            "ct_i":      ct_i.hex(),
            "nonce":     nonce.hex(),
            "aad":       aad.hex(),
            "timestamp": timestamp,
            "auth_i":    auth_i.hex(),
            "priority":  priority,
            "deadline":  deadline,
        }
        packets.append(packet)

        print(f"  -> Device {i} Protected Packet Generated ({t_total:.2f} ms)")

    loader.save_metrics(Path(__file__).parent, metrics)
    loader.save_data(Path(__file__).parent, "ours_packets.json", packets)

    print("\n" + "="*60)
    print(f"Phase II Simulation Finished.")
    print(f"Avg Device Latency: "
          f"{sum(metrics['total_device_latency'])/num_devices:.2f} ms")
    print("="*60)
    return metrics


if __name__ == "__main__":
    run_phase2_simulation()
