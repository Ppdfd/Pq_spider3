"""
Phase 6 (Ref [4]) — User Final Decryption
===================================================================
Paper [4] Sec IV-B, Phase 6: End-User Final Decryption

The user receives the stripped ciphertext from the fog node (Phase 5
already verified Dilithium and removed flexible attribute components).

Step 1: Poly1305 verify on stripped_ct
Step 2: Noise cancellation — subtract ψ_epoch·u and ψ_i·u for each
        strict attribute to recover encoded session key polynomial
Step 3: Decode polynomial coefficients to 256-bit AES key
Step 4: AES-GCM decrypt data payload

CHANGES vs previous version:
  [CORRECTNESS] Now loads ref4_stripped.json (fog-stripped ciphertext)
                instead of ref4_augmented.json (fog-augmented).
  [CORRECTNESS] Dilithium verify REMOVED — paper says fog does it in
                Phase 5, not the user.  This also moves ~7ms of latency
                from user to fog, matching the paper's design.
  [CORRECTNESS] Noise cancellation uses C_r_stripped (= original C_r
                from Phase 3), which contains epoch + strict attribute
                masks.  Previously used C_r_aug which still had flex
                attribute noise, causing AES key recovery to fail.
"""

import sys
import time
import hashlib
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.aes_gcm import SecureAESGCM
from utils.dataset_loader import DataLoader

N_RING = 256
Q_MOD = 8192


def _poly_mul_mod(a, b, q, n=N_RING):
    A = np.fft.fft(a.astype(np.float64), 2 * n)
    B = np.fft.fft(b.astype(np.float64), 2 * n)
    c = np.fft.ifft(A * B).real.round().astype(np.int64)
    return (c[:n] - c[n:]) % q


def _decode_poly_to_key(poly, q, key_bytes=32):
    half_q = q // 2
    bits = []
    for i in range(key_bytes * 8):
        v = int(poly[i]) % q
        d0 = min(v, q - v)
        d1 = abs(v - half_q)
        bits.append(0 if d0 <= d1 else 1)
    out = bytearray(key_bytes)
    for i, b in enumerate(bits):
        if b:
            out[i // 8] |= 1 << (i % 8)
    return bytes(out)


def _poly1305_verify(key32: bytes, data: bytes, tag: bytes) -> bool:
    from cryptography.hazmat.primitives import poly1305
    from cryptography.exceptions import InvalidSignature
    p = poly1305.Poly1305(key32)
    p.update(data)
    try:
        p.verify(tag)
        return True
    except InvalidSignature:
        return False


def run_phase6_ref4():
    print("=" * 60)
    print("PQ-SPIDER Phase 6 Simulation: User Decryption (Ref [4] Poomekum)")
    print("=" * 60)

    metrics = {
        "poly1305_verify":      0,
        "lattice_noise_cancel": 0,
        "poly_decode":          0,
        "aes_gcm_decrypt":      0,
        "total_user_latency":   0,
    }

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase2_dir = Path(__file__).parent.parent / "phase2_iiot_encrypt"
    phase5_dir = Path(__file__).parent.parent / "phase5_fog_node"

    try:
        setup    = loader.load_data(phase1_dir, "ref4_setup.json")
        packets  = loader.load_data(phase2_dir, "ref4_packets.json")
        stripped = loader.load_data(phase5_dir, "ref4_stripped.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        return

    stripped_entries = stripped["stripped_ct"]
    strip_poly_key = bytes.fromhex(stripped["strip_poly_key"])

    print(f"  -> Loaded {len(stripped_entries)} stripped packets.")

    salt = bytes.fromhex(setup["salt"])
    psi_epoch = np.array(setup["psi_epoch"], dtype=np.int64)
    psi_strict = {}
    for attr in setup["user_attributes"]:
        h = hashlib.sha256(attr.encode() + salt).hexdigest()
        psi_strict[attr] = np.array(setup["psi_table"][h], dtype=np.int64)

    # Pre-decode all data OUTSIDE the timer (audit fairness fix)
    pre = []
    for i, sc in enumerate(stripped_entries):
        u = np.array(sc["u"], dtype=np.int64)
        C_ep = np.array(sc["C_ep"], dtype=np.int64)
        C_r_stripped = np.array(sc["C_r_stripped"], dtype=np.int64)
        stripped_bytes = u.tobytes() + C_ep.tobytes() + C_r_stripped.tobytes()
        tag = bytes.fromhex(sc["strip_tag"])

        # Load original packet data for AES decrypt
        p = packets[i]
        c_data = bytes.fromhex(p["c_data"])
        nonce = bytes.fromhex(p["nonce"])

        pre.append({
            "device_id":     sc["device_id"],
            "u":             u,
            "C_r_stripped":  C_r_stripped,
            "stripped_bytes": stripped_bytes,
            "tag":           tag,
            "c_data":        c_data,
            "nonce":         nonce,
            "strict_attrs":  sc["strict_attrs"],
        })

    start_total = time.perf_counter()

    # ── Step 1: Poly1305 verify on stripped_ct ──
    # (Dilithium verify was already done by fog in Phase 5)
    t0 = time.perf_counter()
    for r in pre:
        ok = _poly1305_verify(strip_poly_key, r["stripped_bytes"], r["tag"])
        assert ok, f"Poly1305 verify failed on {r['device_id']}"
    t_poly = (time.perf_counter() - t0) * 1000
    metrics["poly1305_verify"] = t_poly
    print(f"[1/3] Poly1305 verify × {len(pre)}: {t_poly:.2f} ms")

    # ── Step 2: Lattice noise cancellation × N ──
    # C_r_stripped = m·⌊q/2⌋ + B_epoch·r + Σ(B_i·r) + e_r
    # Subtract ψ_epoch·u and each ψ_i·u to recover m·⌊q/2⌋ + small noise
    cancelled_polys = []
    t0 = time.perf_counter()
    for r in pre:
        u = r["u"]
        m_prime = r["C_r_stripped"].copy()
        # Cancel epoch mask
        mask_ep = _poly_mul_mod(psi_epoch, u, Q_MOD)
        m_prime = (m_prime - mask_ep) % Q_MOD
        # Cancel each strict attribute mask
        for attr in r["strict_attrs"]:
            psi_i = psi_strict[attr]
            mask_i = _poly_mul_mod(psi_i, u, Q_MOD)
            m_prime = (m_prime - mask_i) % Q_MOD
        cancelled_polys.append(m_prime)
    t_cancel = (time.perf_counter() - t0) * 1000
    metrics["lattice_noise_cancel"] = t_cancel
    print(f"[2/3] Noise cancel × {len(pre)}: {t_cancel:.2f} ms")

    # ── Step 3: Poly decode + AES-GCM decrypt × N ──
    t0 = time.perf_counter()
    candidate_keys = [_decode_poly_to_key(p, Q_MOD, key_bytes=32)
                      for p in cancelled_polys]
    t_decode = (time.perf_counter() - t0) * 1000
    metrics["poly_decode"] = t_decode

    t0 = time.perf_counter()
    recovered_count = 0
    failed_count = 0
    for i, r in enumerate(pre):
        try:
            aes = SecureAESGCM(key=candidate_keys[i])
            _ = aes.decrypt(r["c_data"], r["nonce"], associated_data=None)
            recovered_count += 1
        except Exception:
            failed_count += 1
    t_aes = (time.perf_counter() - t0) * 1000
    metrics["aes_gcm_decrypt"] = t_aes
    print(f"[3/3] Poly decode: {t_decode:.2f} ms, "
          f"AES-GCM decrypt × {len(pre)}: {t_aes:.2f} ms "
          f"(recovered={recovered_count}, tag-failed={failed_count})")

    metrics["total_user_latency"] = (time.perf_counter() - start_total) * 1000

    loader.save_metrics(Path(__file__).parent, metrics,
                        filename="ref4_metrics.json")

    print("\n" + "=" * 60)
    print("Phase 6 (Ref [4]) Finished.")
    print(f"Total User Latency: {metrics['total_user_latency']:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase6_ref4()
