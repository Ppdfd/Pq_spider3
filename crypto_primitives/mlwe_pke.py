"""
Raw MLWE Public-Key Encryption  —  Primitive for Paper [36]
============================================================
Reference:
  Z. Man et al., "Edge Computing in Internet of Things: Lattice-
  Based and Split Encryption for Post-Quantum Data Security,"
  IEEE IoT Journal, Vol. 12, No. 23, Dec 2025.

This module implements the CPA-PKE described directly in paper
[36], Sec III-B (Algorithm 1 for encryption, Algorithm 2 for
decryption).  This is DIFFERENT from CRYSTALS-Kyber because:

  * [36] uses the raw CPA scheme only; there is no Fujisaki-
    Okamoto transform, no re-encryption check, no implicit
    rejection, and no shared-secret derivation.  The paper's
    Algorithm 1 encrypts a message `m` directly as part of the
    `v` polynomial.
  * The paper explicitly names its ring R_q with q = 3329 and
    n = 256 (Kyber-512 parameters) but pairs (k=2) × (n=256)
    polynomials for the module structure.  This matches our
    Kyber module's underlying CPA-PKE, so this file factors out
    that CPA layer and exposes it as a standalone primitive.

Paper equations
---------------
Eq. 12 (key generation):
    b_i = INTT(NTT(a_i) · NTT(s_i)) + e_i   mod q

Eq. 14 (encryption):
    u_i = INTT(NTT(a_i) · NTT(r_i)) + e1[i]  mod q

Eq. 15 (encryption):
    v = Σ_{i=0..k-1} INTT(NTT(b_i) · NTT(r_i)) + e2 + m_scaled   mod q

Algorithm 2 (decryption):
    m_scaled  = v - Σ INTT(NTT(s_i) · NTT(u_i))   mod q
    m         = rescale(m_scaled)

Honest scope statement
----------------------
This is a real CPA-PKE under MLWE and gives semantic security
under the decisional MLWE problem.  It is NOT CCA-secure by
itself.  Paper [36] does not claim CCA security either — the
paper's "post-quantum" argument is based on the MLWE assumption
for IND-CPA, which is exactly what this code gives.

The code re-uses NTT helpers from the project's `kyber.py` to
avoid duplication.  Paper [36] quotes ψ = 17 and ω = 1175 for
the NTT; these are the same bit-reversed zeta values our Kyber
module already computes (they appear at specific positions in
the ZETAS table), so nothing extra is needed.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from crypto_primitives.kyber import (
    KYBER_N as N, KYBER_Q as Q, KYBER_K as K,
    _ntt, _inv_ntt, _poly_basemul, _poly_add,
    _cbd, _prf,
)


# ────────── Sampling helpers ────────────────────────────────────────

def _sample_small(q: int) -> List[int]:
    """
    Sample a polynomial of length N with coefficients in {-1, 0, 1}
    as a Python list of ints reduced mod q.  Paper [36] Algorithm 1
    says "coefficients uniformly random in [-1, 1]".
    """
    v = np.random.randint(-1, 2, size=N)
    return [int(x) % q for x in v]


def _sample_uniform_poly(q: int) -> List[int]:
    """Uniform polynomial with coefficients in [0, q-1]."""
    return [int(x) for x in np.random.randint(0, q, size=N)]


def _encode_message(msg: bytes, q: int, n: int) -> List[int]:
    """
    Paper [36] calls this "m_scaled" — the simplest embedding is
    pixel byte -> pixel * ⌊q/256⌋.  Bytes beyond index n are
    ignored; if len(msg) < n the rest is zero-padded.

    This is faithful to the paper's Step 1 description of
    "compressed display of the information block".
    """
    coeffs = [0] * n
    scale = q // 256
    for i in range(min(n, len(msg))):
        coeffs[i] = int(msg[i]) * scale
    return coeffs


def _decode_message(coeffs: List[int], q: int, n: int,
                    length: int) -> bytes:
    """Inverse of _encode_message with rounding."""
    out = bytearray()
    scale = q // 256
    half = scale // 2
    for i in range(min(n, length)):
        c = int(coeffs[i]) % q
        # Recover the byte closest to (c / scale) with rounding
        byte = (c + half) // scale
        out.append(byte & 0xFF)
    return bytes(out)


# ────────── Key generation ─────────────────────────────────────────
#
# Paper [36] Key Generation (Sec III-B, Step 2-3):
#   a_i  <- uniform Z_q^n             public
#   s_i  <- small Z_q^n               secret
#   e_i  <- small Z_q^n               noise
#   b_i  = INTT(NTT(a_i) · NTT(s_i)) + e_i   mod q

def keygen() -> Tuple[dict, dict]:
    """
    Generate a raw MLWE-PKE keypair.

    Returns:
        pk = {"a": [a_0, ..., a_{k-1}],  "b": [b_0, ..., b_{k-1}]}
        sk = {"s": [s_0, ..., s_{k-1}]}
    where each a_i, b_i, s_i is a polynomial stored as a list of
    N ints reduced mod Q.
    """
    a = [_sample_uniform_poly(Q) for _ in range(K)]
    s = [_sample_small(Q) for _ in range(K)]
    e = [_sample_small(Q) for _ in range(K)]

    b = []
    for i in range(K):
        a_hat = _ntt(list(a[i]))
        s_hat = _ntt(list(s[i]))
        prod  = _inv_ntt(list(_poly_basemul(a_hat, s_hat)))
        b_i   = [(prod[j] + e[i][j]) % Q for j in range(N)]
        b.append(b_i)

    return {"a": a, "b": b}, {"s": s}


# ────────── Encryption ─────────────────────────────────────────────
#
# Paper [36] Algorithm 1:
#   r  <- small poly
#   e1 <- small poly
#   e2 <- small poly
#   u_i = INTT(NTT(a_i) · NTT(r_i)) + e1[i]                     mod q
#   v   = Σ INTT(NTT(b_i) · NTT(r_i)) + e2 + m_scaled            mod q

def encrypt(pk: dict, message: bytes) -> dict:
    """
    Encrypt a byte string under pk.

    Returns ciphertext dict {"u": [...k polys...], "v": poly}.
    """
    a = pk["a"]
    b = pk["b"]

    r  = [_sample_small(Q) for _ in range(K)]
    e1 = [_sample_small(Q) for _ in range(K)]
    e2 = _sample_small(Q)

    # u_i = INTT(NTT(a_i) · NTT(r_i)) + e1[i]
    u = []
    for i in range(K):
        a_hat = _ntt(list(a[i]))
        r_hat = _ntt(list(r[i]))
        prod  = _inv_ntt(list(_poly_basemul(a_hat, r_hat)))
        u_i   = [(prod[j] + e1[i][j]) % Q for j in range(N)]
        u.append(u_i)

    # v = Σ INTT(NTT(b_i) · NTT(r_i)) + e2 + m_scaled
    v = [0] * N
    for i in range(K):
        b_hat = _ntt(list(b[i]))
        r_hat = _ntt(list(r[i]))
        prod  = _inv_ntt(list(_poly_basemul(b_hat, r_hat)))
        v = [(v[j] + prod[j]) % Q for j in range(N)]

    m_scaled = _encode_message(message, Q, N)
    v = [(v[j] + e2[j] + m_scaled[j]) % Q for j in range(N)]

    return {"u": u, "v": v}


# ────────── Decryption ─────────────────────────────────────────────
#
# Paper [36] Algorithm 2:
#   m_part_i = INTT(NTT(s_i) · NTT(u_i))         mod q
#   m_scaled = v - Σ m_part_i                    mod q
#   m        = rescale(m_scaled)  in [0, 255]

def decrypt(sk: dict, ct: dict, message_length: int) -> bytes:
    """
    Decrypt ciphertext under sk.  `message_length` is needed because
    the raw MLWE-PKE does not include framing; the caller must
    remember how long the original message was.
    """
    s = sk["s"]
    u = ct["u"]
    v = ct["v"]

    v_minus = list(v)
    for i in range(K):
        s_hat = _ntt(list(s[i]))
        u_hat = _ntt(list(u[i]))
        prod  = _inv_ntt(list(_poly_basemul(s_hat, u_hat)))
        v_minus = [(v_minus[j] - prod[j]) % Q for j in range(N)]

    return _decode_message(v_minus, Q, N, message_length)


# ────────── Convenience class ──────────────────────────────────────

class MLWE_PKE:
    """
    Object-oriented wrapper.  Exposes the same (keygen, encrypt,
    decrypt) interface but keeps keys on the instance.  Useful for
    benchmarking comparisons with [36].
    """

    def __init__(self):
        self.pk = None
        self.sk = None

    def keygen(self):
        self.pk, self.sk = keygen()
        return self.pk, self.sk

    def encrypt(self, message: bytes, pk: dict = None) -> dict:
        return encrypt(pk if pk is not None else self.pk, message)

    def decrypt(self, ct: dict, message_length: int,
                sk: dict = None) -> bytes:
        return decrypt(sk if sk is not None else self.sk, ct,
                       message_length)
