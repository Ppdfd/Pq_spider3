"""
Phase 2 (Ref [4]): Poomekum et al. — IoT Device Partial Encryption
====================================================================
Implements "Partial Encryption in IoT Device" (Sec IV-B, Phase 3):

Step 1: Attribute Representation
  - Hash each strict attr a_i with salt:  l_i = H(a_i || salt)
  - Build strict attribute matrix F_s = AttrMatrix(PP, L_s)
  - Forward flexible labels L_f (hashed) to fog

Step 2: Symmetric Encryption
  - K_sess ← RNG(256)
  - (C_data, nonce) = AES-GCM.Enc(K_sess, M)

Step 3: Lattice-Based Key Encapsulation
  - Sample r ← Gaussian
  - Encode K_sess into polynomial m over R_q
  - u        = a · r + e_u
  - C_epoch  = B_epoch · r + e_epoch
  - C_attr_i = B_i · r + e_i      for each strict attribute
  - C_r      = m + e_r

Step 4: Integrity and Packaging
  - outer_ct = {u, C_epoch, C_attrs, C_r}
  - PolyKey loaded via secure registry
  - PolyTag = Poly1305(PolyKey, serialize(outer_ct))
  - CT_partial = {outer_ct, C_data, nonce, T_exp, PolyTag}
"""

import os
import sys
import config
import time
import hashlib
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.aes_gcm import SecureAESGCM
from utils.dataset_loader import DataLoader

# Paper [4] ring-LWE params
N_RING = 256
Q_MOD = 8192
SIGMA_GAUSS = 3.2


def _sample_gaussian(n, sigma, q):
    return np.random.normal(0.0, sigma, size=n).round().astype(np.int64) % q


def _sample_uniform(n, q):
    return np.random.randint(0, q, size=n).astype(np.int64)


def _poly_mul_mod(a, b, q, n=N_RING):
    A = np.fft.fft(a.astype(np.float64), 2 * n)
    B = np.fft.fft(b.astype(np.float64), 2 * n)
    c = np.fft.ifft(A * B).real.round().astype(np.int64)
    return (c[:n] - c[n:]) % q


def _encode_key_to_poly(key_bytes, q, n):
    half_q = q // 2
    m = np.zeros(n, dtype=np.int64)
    for i, byte in enumerate(key_bytes):
        for j in range(8):
            bit = (byte >> j) & 1
            idx = i * 8 + j
            if idx < n:
                m[idx] = bit * half_q
    return m


def _poly1305_mac(key32: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives import poly1305
    p = poly1305.Poly1305(key32)
    p.update(data)
    return p.finalize()


def run_phase2_ref4():
    print("=" * 60)
    print("PQ-SPIDER Phase 2 Simulation: IoT Device Enc (Ref [4] Poomekum et al.)")
    print("=" * 60)

    num_devices = config.NUM_DEVICES

    metrics = {
        "aes_gcm_encrypt":   [],
        "attr_hashing":      [],
        "ringlwe_encap":     [],
        "poly1305_tag":      [],
        "total_device_latency": [],
    }
    packets = []

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    try:
        setup = loader.load_data(phase1_dir, "ref4_setup.json")
        registry = loader.load_data(phase1_dir, "ref4_device_registry.json")
    except FileNotFoundError:
        print("  ! Run phase1/ref_4.py first.")
        return
        
    devices_info = {d["device_id"]: d for d in registry}

    salt = bytes.fromhex(setup["salt"])
    a_pub = np.array(setup["a_pub"], dtype=np.int64)

    strict_attrs = setup["user_attributes"]
    B_attrs = {}
    for attr in strict_attrs:
        h = hashlib.sha256(attr.encode() + salt).hexdigest()
        B_attrs[attr] = np.array(setup["B_table"][h], dtype=np.int64)

    B_epoch = np.array(setup["B_epoch"], dtype=np.int64)

    for i in range(num_devices):
        device_id = f"IoT-DEV-{i:03d}"
        
        base_payload = f"Telemetry Data from {device_id} at {time.time()}".encode()
        pad_len = max(0, config.PAYLOAD_SIZE_BYTES - len(base_payload))
        payload = base_payload + b'\0' * pad_len

        # Pull poly_key from assumed secure transport / registry
        poly_key = bytes.fromhex(devices_info[device_id]["poly_key"])

        start = time.perf_counter()

        # ── Step 1: Attribute hashing (with salt) ──
        t0 = time.perf_counter()
        l_strict = [hashlib.sha256(a.encode() + salt).digest()
                    for a in strict_attrs]
        t_hash = (time.perf_counter() - t0) * 1000
        metrics["attr_hashing"].append(t_hash)

        # ── Step 2: AES-GCM symmetric encryption ──
        t0 = time.perf_counter()
        k_sess = os.urandom(32)
        aes = SecureAESGCM(key=k_sess)
        c_data, nonce = aes.encrypt(payload, associated_data=None)
        t_aes = (time.perf_counter() - t0) * 1000
        metrics["aes_gcm_encrypt"].append(t_aes)

        # ── Step 3: Ring-LWE key encapsulation ──
        t0 = time.perf_counter()
        r = _sample_gaussian(N_RING, SIGMA_GAUSS, Q_MOD)
        e_u = _sample_gaussian(N_RING, SIGMA_GAUSS, Q_MOD)
        e_ep_r = _sample_gaussian(N_RING, SIGMA_GAUSS, Q_MOD)
        e_r = _sample_gaussian(N_RING, SIGMA_GAUSS, Q_MOD)

        m_poly = _encode_key_to_poly(k_sess, Q_MOD, N_RING)

        u = (_poly_mul_mod(a_pub, r, Q_MOD) + e_u) % Q_MOD
        C_ep = (_poly_mul_mod(B_epoch, r, Q_MOD) + e_ep_r) % Q_MOD
        C_attrs = {}
        for attr in strict_attrs:
            e_attr_r = _sample_gaussian(N_RING, SIGMA_GAUSS, Q_MOD)
            C_attrs[attr] = (_poly_mul_mod(B_attrs[attr], r, Q_MOD)
                             + e_attr_r) % Q_MOD
        # C_r includes epoch + strict attribute masks (standard Ring-LWE ABE).
        # Phase 6 decryption cancels each mask via ψ_i · u subtraction.
        C_r = (m_poly
               + _poly_mul_mod(B_epoch, r, Q_MOD)
               + sum((_poly_mul_mod(B_attrs[a], r, Q_MOD)
                      for a in strict_attrs),
                     np.zeros(N_RING, dtype=np.int64))
               + e_r) % Q_MOD
        t_rlwe = (time.perf_counter() - t0) * 1000
        metrics["ringlwe_encap"].append(t_rlwe)

        # ── Step 4: Serialize outer_ct + Poly1305 tag ──
        t0 = time.perf_counter()
        outer_ct_bytes = (u.tobytes() + C_ep.tobytes() + C_r.tobytes()
                          + b"".join(C_attrs[a].tobytes()
                                     for a in strict_attrs))
        
        poly_tag = _poly1305_mac(poly_key, outer_ct_bytes)
        t_poly = (time.perf_counter() - t0) * 1000
        metrics["poly1305_tag"].append(t_poly)

        t_total = (time.perf_counter() - start) * 1000
        metrics["total_device_latency"].append(t_total)

        packets.append({
            "device_id": device_id,
            "u":         u.tolist(),
            "C_ep":      C_ep.tolist(),
            "C_r":       C_r.tolist(),
            "C_attrs":   {a: C_attrs[a].tolist() for a in strict_attrs},
            "outer_ct_len": len(outer_ct_bytes),
            "c_data":    c_data.hex(),
            "c_data_len": len(c_data),
            "nonce":     nonce.hex(),
            "poly_tag":  poly_tag.hex(),
            "salt":      salt.hex(),
            "strict_attrs": strict_attrs,
        })
        print(f"  -> Device {i} Packet Generated ({t_total:.2f} ms)")

    loader = DataLoader()
    phase_dir = Path(__file__).parent
    loader.save_metrics(phase_dir, metrics, filename="ref4_metrics.json")
    loader.save_data(phase_dir, "ref4_packets.json", packets)

    print("\n" + "=" * 60)
    print("Phase 2 (Ref [4]) Finished.")
    avg = sum(metrics["total_device_latency"]) / num_devices
    print(f"Avg Device Latency: {avg:.2f} ms")
    print("=" * 60)
    return metrics

if __name__ == "__main__":
    run_phase2_ref4()
