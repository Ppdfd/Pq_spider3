"""
Phase 5 (Ref [4]): Poomekum et al. — Partial Encryption at Fog Node
======================================================================
Matches [4] Sec IV-B, Phase 4 "Partial Encryption at Fog Node":

Step 1: Ciphertext Validation — verify Poly1305 tag on outer_ct.
Step 2: Flexible Attribute Augmentation — add Sum(beta_i * C_i) to C_r.
Step 3: Digital Signing — Dilithium2 over serialized outer_ct.
Step 4: Output CT_final.
"""

import os
import sys
import time
import hashlib
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.dilithium import SecureDilithium
from utils.dataset_loader import DataLoader

N_RING = 256
Q_MOD = 8192

def _poly_mul_mod(a, b, q, n=N_RING):
    A = np.fft.fft(a.astype(np.float64), 2 * n)
    B = np.fft.fft(b.astype(np.float64), 2 * n)
    c = np.fft.ifft(A * B).real.round().astype(np.int64)
    return (c[:n] - c[n:]) % q

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

def run_phase5_ref4():
    print("=" * 60)
    print("PQ-SPIDER Phase 5 Simulation: Fog Augmentation (Ref [4] Poomekum)")
    print("=" * 60)

    metrics = {
        "poly1305_verify":         0,
        "beta_augmentation":       0,
        "dilithium_sign":          0,
        "total_fog_latency":       0,
    }

    loader = DataLoader()
    phase1_dir = Path(__file__).parent.parent / "phase1_initialization"
    phase2_dir = Path(__file__).parent.parent / "phase2_iiot_encrypt"

    try:
        setup = loader.load_data(phase1_dir, "ref4_setup.json")
        registry = loader.load_data(phase1_dir, "ref4_device_registry.json")
        ref4_packets = loader.load_data(phase2_dir, "ref4_packets.json")
    except FileNotFoundError as e:
        print(f"  ! {e}")
        return

    print(f"  -> Loaded {len(ref4_packets)} IoT packets.")
    num_packets = len(ref4_packets)
    devices_info = {d["device_id"]: d for d in registry}

    beta_matrix = {h: np.array(b, dtype=np.int64)
                   for h, b in setup["beta_matrix_fog0"].items()}

    dil = SecureDilithium()
    sk_sig = {
        "rho":     bytes.fromhex(setup["fog_sig_sk"]["rho"]),
        "sigma":   bytes.fromhex(setup["fog_sig_sk"]["sigma"]),
        "pk_hash": bytes.fromhex(setup["fog_sig_sk"]["pk_hash"]),
        "s1":      setup["fog_sig_sk"]["s1"],
        "s2":      setup["fog_sig_sk"]["s2"],
        "t0":      setup["fog_sig_sk"]["t0"],
    }

    flex_attrs_hashed = list(beta_matrix.keys())
    start_total = time.perf_counter()

    t_verify_total = 0.0
    for p in ref4_packets:
        t0 = time.perf_counter()
        
        device_id = p["device_id"]
        poly_key = bytes.fromhex(devices_info[device_id]["poly_key"])
        
        u    = np.array(p["u"],    dtype=np.int64)
        C_ep = np.array(p["C_ep"], dtype=np.int64)
        C_r  = np.array(p["C_r"],  dtype=np.int64)
        C_attrs_real = {a: np.array(v, dtype=np.int64)
                        for a, v in p["C_attrs"].items()}
        outer_ct_bytes = (u.tobytes() + C_ep.tobytes() + C_r.tobytes()
                          + b"".join(C_attrs_real[a].tobytes()
                                     for a in p["strict_attrs"]))
        tag      = bytes.fromhex(p["poly_tag"])
        ok = _poly1305_verify(poly_key, outer_ct_bytes, tag)
        assert ok, f"Poly1305 verify failed on {device_id}"
        t_verify_total += (time.perf_counter() - t0) * 1000
        
    metrics["poly1305_verify"] = t_verify_total
    print(f"[1/3] Poly1305 verify × {num_packets}: {t_verify_total:.2f} ms")

    augmented_C_rs = []
    t0 = time.perf_counter()
    for p in ref4_packets:
        C_r = np.array(p["C_r"], dtype=np.int64)
        u   = np.array(p["u"], dtype=np.int64)
        aggregate = np.zeros(N_RING, dtype=np.int64)
        for h_flex in flex_attrs_hashed:
            beta_i = beta_matrix[h_flex]
            seed = hashlib.sha256(u.tobytes() + h_flex.encode()).digest()
            rng = np.random.RandomState(int.from_bytes(seed[:4], "little"))
            C_flex_i = rng.randint(0, Q_MOD, size=N_RING).astype(np.int64)
            aggregate = (aggregate + _poly_mul_mod(beta_i, C_flex_i, Q_MOD)) % Q_MOD
        C_r_aug = (C_r + aggregate) % Q_MOD
        augmented_C_rs.append(C_r_aug.tolist())
        
    t_beta = (time.perf_counter() - t0) * 1000
    metrics["beta_augmentation"] = t_beta
    print(f"[2/5] Beta augmentation × {num_packets}: {t_beta:.2f} ms")

    batch_header = b"".join(
        np.array(p["u"], dtype=np.int64).tobytes()
        + np.array(augmented_C_rs[i], dtype=np.int64).tobytes()
        for i, p in enumerate(ref4_packets)
    )
    batch_hash = hashlib.sha256(batch_header).digest()

    t0 = time.perf_counter()
    sigma = dil.sign(batch_hash, sk_sig)
    t_sign = (time.perf_counter() - t0) * 1000
    metrics["dilithium_sign"] = t_sign
    print(f"[3/5] Dilithium sign (keygen excluded): {t_sign:.2f} ms "
          f"({len(sigma)} B signature)")

    # ────────────────────────────────────────────────────────────────
    # Paper [4] Phase 5: PARTIAL DECRYPTION AT FOG NODE
    # Sec IV-B, Phase 5 — strips flexible attribute contribution
    # so the end-user only needs strict attrs + epoch to decrypt.
    # ────────────────────────────────────────────────────────────────

    # Step 1: Dilithium signature verification (fog verifies its own Phase 4 output)
    t0 = time.perf_counter()
    pk_sig = {
        "rho": bytes.fromhex(setup["fog_sig_pk"]["rho"]),
        "t1":  setup["fog_sig_pk"]["t1"],
    }
    valid = dil.verify(batch_hash, sigma, pk_sig)
    assert valid, "Phase 5: Dilithium verify on augmented batch failed"
    t_dil_verify = (time.perf_counter() - t0) * 1000
    metrics["dilithium_verify"] = t_dil_verify
    print(f"[4/5] Dilithium verify (fog-side): {t_dil_verify:.2f} ms -> valid={valid}")

    # Step 2: Flexible Attribute Stripping
    # Fog re-computes the same aggregate it added in Phase 4 and subtracts it.
    # C_r_stripped = C_r_aug - Σ(β_i · C_flex_i)  =  original C_r
    stripped_C_rs = []
    t0 = time.perf_counter()
    for idx, p in enumerate(ref4_packets):
        C_r_aug = np.array(augmented_C_rs[idx], dtype=np.int64)
        u = np.array(p["u"], dtype=np.int64)
        aggregate = np.zeros(N_RING, dtype=np.int64)
        for h_flex in flex_attrs_hashed:
            beta_i = beta_matrix[h_flex]
            seed = hashlib.sha256(u.tobytes() + h_flex.encode()).digest()
            rng = np.random.RandomState(int.from_bytes(seed[:4], "little"))
            C_flex_i = rng.randint(0, Q_MOD, size=N_RING).astype(np.int64)
            aggregate = (aggregate + _poly_mul_mod(beta_i, C_flex_i, Q_MOD)) % Q_MOD
        C_r_stripped = (C_r_aug - aggregate) % Q_MOD
        stripped_C_rs.append(C_r_stripped.tolist())
    t_strip = (time.perf_counter() - t0) * 1000
    metrics["flex_stripping"] = t_strip
    print(f"[5/5] Flex attribute stripping × {num_packets}: {t_strip:.2f} ms")

    metrics["total_fog_latency"] = (time.perf_counter() - start_total) * 1000

    # Step 3: Package stripped_ct with new Poly1305 tag for user
    strip_poly_key = os.urandom(32)
    stripped_ct_entries = []
    for idx, p in enumerate(ref4_packets):
        u = np.array(p["u"], dtype=np.int64)
        C_ep = np.array(p["C_ep"], dtype=np.int64)
        stripped_bytes = u.tobytes() + C_ep.tobytes() + np.array(stripped_C_rs[idx], dtype=np.int64).tobytes()
        from cryptography.hazmat.primitives import poly1305 as p1305
        tagger = p1305.Poly1305(strip_poly_key)
        tagger.update(stripped_bytes)
        tag = tagger.finalize()
        stripped_ct_entries.append({
            "device_id":   p["device_id"],
            "u":           p["u"],
            "C_ep":        p["C_ep"],
            "C_r_stripped": stripped_C_rs[idx],
            "c_data":      p["c_data"] if "c_data" in p else None,
            "nonce":       p["nonce"] if "nonce" in p else None,
            "strict_attrs": p["strict_attrs"],
            "strip_tag":   tag.hex(),
        })

    loader.save_metrics(Path(__file__).parent, metrics, filename="ref4_metrics.json")
    loader.save_data(Path(__file__).parent, "ref4_augmented.json", {
        "augmented_C_rs": augmented_C_rs,
        "batch_sigma":    sigma.hex(),
        "batch_hash":     batch_hash.hex(),
    })
    loader.save_data(Path(__file__).parent, "ref4_stripped.json", {
        "stripped_ct": stripped_ct_entries,
        "strip_poly_key": strip_poly_key.hex(),
    })

    print("\n" + "=" * 60)
    print("Phase 5 (Ref [4]) Finished.")
    print(f"Total Fog Latency : {metrics['total_fog_latency']:.2f} ms")
    print(f"  Phase 4 (augment): {t_beta:.2f} ms + sign {t_sign:.2f} ms")
    print(f"  Phase 5 (strip):   verify {t_dil_verify:.2f} ms + strip {t_strip:.2f} ms")
    print("=" * 60)
    return metrics

if __name__ == "__main__":
    run_phase5_ref4()

