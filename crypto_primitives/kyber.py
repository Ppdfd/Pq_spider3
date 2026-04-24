"""
CRYSTALS-Kyber KEM  —  Pure-Python Reference Implementation
==========================================================
Implements Kyber512 (NIST ML-KEM) key encapsulation mechanism.

Ring:  R_q = Z_q[X] / (X^256 + 1),   q = 3329,   n = 256
Kyber512 params: k=2, eta1=3, eta2=2, du=10, dv=4

Operations:
  - NTT-based polynomial multiplication in Z_q[X]/(X^256+1)
  - Centered Binomial Distribution (CBD) noise sampling
  - Compress / Decompress for ciphertext compactness
  - CPA-secure PKE (KeyGen, Encrypt, Decrypt)
  - CCA-secure KEM via Fujisaki-Okamoto (Encapsulate, Decapsulate)

Matches the PQ-SPIDER paper equations (4), (8):
    (pk_FN, sk_FN) <- KeyGenKyber(1^lambda)
    (c_kem,i, k_kem,i) <- EncapKyber(pk_FN)
"""

import os
import hashlib

# ─────────────────────── Kyber-512 Parameters ───────────────────────
KYBER_N   = 256
KYBER_Q   = 3329
KYBER_K   = 2
KYBER_ETA1 = 3
KYBER_ETA2 = 2
KYBER_DU  = 10
KYBER_DV  = 4

# ───────────── NTT zeta table (bit-reversed, root = 17) ─────────────

def _compute_zetas():
    g = 17                       # primitive 512-th root of unity mod q
    zetas = [0] * 128
    for i in range(128):
        bits = 0; tmp = i
        for _ in range(7):
            bits = (bits << 1) | (tmp & 1); tmp >>= 1
        zetas[i] = pow(g, bits, KYBER_Q)
    return zetas

ZETAS = _compute_zetas()

# ─────────────────────── NTT / INTT ─────────────────────────────────

def _ntt(r):
    """In-place forward NTT (Cooley-Tukey)."""
    k = 1; length = 128
    while length >= 2:
        start = 0
        while start < 256:
            zeta = ZETAS[k]; k += 1
            for j in range(start, start + length):
                t = (zeta * r[j + length]) % KYBER_Q
                r[j + length] = (r[j] - t) % KYBER_Q
                r[j]          = (r[j] + t) % KYBER_Q
            start += 2 * length
        length >>= 1
    return r


def _inv_ntt(r):
    """In-place inverse NTT (Gentleman-Sande)."""
    k = 127; length = 2
    while length <= 128:
        start = 0
        while start < 256:
            zeta = ZETAS[k]; k -= 1
            for j in range(start, start + length):
                t = r[j]
                r[j]          = (t + r[j + length]) % KYBER_Q
                r[j + length] = (zeta * (r[j + length] - t)) % KYBER_Q
            start += 2 * length
        length <<= 1
    f = 3303                     # 256^{-1} mod 3329
    for i in range(256):
        r[i] = (r[i] * f) % KYBER_Q
    return r


def _basemul(a0, a1, b0, b1, zeta):
    r0 = (a0*b0 + a1*b1*zeta) % KYBER_Q
    r1 = (a0*b1 + a1*b0)      % KYBER_Q
    return r0, r1


def _poly_basemul(a, b):
    """Point-wise multiply two NTT-domain polynomials."""
    r = [0] * KYBER_N
    for i in range(64):
        z0 = ZETAS[64 + i]
        r[4*i],   r[4*i+1] = _basemul(a[4*i],   a[4*i+1],
                                        b[4*i],   b[4*i+1], z0)
        z1 = KYBER_Q - z0
        r[4*i+2], r[4*i+3] = _basemul(a[4*i+2], a[4*i+3],
                                        b[4*i+2], b[4*i+3], z1)
    return r

def _poly_add(a, b):
    return [(a[i] + b[i]) % KYBER_Q for i in range(KYBER_N)]

def _poly_sub(a, b):
    return [(a[i] - b[i]) % KYBER_Q for i in range(KYBER_N)]

# ──────────────────── CBD noise sampling ────────────────────────────

def _cbd(buf, eta):
    r = [0] * KYBER_N
    if eta == 2:
        for i in range(KYBER_N // 2):
            v = buf[i]
            a  = (v & 1) + ((v >> 1) & 1)
            b  = ((v >> 2) & 1) + ((v >> 3) & 1)
            r[2*i] = (a - b) % KYBER_Q
            a  = ((v >> 4) & 1) + ((v >> 5) & 1)
            b  = ((v >> 6) & 1) + ((v >> 7) & 1)
            r[2*i+1] = (a - b) % KYBER_Q
    elif eta == 3:
        for i in range(KYBER_N // 4):
            t = buf[3*i] | (buf[3*i+1] << 8) | (buf[3*i+2] << 16)
            for j in range(4):
                bits = (t >> (6*j)) & 0x3F
                a = (bits & 1) + ((bits >> 1) & 1) + ((bits >> 2) & 1)
                b = ((bits >> 3) & 1) + ((bits >> 4) & 1) + ((bits >> 5) & 1)
                r[4*i+j] = (a - b) % KYBER_Q
    return r


def _prf(key, nonce, length):
    return hashlib.shake_256(key + bytes([nonce])).digest(length)

def _xof(seed, i, j):
    return hashlib.shake_128(seed + bytes([i, j])).digest(672)

# ──────────── Polynomial serialisation / sampling ──────────────────

def _poly_sample_uniform(buf):
    r = [0] * KYBER_N; ctr = 0; pos = 0
    while ctr < KYBER_N and pos + 2 < len(buf):
        d1 = buf[pos] | ((buf[pos+1] & 0x0F) << 8)
        d2 = (buf[pos+1] >> 4) | (buf[pos+2] << 4)
        pos += 3
        if d1 < KYBER_Q:
            r[ctr] = d1; ctr += 1
        if ctr < KYBER_N and d2 < KYBER_Q:
            r[ctr] = d2; ctr += 1
    return r

def _poly_tobytes(p):
    buf = bytearray(384)
    for i in range(KYBER_N // 2):
        t0 = p[2*i] % KYBER_Q; t1 = p[2*i+1] % KYBER_Q
        buf[3*i]   =  t0 & 0xFF
        buf[3*i+1] = ((t0 >> 8) | (t1 << 4)) & 0xFF
        buf[3*i+2] =  (t1 >> 4) & 0xFF
    return bytes(buf)

def _poly_frombytes(buf):
    r = [0] * KYBER_N
    for i in range(KYBER_N // 2):
        r[2*i]   = (buf[3*i] | ((buf[3*i+1] & 0x0F) << 8)) % KYBER_Q
        r[2*i+1] = ((buf[3*i+1] >> 4) | (buf[3*i+2] << 4)) % KYBER_Q
    return r

# ──────────────────── Compress / Decompress ────────────────────────

def _compress(x, d):
    return ((x * (1 << d) + KYBER_Q // 2) // KYBER_Q) & ((1 << d) - 1)

def _decompress(x, d):
    return (x * KYBER_Q + (1 << (d-1))) >> d

def _poly_compress_bytes(p, d):
    t = [_compress(c, d) for c in p]
    if d == 4:
        buf = bytearray(128)
        for i in range(KYBER_N // 2):
            buf[i] = (t[2*i] & 0xF) | ((t[2*i+1] & 0xF) << 4)
        return bytes(buf)
    elif d == 10:
        buf = bytearray(320)
        pos = 0
        for i in range(KYBER_N // 4):
            v = [t[4*i+j] & 0x3FF for j in range(4)]
            c = v[0] | (v[1] << 10) | (v[2] << 20) | (v[3] << 30)
            for b in range(5):
                buf[pos] = (c >> (8*b)) & 0xFF; pos += 1
        return bytes(buf)
    raise ValueError(f"Unsupported d={d}")

def _poly_decompress_bytes(buf, d):
    t = [0] * KYBER_N
    if d == 4:
        for i in range(KYBER_N // 2):
            t[2*i] = buf[i] & 0xF; t[2*i+1] = (buf[i] >> 4) & 0xF
    elif d == 10:
        pos = 0
        for i in range(KYBER_N // 4):
            c = 0
            for b in range(5):
                c |= buf[pos] << (8*b); pos += 1
            t[4*i]   =  c        & 0x3FF
            t[4*i+1] = (c >> 10) & 0x3FF
            t[4*i+2] = (c >> 20) & 0x3FF
            t[4*i+3] = (c >> 30) & 0x3FF
    return [_decompress(x, d) for x in t]

def _msg_to_poly(msg):
    r = [0] * KYBER_N
    for i in range(KYBER_N):
        bit = (msg[i // 8] >> (i % 8)) & 1
        r[i] = _decompress(bit, 1)
    return r

def _poly_to_msg(p):
    msg = bytearray(32)
    for i in range(KYBER_N):
        t = _compress(p[i], 1)
        msg[i // 8] |= (t & 1) << (i % 8)
    return bytes(msg)

# ═══════════════════════ CPA-PKE ════════════════════════════════════

def _cpapke_keygen(seed):
    h = hashlib.sha3_512(seed).digest()
    rho, sigma = h[:32], h[32:64]

    A_hat = [[_poly_sample_uniform(_xof(rho, i, j))
              for j in range(KYBER_K)] for i in range(KYBER_K)]

    s = [list(_cbd(_prf(sigma, i, 64*KYBER_ETA1), KYBER_ETA1))
         for i in range(KYBER_K)]
    e = [list(_cbd(_prf(sigma, KYBER_K+i, 64*KYBER_ETA1), KYBER_ETA1))
         for i in range(KYBER_K)]

    s_hat = [_ntt(list(si)) for si in s]
    e_hat = [_ntt(list(ei)) for ei in e]

    t_hat = [[0]*KYBER_N for _ in range(KYBER_K)]
    for i in range(KYBER_K):
        for j in range(KYBER_K):
            t_hat[i] = _poly_add(t_hat[i], _poly_basemul(A_hat[i][j], s_hat[j]))
        t_hat[i] = _poly_add(t_hat[i], e_hat[i])

    pk = b''.join(_poly_tobytes(t_hat[i]) for i in range(KYBER_K)) + rho
    sk = b''.join(_poly_tobytes(s_hat[i]) for i in range(KYBER_K))
    return pk, sk


def _cpapke_enc(pk, msg, coins):
    t_hat = [_poly_frombytes(pk[384*i:384*(i+1)]) for i in range(KYBER_K)]
    rho   = pk[384*KYBER_K:]

    A_hat = [[_poly_sample_uniform(_xof(rho, i, j))
              for j in range(KYBER_K)] for i in range(KYBER_K)]

    r  = [list(_cbd(_prf(coins, i, 64*KYBER_ETA1), KYBER_ETA1))
          for i in range(KYBER_K)]
    e1 = [list(_cbd(_prf(coins, KYBER_K+i, 64*KYBER_ETA2), KYBER_ETA2))
          for i in range(KYBER_K)]
    e2 = list(_cbd(_prf(coins, 2*KYBER_K, 64*KYBER_ETA2), KYBER_ETA2))

    r_hat = [_ntt(list(ri)) for ri in r]

    # u = INTT(A^T r_hat) + e1
    u = [[0]*KYBER_N for _ in range(KYBER_K)]
    for i in range(KYBER_K):
        for j in range(KYBER_K):
            u[i] = _poly_add(u[i], _poly_basemul(A_hat[j][i], r_hat[j]))
        u[i] = _poly_add(_inv_ntt(list(u[i])), e1[i])

    # v = INTT(t_hat^T r_hat) + e2 + decode(msg)
    v = [0] * KYBER_N
    for i in range(KYBER_K):
        v = _poly_add(v, _poly_basemul(t_hat[i], r_hat[i]))
    v = _poly_add(_poly_add(_inv_ntt(list(v)), e2), _msg_to_poly(msg))

    ct = b''.join(_poly_compress_bytes(u[i], KYBER_DU) for i in range(KYBER_K))
    ct += _poly_compress_bytes(v, KYBER_DV)
    return ct


def _cpapke_dec(sk, ct):
    u_len = 320   # 256 * 10 / 8
    u = [_poly_decompress_bytes(ct[u_len*i:u_len*(i+1)], KYBER_DU)
         for i in range(KYBER_K)]
    v = _poly_decompress_bytes(ct[u_len*KYBER_K:], KYBER_DV)

    s_hat = [_poly_frombytes(sk[384*i:384*(i+1)]) for i in range(KYBER_K)]
    u_hat = [_ntt(list(ui)) for ui in u]

    w = [0] * KYBER_N
    for i in range(KYBER_K):
        w = _poly_add(w, _poly_basemul(s_hat[i], u_hat[i]))
    w = _inv_ntt(list(w))
    return _poly_to_msg(_poly_sub(v, w))

# ═══════════════════════ CCA-KEM (FO) ══════════════════════════════

def _kem_keygen():
    d  = os.urandom(32)
    pk, sk_cpa = _cpapke_keygen(d)
    z  = os.urandom(32)
    pk_h = hashlib.sha3_256(pk).digest()
    sk_full = sk_cpa + pk + pk_h + z          # (sk || pk || H(pk) || z)
    return pk, sk_full

def _kem_encaps(pk):
    m     = hashlib.sha3_256(os.urandom(32)).digest()
    pk_h  = hashlib.sha3_256(pk).digest()
    kr    = hashlib.sha3_512(m + pk_h).digest()
    ct    = _cpapke_enc(pk, m, kr[32:64])
    ct_h  = hashlib.sha3_256(ct).digest()
    ss    = hashlib.shake_256(kr[:32] + ct_h).digest(32)
    return ct, ss

def _kem_decaps(ct, sk_full):
    L = 384 * KYBER_K
    P = L + 32
    sk_cpa = sk_full[:L]
    pk     = sk_full[L:L+P]
    pk_h   = sk_full[L+P:L+P+32]
    z      = sk_full[L+P+32:L+P+64]

    m2  = _cpapke_dec(sk_cpa, ct)
    kr  = hashlib.sha3_512(m2 + pk_h).digest()
    ct2 = _cpapke_enc(pk, m2, kr[32:64])
    ct_h = hashlib.sha3_256(ct).digest()

    if ct == ct2:
        return hashlib.shake_256(kr[:32] + ct_h).digest(32)
    return hashlib.shake_256(z + ct_h).digest(32)

# ═══════════════════ Public API ═════════════════════════════════════

class SecureKyber:
    """
    CRYSTALS-Kyber512 KEM  —  real lattice-based implementation.

    * Polynomial ring R_q = Z_q[X]/(X^256+1),  q = 3329
    * NTT-based polynomial multiplication
    * CBD noise sampling  (η1 = 3,  η2 = 2)
    * CPA-PKE + Fujisaki-Okamoto  IND-CCA2 KEM

    Matches PQ-SPIDER Eq. (4) and (8).
    """

    def __init__(self, variant="Kyber512"):
        self.variant    = variant
        self.public_key = None
        self.secret_key = None
        self.is_oqs     = False      # API compat flag

    def keygen(self):
        """(pk, sk) <- KeyGenKyber(1^lambda)  [PQ-SPIDER Eq. 4]"""
        self.public_key, self.secret_key = _kem_keygen()
        return self.public_key, self.secret_key

    def encap(self, public_key: bytes):
        """(ct, ss) <- EncapKyber(pk)  [PQ-SPIDER Eq. 8]"""
        return _kem_encaps(public_key)

    def decap(self, ciphertext: bytes, secret_key: bytes) -> bytes:
        """ss <- DecapKyber(ct, sk)"""
        return _kem_decaps(ciphertext, secret_key)
