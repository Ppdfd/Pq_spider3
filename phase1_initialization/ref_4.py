"""
Phase 1 (Ref [4]): Poomekum et al. — Ring-LWE CP-ABE System Setup
==================================================================
Implements the System Setup phase of:
  P. Poomekum, A. Suriyawong, S. Fugkeaw,
  "Fine-Grained and Lightweight Quantum-Resistant Access Control System
   With Efficient Revocation for IoT Cloud," IEEE OJCOMS, 2025.

Paper parameters (Sec IV-B, Phase 1):
  - Ring dimension n = 256
  - Modulus q = 2^13 = 8192
  - Gaussian sigma = 3.2
  - Polynomial ring R_q = Z_q[x]/(x^n + 1)

Paper operations (Algorithm 1):
  1. (n, q, sigma) ← SystemParameters()
  2. salt ← RNG()
  3. a ← R_q                                  (public polynomial)
  4. s ← D_sigma                              (master secret polynomial)
  5. For each attr in universe:
        (psi_attr, B_attr) ← GenAttributePair(a, sigma)
        where B_attr = a·psi_attr + e_attr
        h_attr ← H(attr || salt)              (salted hash for policy hiding)
        MSK.psi_table[h_attr] ← psi_attr
        MPK.B_table[h_attr] ← B_attr
  6. MPK = {n, q, sigma, a}, MSK = {s}

KeyGen (Algorithm 2):
  - For each strict attribute: SK_user ← psi_vector
  - Fog node generates Dilithium2 signing keys  (pk_sig, sk_sig)
  - tk.beta ← InitializeBetaMatrix() via PRF for flexible attributes
"""

import os
import sys
import config
import time
import hashlib
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crypto_primitives.dilithium import SecureDilithium
from utils.dataset_loader import DataLoader

# ─────────────────── Paper [4] Parameters ──────────────────────────
N_RING     = 256     # ring dimension
Q_MOD      = 8192    # 2^13 modulus
SIGMA_GAUSS = 3.2    # discrete Gaussian width


def _sample_gaussian(n, sigma, q):
    """Sample polynomial coefficients from discrete Gaussian N(0, sigma^2)."""
    # Box-Muller then round
    samples = np.random.normal(0.0, sigma, size=n).round().astype(np.int64)
    return samples % q


def _sample_uniform_poly(n, q):
    """Sample uniformly random polynomial in R_q."""
    return np.random.randint(0, q, size=n).astype(np.int64)


def _poly_mul_mod(a, b, q, n=N_RING):
    """Multiply polynomials in Z_q[x]/(x^n+1) via FFT-based negacyclic
    convolution — O(n log n).  See phase2/ref_4.py for fairness note.
    """
    A = np.fft.fft(a.astype(np.float64), 2 * n)
    B = np.fft.fft(b.astype(np.float64), 2 * n)
    c = np.fft.ifft(A * B).real.round().astype(np.int64)
    return (c[:n] - c[n:]) % q


def _hash_attr(attr, salt):
    """Salted SHA-256 attribute label (Eq: h_attr = H(attr || salt))."""
    return hashlib.sha256(attr.encode() + salt).hexdigest()


def gen_attribute_pair(a_poly, q, n, sigma):
    """
    GenAttributePair(a, sigma):
      psi ← D_sigma  (secret)
      e   ← D_sigma  (noise)
      B   = a · psi + e  (mod q)
    Returns (psi, B).
    """
    psi = _sample_gaussian(n, sigma, q)
    e   = _sample_gaussian(n, sigma, q)
    B   = (_poly_mul_mod(a_poly, psi, q, n) + e) % q
    return psi, B


def run_phase1_ref4():
    print("=" * 60)
    print("PQ-SPIDER Phase 1 Simulation: System Setup (Ref [4] Poomekum et al.)")
    print("=" * 60)

    metrics = {
        "aa_setup": 0,
        "user_keygen": 0,
        "fog_node_init": [],
        "total_init": 0,
        "paper_params": {"n": N_RING, "q": Q_MOD, "sigma": SIGMA_GAUSS}
    }

    start_total = time.perf_counter()

    # ── Step 1: System Initialization (Algorithm 1, lines 1-4) ──
    print("[1/4] Trusted Authority Setup (Ring-LWE CP-ABE)...")
    t0 = time.perf_counter()

    # (n, q, sigma) ← SystemParameters()  — already set as constants
    # salt ← RNG()
    salt = os.urandom(32)

    # a ← R_q  (public polynomial, uniformly random)
    a_poly = _sample_uniform_poly(N_RING, Q_MOD)

    # s ← D_sigma  (master secret polynomial)
    s_master = _sample_gaussian(N_RING, SIGMA_GAUSS, Q_MOD)

    # For each attribute: (psi, B) pair with salted hash label
    universe = config.CP_ABE_UNIVERSE
    psi_table = {}
    B_table = {}
    for attr in universe:
        psi, B = gen_attribute_pair(a_poly, Q_MOD, N_RING, SIGMA_GAUSS)
        h = _hash_attr(attr, salt)
        psi_table[h] = psi
        B_table[h] = B

    # Epoch key pair (Algorithm 2, lines 2-4)
    psi_epoch, B_epoch = gen_attribute_pair(a_poly, Q_MOD, N_RING, SIGMA_GAUSS)

    t_aa = (time.perf_counter() - t0) * 1000
    metrics["aa_setup"] = t_aa
    print(f"  -> TA Setup Completed: {t_aa:.2f} ms")
    print(f"  -> Generated {len(universe)} attribute pairs + epoch pair")
    print(f"  -> MPK = (n, q, sigma, a); MSK = (s, psi_table)")

    # ── Step 2: User KeyGen (Algorithm 2, lines 6-9) ──
    print("\n[2/4] Registering Authorized User (epoch-based key generation)...")
    t0 = time.perf_counter()

    user_attributes = config.USER_ATTRIBUTES
    # sk_user ← {psi_epoch}
    sk_user = {"psi_epoch": psi_epoch.tolist()}
    # For each strict attribute, add psi from table
    for attr in user_attributes:
        h = _hash_attr(attr, salt)
        sk_user[h] = psi_table[h].tolist()

    t_kg = (time.perf_counter() - t0) * 1000
    metrics["user_keygen"] = t_kg
    print(f"  -> User KeyGen Completed: {t_kg:.2f} ms")
    print(f"  -> Attributes: {user_attributes}")

    # ── Step 3: Fog Node Credentials (Algorithm 2, line 17) ──
    # Fog nodes get Dilithium2 signing keys + beta matrix (via PRF)
    num_fog_nodes = config.NUM_GLOBAL_NODES
    print(f"\n[3/4] Initializing {num_fog_nodes} Fog Nodes (Dilithium keys + beta)...")

    fog_nodes = []
    flex_attrs = config.FLEX_ATTRIBUTES
    for i in range(num_fog_nodes):
        t_fn0 = time.perf_counter()

        # (pk_sig, sk_sig) ← GenSignKeys()  — Dilithium2
        dil = SecureDilithium()
        pk_sig, sk_sig = dil.keygen()

        # beta ← InitializeBetaMatrix() via PRF(seed_fog_attr)
        #   For each flexible attribute, derive a beta polynomial via PRF
        beta_matrix = {}
        for attr in flex_attrs:
            seed = hashlib.sha256(("fog_seed_" + str(i) + "_" + attr).encode()).digest()
            # PRF: seed → polynomial coefficients
            rng = np.random.RandomState(
                int.from_bytes(seed[:4], "little"))
            beta_poly = rng.randint(0, Q_MOD, size=N_RING).astype(np.int64)
            beta_matrix[_hash_attr(attr, salt)] = beta_poly

        t_fn = (time.perf_counter() - t_fn0) * 1000

        fog_nodes.append({
            "id": i,
            "pk_sig_len": len(pk_sig["rho"]) + len(pk_sig["t1"]) * 256 * 2,
            "num_beta_entries": len(beta_matrix),
            "init_time": t_fn,
        })
        metrics["fog_node_init"].append(t_fn)
        print(f"  -> Fog Node {i} Ready ({t_fn:.2f} ms)")

    # ── Step 4: Device Registry (Simulation for Poly1305 Keys) ──
    # since paper assume send using secure channel (peppo)
    print("\n[4/4] Initializing IIoT Devices (poly_key registry)...")
    device_registry = []
    num_devices = config.NUM_DEVICES
    for i in range(num_devices):
        device_id = f"IoT-DEV-{i:03d}"
        poly_key = os.urandom(32)
        device_registry.append({
            "device_id": device_id,
            "poly_key": poly_key.hex()
        })

    metrics["total_init"] = (time.perf_counter() - start_total) * 1000

    # Save metrics
    loader = DataLoader()
    phase_dir = Path(__file__).parent
    loader.save_metrics(phase_dir, metrics, filename="ref4_metrics.json")
    
    loader.save_data(phase_dir, "ref4_device_registry.json", device_registry)

    # Persist all public + secret key material so phase2/5/6 can run
    # against the SAME parameters.  Without this, each phase samples
    # its own salt and public polynomial, and cross-phase decryption
    # is impossible.
    loader.save_data(phase_dir, "ref4_setup.json", {
        "salt":        salt.hex(),
        "a_pub":       a_poly.tolist(),
        "psi_epoch":   psi_epoch.tolist(),
        "B_epoch":     B_epoch.tolist(),
        "psi_table":   {h: psi.tolist() for h, psi in psi_table.items()},
        "B_table":     {h: B.tolist()   for h, B   in B_table.items()},
        "universe":    universe,
        "user_attributes": user_attributes,
        "flex_attrs":  flex_attrs,
        # Fog-0's beta matrix (used by phase5/ref_4); in a real system
        # each fog node would have its own, but for the benchmark we
        # use a single shared one.
        "beta_matrix_fog0": {h: beta.tolist()
                             for h, beta in beta_matrix.items()},
        # Save one Dilithium key pair for the fog (pk only as hex; sk
        # components as lists of ints).  Phase5 uses sk to sign and
        # phase6 uses pk to verify.
        "fog_sig_pk": {
            "rho": pk_sig["rho"].hex(),
            "t1":  [list(p) for p in pk_sig["t1"]],
        },
        "fog_sig_sk": {
            "rho":    sk_sig["rho"].hex(),
            "sigma":  sk_sig["sigma"].hex(),
            "pk_hash": sk_sig["pk_hash"].hex(),
            "s1":     [list(p) for p in sk_sig["s1"]],
            "s2":     [list(p) for p in sk_sig["s2"]],
            "t0":     [list(p) for p in sk_sig["t0"]],
        },
    })

    print("\n" + "=" * 60)
    print("Phase 1 (Ref [4]) Finished.")
    print(f"Total Latency:       {metrics['total_init']:.2f} ms")
    print(f"Average Fog Init:    {sum(metrics['fog_node_init'])/num_fog_nodes:.2f} ms")
    print("=" * 60)
    return metrics


if __name__ == "__main__":
    run_phase1_ref4()
