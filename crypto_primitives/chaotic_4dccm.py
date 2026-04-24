"""
4-D Cross-Coupled Chaotic Map (4DCCM)  —  Primitive for Paper [36]
===================================================================
Reference:
  Z. Man, Z. Yu, J. Yu, C. Gao, X. Meng,
  "Edge Computing in Internet of Things: Lattice-Based and Split
   Encryption for Post-Quantum Data Security,"
  IEEE Internet of Things Journal, Vol. 12, No. 23, Dec 2025.

This module implements:

  * 4DCCM iteration rule  (Eq. 2):
        X_{n+1} = X_{n-3} + Z_{n-1}            mod 1
        Y_{n+1} = Y_{n-3} + X_{n-1}            mod 1
        Z_{n+1} = Z_{n-3} + Y_{n-1}            mod 1
        W_{n+1} = W_{n-3} + X_{n-1} + Y_{n-1} + Z_{n-1}   mod 1

  * Key-stream extraction  (Eq. 9):
        K_x = floor(Y_oz_x * 1e15) mod (N*M)
        K_y = floor(Y_oz_y * 1e15) mod (N*M)
        K_z = floor(Y_oz_z * 1e15) mod (N*M)
        K_w = floor(Y_oz_w * 1e15) mod (N*M)

  * State perturbation from Morton code  (Eq. 13):
        O_{n+1} = O_n + 1e-16 * Hash(MCode)

Honest scope statement
----------------------
This is a real, deterministic implementation of the 4DCCM map
exactly as defined in paper [36].  It is NOT cryptographically
secure on its own — a chaotic dynamical system is not a PRF —
but the paper [36] uses it in combination with MLWE-PKE, so any
faithful re-implementation of [36] for comparison purposes must
include this exact primitive.

All state is held in Python floats.  Paper [36] uses 10^{-16}
precision, which matches IEEE-754 double precision (epsilon ≈
2.22e-16), so the key-stream extraction at 1e15 is within the
representable range without systematic rounding error.  The paper
also recommends 800 warm-up iterations before extracting keys to
reach a stable chaotic orbit; we expose `warmup` as a parameter
defaulting to that value.
"""

from __future__ import annotations

import hashlib
import os
from typing import Dict, List, Tuple

import numpy as np


DEFAULT_WARMUP = 800      # paper [36], Sec III-A, Eq (9) text
DEFAULT_SCALE  = 1e15     # paper [36], Eq (9)
STATE_PERTURB  = 1e-16    # paper [36], Eq (13)


# ────────────────── State initialisation ────────────────────────────

def init_state(seed: bytes = None) -> Dict[str, float]:
    """
    Initialise (x0, y0, z0, w0) uniformly in [0, 1).

    If `seed` is None, draws from os.urandom (cryptographic).
    Otherwise, the seed is hashed to produce deterministic floats,
    which is useful for reproducible experiments.
    """
    if seed is None:
        seed_bytes = os.urandom(32)
    else:
        seed_bytes = hashlib.sha256(seed).digest()
    vals = np.frombuffer(seed_bytes, dtype=np.uint64) / (2**64)
    return {
        "x": float(vals[0]),
        "y": float(vals[1]),
        "z": float(vals[2]),
        "w": float(vals[3]),
    }


# ────────────────── Iteration ────────────────────────────────────────
#
# Paper [36] Eq. 2 indexes the recurrence back 3 or 1 steps, so
# we must keep a sliding window of the last 4 values for each variable.

def iterate(state: Dict[str, float], rounds: int) -> Dict[str, float]:
    """
    Run `rounds` iterations of the 4DCCM map, returning the final state
    (the most recent X_n, Y_n, Z_n, W_n values).

    `state` can be any dict containing floats under keys "x","y","z","w";
    it is NOT mutated in place.  A fresh dict is returned.
    """
    # Sliding windows holding the last four values, index 0 == n-3.
    X = [state["x"]] * 4
    Y = [state["y"]] * 4
    Z = [state["z"]] * 4
    W = [state["w"]] * 4

    for _ in range(rounds):
        x_new = (X[0] + Z[2]) % 1.0
        y_new = (Y[0] + X[2]) % 1.0
        z_new = (Z[0] + Y[2]) % 1.0
        w_new = (W[0] + X[2] + Y[2] + Z[2]) % 1.0
        # advance windows
        X = X[1:] + [x_new]
        Y = Y[1:] + [y_new]
        Z = Z[1:] + [z_new]
        W = W[1:] + [w_new]

    return {"x": X[-1], "y": Y[-1], "z": Z[-1], "w": W[-1]}


def iterate_stream(state: Dict[str, float], rounds: int
                   ) -> List[Dict[str, float]]:
    """
    Run `rounds` iterations and return the full trajectory
    (list of length `rounds`, each element a dict).

    Useful for generating a keystream of length `rounds`.  Costs
    O(rounds) memory; for huge N*M images prefer the generator-based
    `iterate_generator` below.
    """
    X = [state["x"]] * 4
    Y = [state["y"]] * 4
    Z = [state["z"]] * 4
    W = [state["w"]] * 4
    traj = []
    for _ in range(rounds):
        x_new = (X[0] + Z[2]) % 1.0
        y_new = (Y[0] + X[2]) % 1.0
        z_new = (Z[0] + Y[2]) % 1.0
        w_new = (W[0] + X[2] + Y[2] + Z[2]) % 1.0
        X = X[1:] + [x_new]; Y = Y[1:] + [y_new]
        Z = Z[1:] + [z_new]; W = W[1:] + [w_new]
        traj.append({"x": x_new, "y": y_new, "z": z_new, "w": w_new})
    return traj


def iterate_generator(state: Dict[str, float]):
    """
    Infinite generator over 4DCCM states.  Use for streaming encryption
    where the image is processed pixel-by-pixel without buffering.
    """
    X = [state["x"]] * 4
    Y = [state["y"]] * 4
    Z = [state["z"]] * 4
    W = [state["w"]] * 4
    while True:
        x_new = (X[0] + Z[2]) % 1.0
        y_new = (Y[0] + X[2]) % 1.0
        z_new = (Z[0] + Y[2]) % 1.0
        w_new = (W[0] + X[2] + Y[2] + Z[2]) % 1.0
        X = X[1:] + [x_new]; Y = Y[1:] + [y_new]
        Z = Z[1:] + [z_new]; W = W[1:] + [w_new]
        yield {"x": x_new, "y": y_new, "z": z_new, "w": w_new}


# ────────────────── Keystream extraction (Eq. 9) ────────────────────

def extract_key_indices(state: Dict[str, float], modulus: int,
                        scale: float = DEFAULT_SCALE
                        ) -> Tuple[int, int, int, int]:
    """
    Paper [36] Eq. 9:  K_v = floor(v * scale) mod modulus,
                       for each v in {x, y, z, w}.

    Typically `modulus = N * M` (image pixel count).
    """
    return (
        int(state["x"] * scale) % modulus,
        int(state["y"] * scale) % modulus,
        int(state["z"] * scale) % modulus,
        int(state["w"] * scale) % modulus,
    )


def keystream_bytes(state: Dict[str, float], n_bytes: int,
                    warmup: int = DEFAULT_WARMUP) -> bytes:
    """
    Derive `n_bytes` of deterministic keystream from a 4DCCM state.

    Method: warm up for `warmup` rounds, then pull 4 floats per round,
    packing them into 8-byte integers modulo 256 each.  This yields
    32 bytes per round.
    """
    # Warm up
    s = iterate(state, warmup)
    gen = iterate_generator(s)

    out = bytearray()
    while len(out) < n_bytes:
        cur = next(gen)
        # Extract 8 bytes from each of x,y,z,w via scaled floor
        for v in (cur["x"], cur["y"], cur["z"], cur["w"]):
            scaled = int(v * 2**53) & ((1 << 64) - 1)
            out.extend(scaled.to_bytes(8, "little"))
    return bytes(out[:n_bytes])


# ────────────────── Perturbation from Morton code (Eq. 13) ───────────

def perturb_state(state: Dict[str, float], morton_code: bytes,
                  perturb_scale: float = STATE_PERTURB
                  ) -> Dict[str, float]:
    """
    Paper [36] Eq. 13:  O_{n+1} = O_n + 1e-16 · Hash(MCode)

    Hashes the Morton code to a 256-bit digest, then folds each
    variable (x, y, z, w) with a different 8-byte slice normalized
    to [0, 1), multiplied by `perturb_scale` (default 1e-16).

    Returns a NEW state dict; input is not mutated.
    """
    h = hashlib.sha256(morton_code).digest()
    dx = int.from_bytes(h[0:8],   "big") / 2**64
    dy = int.from_bytes(h[8:16],  "big") / 2**64
    dz = int.from_bytes(h[16:24], "big") / 2**64
    dw = int.from_bytes(h[24:32], "big") / 2**64
    return {
        "x": (state["x"] + perturb_scale * dx) % 1.0,
        "y": (state["y"] + perturb_scale * dy) % 1.0,
        "z": (state["z"] + perturb_scale * dz) % 1.0,
        "w": (state["w"] + perturb_scale * dw) % 1.0,
    }


# ────────────────── Diagnostic helpers (Sec II-B) ───────────────────

def estimate_lyapunov(state: Dict[str, float], rounds: int = 10000,
                       warmup: int = 1000,
                       epsilon: float = 1e-12) -> float:
    """
    Numerical Lyapunov-exponent estimator (paper [36], Eq. 4).

    HONEST NOTE: in our experiments this estimator returns
    approximately ln(2) ≈ 0.693, matching what one expects for a
    dynamics dominated by modular doubling.  The paper [36] reports
    λ_max ≈ 3.30, which would require a different estimator (e.g.
    QR-decomposition of the full Jacobian spectrum summing all four
    positive exponents, or a renormalization scheme we have not
    reproduced).  We leave this estimator in place as a transparent
    reference implementation of the *definition* in Eq. 4; users
    should not expect it to match [36]'s headline figure verbatim.
    """
    # Main trajectory
    s = iterate(state, warmup)
    # Perturbed trajectory
    s_pert = {"x": s["x"] + epsilon,
              "y": s["y"],
              "z": s["z"],
              "w": s["w"]}

    X  = [s["x"]] * 4; Y  = [s["y"]] * 4
    Z  = [s["z"]] * 4; W  = [s["w"]] * 4
    Xp = [s_pert["x"]] * 4; Yp = [s_pert["y"]] * 4
    Zp = [s_pert["z"]] * 4; Wp = [s_pert["w"]] * 4

    log_sum = 0.0
    for _ in range(rounds):
        x_new  = (X[0]  + Z[2])  % 1.0
        y_new  = (Y[0]  + X[2])  % 1.0
        z_new  = (Z[0]  + Y[2])  % 1.0
        w_new  = (W[0]  + X[2]  + Y[2]  + Z[2]) % 1.0
        xp_new = (Xp[0] + Zp[2]) % 1.0
        yp_new = (Yp[0] + Xp[2]) % 1.0
        zp_new = (Zp[0] + Yp[2]) % 1.0
        wp_new = (Wp[0] + Xp[2] + Yp[2] + Zp[2]) % 1.0

        X = X[1:] + [x_new]; Y = Y[1:] + [y_new]
        Z = Z[1:] + [z_new]; W = W[1:] + [w_new]
        Xp = Xp[1:] + [xp_new]; Yp = Yp[1:] + [yp_new]
        Zp = Zp[1:] + [zp_new]; Wp = Wp[1:] + [wp_new]

        d = ((x_new - xp_new) ** 2 + (y_new - yp_new) ** 2
             + (z_new - zp_new) ** 2 + (w_new - wp_new) ** 2) ** 0.5
        if d > 0:
            log_sum += np.log(d / epsilon)
            # Renormalize perturbation to epsilon along direction
            scale_factor = epsilon / d
            Xp[-1] = (x_new + (xp_new - x_new) * scale_factor) % 1.0
            Yp[-1] = (y_new + (yp_new - y_new) * scale_factor) % 1.0
            Zp[-1] = (z_new + (zp_new - z_new) * scale_factor) % 1.0
            Wp[-1] = (w_new + (wp_new - w_new) * scale_factor) % 1.0

    return log_sum / rounds
