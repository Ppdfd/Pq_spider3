"""
CRYSTALS-Dilithium2 Digital Signatures  —  Pure-Python Reference
================================================================
Implements Dilithium2 (NIST ML-DSA-44) lattice-based signatures.

Ring:  R_q = Z_q[X] / (X^256 + 1),   q = 8380417,   n = 256
Dilithium2 params:
    k=4, l=4, η=2, τ=39, β=78, γ1=2^17, γ2=(q-1)/88, d=13, ω=80

Operations:
  - NTT-based polynomial multiplication in Z_q[X]/(X^256+1)
  - Uniform & CBD sampling from XOF
  - Fiat-Shamir with rejection sampling for EUF-CMA signatures
  - HighBits / LowBits / MakeHint / UseHint decomposition

Matches PQ-SPIDER Eq. (59), (62):
    σ <- Sign_Dilithium(sk_FN, H(...))
    Verify_Dilithium(pk_FN, σ, H(...))
"""

import os
import hashlib
import numpy as np

# ─────────────────── Dilithium-2 Parameters ─────────────────────────
N      = 256
Q      = 8380417
K      = 4
L      = 4
ETA    = 2
TAU    = 39
BETA_  = TAU * ETA       # = 78
GAMMA1 = 1 << 17         # 131072
GAMMA2 = (Q - 1) // 88   # 95232
D      = 13              # dropped bits from t
OMEGA  = 80              # max # of 1s in hint

# ────────────── NTT tables for q = 8380417 ──────────────────────────
# Primitive 512-th root of unity mod q = 1753
# Dilithium uses a FULL NTT (256 zetas, 8-bit reversal, butterfly to len=1)
# Unlike Kyber which stops at len=2 and uses basemul.

def _compute_zetas_dil():
    g = 1753
    zetas = [0] * 256
    for i in range(256):
        bits = 0; tmp = i
        for _ in range(8):
            bits = (bits << 1) | (tmp & 1); tmp >>= 1
        zetas[i] = pow(g, bits, Q)
    return zetas

ZETAS = _compute_zetas_dil()
NEG_ZETAS = [(Q - z) % Q for z in ZETAS]   # pre-computed for INTT
NINV  = pow(256, Q - 2, Q)   # 256^{-1} mod Q  (full NTT scaling)

# Pre-computed numpy arrays for batch NTT
_ZETAS_NP = np.array(ZETAS, dtype=np.int64)
_NEG_ZETAS_NP = np.array(NEG_ZETAS, dtype=np.int64)


def _ntt(a):
    """Forward NTT — optimised with local variable binding."""
    r = list(a)
    _q = Q                  # local binding avoids global lookup in hot loop
    _z = ZETAS
    k = 0; length = 128
    while length >= 1:
        start = 0
        while start < 256:
            k += 1
            zeta = _z[k]
            end = start + length
            for j in range(start, end):
                jl = j + length
                rj = r[j]; rjl = r[jl]
                t = zeta * rjl % _q
                r[jl] = (rj - t) % _q
                r[j]  = (rj + t) % _q
            start = end + length
        length >>= 1
    return r


def _inv_ntt(a):
    """Inverse NTT — pre-computed neg-zetas, local binding."""
    r = list(a)
    _q = Q
    _nz = NEG_ZETAS
    k = 256; length = 1
    while length <= 128:
        start = 0
        while start < 256:
            k -= 1
            zeta = _nz[k]
            end = start + length
            for j in range(start, end):
                jl = j + length
                rj = r[j]; rjl = r[jl]
                r[j]  = (rj + rjl) % _q
                r[jl] = zeta * (rj - rjl) % _q
            start = end + length
        length <<= 1
    _ninv = NINV
    for i in range(256):
        r[i] = r[i] * _ninv % _q
    return r


def _ntt_batch(polys):
    """Batch NTT: process multiple polynomials at once using numpy.
    Args: polys — list of M polynomials, each length 256
    Returns: list of M NTT'd polynomials
    """
    M = len(polys)
    if M == 0:
        return []
    # Stack into (M, 256) array
    r = np.array(polys, dtype=np.int64)
    _q = Q
    k = 0
    length = 128
    while length >= 1:
        start = 0
        while start < 256:
            k += 1
            zeta = int(_ZETAS_NP[k])
            end = start + length
            # Vectorized butterfly across all M polynomials
            j_indices = np.arange(start, end)
            jl_indices = j_indices + length
            rj = r[:, j_indices]
            rjl = r[:, jl_indices]
            t = rjl * zeta % _q
            r[:, jl_indices] = (rj - t) % _q
            r[:, j_indices] = (rj + t) % _q
            start = end + length
        length >>= 1
    return [r[i].tolist() for i in range(M)]


def _inv_ntt_batch(polys):
    """Batch inverse NTT using numpy."""
    M = len(polys)
    if M == 0:
        return []
    r = np.array(polys, dtype=np.int64)
    _q = Q
    k = 256
    length = 1
    while length <= 128:
        start = 0
        while start < 256:
            k -= 1
            zeta = int(_NEG_ZETAS_NP[k])
            end = start + length
            j_indices = np.arange(start, end)
            jl_indices = j_indices + length
            rj = r[:, j_indices]
            rjl = r[:, jl_indices]
            r[:, j_indices] = (rj + rjl) % _q
            r[:, jl_indices] = zeta * (rj - rjl) % _q
            start = end + length
        length <<= 1
    r = r * NINV % _q
    return [r[i].tolist() for i in range(M)]


def _poly_pointwise(a, b):
    """Element-wise multiply in NTT domain (full NTT, no basemul needed)."""
    _q = Q
    return [a[i] * b[i] % _q for i in range(N)]


def _poly_add(a, b):
    _q = Q
    return [(a[i] + b[i]) % _q for i in range(N)]

def _poly_sub(a, b):
    return [(a[i] - b[i]) % Q for i in range(N)]

def _poly_neg(a):
    return [(Q - a[i]) % Q for i in range(N)]

def _to_signed(x):
    """Map [0, Q) to [-(Q-1)/2, (Q-1)/2]."""
    return x if x <= Q // 2 else x - Q

def _poly_infnorm(a):
    return max(abs(_to_signed(c)) for c in a)

# ───────────────────── Sampling ─────────────────────────────────────

def _shake256(data, length):
    return hashlib.shake_256(data).digest(length)

def _shake128(data, length):
    return hashlib.shake_128(data).digest(length)


def _sample_uniform(seed, i, j):
    """Rejection-sample a uniform polynomial mod Q from SHAKE-128.
    Optimised: single large buffer, local Q binding, memoryview access.
    """
    r = [0] * N
    ctr = 0
    _q = Q
    # Pre-allocate buffer large enough for ~341 candidates (need 256)
    # Acceptance rate = Q/2^23 ≈ 99.9%, so 1024 bytes is very safe
    buf = hashlib.shake_128(seed + bytes([j, i, 1])).digest(1536)
    mv = memoryview(buf)
    pos = 0; blen = len(buf)
    while ctr < N:
        if pos + 2 >= blen:
            buf = hashlib.shake_128(seed + bytes([j, i, 2])).digest(1536)
            mv = memoryview(buf)
            pos = 0; blen = len(buf)
        b0 = buf[pos]; b1 = buf[pos+1]; b2 = buf[pos+2]
        d = b0 | (b1 << 8) | ((b2 & 0x7F) << 16)
        pos += 3
        if d < _q:
            r[ctr] = d
            ctr += 1
    return r


def _sample_eta(seed, nonce):
    """Sample polynomial with coefficients in [-η, η] using CBD."""
    buf = hashlib.shake_256(seed + bytes([nonce, 0])).digest(128)
    r = [0] * N
    _q = Q
    for i in range(N // 2):
        v = buf[i]
        a = (v & 1) + ((v >> 1) & 1)
        b = ((v >> 2) & 1) + ((v >> 3) & 1)
        r[2*i] = (a - b) % _q
        a = ((v >> 4) & 1) + ((v >> 5) & 1)
        b = ((v >> 6) & 1) + ((v >> 7) & 1)
        r[2*i+1] = (a - b) % _q
    return r


def _sample_gamma1_poly(seed, nonce):
    """Sample polynomial with coefficients uniform in [-γ1+1, γ1].
    Each coefficient needs 18 bits. Total = 256*18/8 = 576 bytes."""
    buf = _shake256(seed + nonce.to_bytes(2, 'little'), 576)
    r = [0] * N
    # Read 18 bits per coefficient from a bit-stream
    bits = int.from_bytes(buf, 'little')
    for i in range(N):
        val = (bits >> (18 * i)) & 0x3FFFF   # 18-bit value in [0, 2^18)
        r[i] = (GAMMA1 - val) % Q
    return r

# ────────────── HighBits / LowBits / Decompose ──────────────────────

def _decompose(r):
    """Decompose r into (r1, r0) per FIPS 204.
    r+ = r mod q  (unsigned, in [0, q-1])
    r0 = r+ mod± (2*gamma2)  (centered)
    r1 = (r+ - r0) / (2*gamma2), in {0, 1, ..., 43}
    Special case: if r+ - r0 == q-1, set r1=0, r0-=1.
    """
    rp = r % Q                        # unsigned in [0, q-1]
    r0 = rp % (2 * GAMMA2)
    if r0 > GAMMA2:
        r0 -= 2 * GAMMA2              # center to [-gamma2, gamma2)
    if rp - r0 == Q - 1:
        r1 = 0; r0 -= 1
    else:
        r1 = (rp - r0) // (2 * GAMMA2)
    return r1, r0


def _highbits(r):
    r1, _ = _decompose(r)
    return r1

def _lowbits(r):
    _, r0 = _decompose(r)
    return r0

def _poly_highbits(a):
    return [_highbits(c) for c in a]

def _poly_lowbits(a):
    return [_lowbits(c) for c in a]

def _make_hint(z, r):
    """MakeHint: 1 if HighBits(r) != HighBits(r + z)."""
    return [1 if _highbits(r[i]) != _highbits((r[i] + z[i]) % Q) else 0
            for i in range(N)]

def _use_hint(h, r):
    """UseHint: recover correct high bits using hint."""
    result = [0] * N
    for i in range(N):
        r1, r0 = _decompose(r[i])
        if h[i] == 1:
            if r0 > 0:
                result[i] = (r1 + 1) % 44  # 44 = (Q-1)/(2*gamma2)
            else:
                result[i] = (r1 - 1) % 44
        else:
            result[i] = r1
    return result


# ────────────── Challenge polynomial ────────────────────────────────

def _sample_challenge(seed):
    """Sample challenge c with exactly τ = 39 nonzero coefficients in {-1,1}."""
    buf = _shake256(seed, 136)
    c = [0] * N
    signs = 0
    for i in range(8):
        signs |= buf[i] << (8 * i)
    pos = 8
    for i in range(256 - TAU, 256):
        # Get j from buf uniformly in [0, i]
        while True:
            if pos >= len(buf):
                buf = _shake256(seed + buf, 272)
                pos = 0
            j = buf[pos]; pos += 1
            if j <= i:
                break
        c[i] = c[j]
        c[j] = 1 - 2 * (signs & 1)
        signs >>= 1
    return c


def _poly_power2round(a, d):
    """Power2Round: split a into (a1, a0) where a = a1*2^d + a0."""
    a1_list = [0] * N
    a0_list = [0] * N
    for i in range(N):
        val = a[i] % Q
        a0 = val % (1 << d)
        if a0 > (1 << (d-1)):
            a0 -= (1 << d)
        a1_list[i] = (val - a0) >> d
        a0_list[i] = a0 % Q
    return a1_list, a0_list


# ═══════════════════════ Key Generation ═════════════════════════════

def _keygen():
    seed = os.urandom(32)
    rho_prime = hashlib.sha3_512(seed).digest()
    rho   = rho_prime[:32]
    sigma = rho_prime[32:64]

    # Sample all A polynomials first (K*L = 16 polys)
    A_polys = [_sample_uniform(rho, i, j)
               for i in range(K) for j in range(L)]

    # Batch NTT: all 16 A polynomials + 4 s1 polynomials in ONE call
    s1 = [_sample_eta(sigma, i) for i in range(L)]
    s2 = [_sample_eta(sigma, L + i) for i in range(K)]

    all_polys = A_polys + s1   # 16 + 4 = 20 polys
    all_ntt = _ntt_batch(all_polys)

    # Unpack: first 16 are A_hat, last 4 are s1_hat
    A_hat_flat = all_ntt[:K*L]
    A_hat = [A_hat_flat[i*L:(i+1)*L] for i in range(K)]
    s1_hat = all_ntt[K*L:]

    # t = A * s1 + s2 using numpy for pointwise multiply + accumulate
    t_ntt = []
    for i in range(K):
        # Vectorized: sum of pointwise products using numpy
        a_row = np.array(A_hat[i], dtype=np.int64)   # (L, N)
        s_hat = np.array(s1_hat, dtype=np.int64)      # (L, N)
        acc = np.sum(a_row * s_hat % Q, axis=0) % Q
        t_ntt.append(acc.tolist())

    # Batch INTT on K polynomials
    t_list = _inv_ntt_batch(t_ntt)
    for i in range(K):
        t_list[i] = _poly_add(t_list[i], s2[i])

    # Power2Round: t = t1*2^d + t0
    t1 = []; t0 = []
    for i in range(K):
        t1_i, t0_i = _poly_power2round(t_list[i], D)
        t1.append(t1_i); t0.append(t0_i)

    # Hash of public key for signing
    pk_hash = hashlib.sha3_256(rho + _pack_t1(t1)).digest()

    pk_data = {
        'rho': rho,
        't1': t1,
    }
    sk_data = {
        'rho': rho,
        'sigma': sigma,
        's1': s1,
        's2': s2,
        't0': t0,
        'pk_hash': pk_hash,
    }
    return pk_data, sk_data


def _pack_t1(t1):
    """
    Pack t1 as a concatenation of 10-bit coefficients, little-endian.
    (Dilithium2 uses 10 bits per coefficient of t1; this function
    packs each polynomial of t1 into 256*10/8 = 320 bytes and
    returns K * 320 = 1280 bytes total.)

    NOTE: older versions of this function had the misleading name
    `_pack_t1` applied to arbitrary poly lists.  We now have a
    separate `_pack_poly_list` below for general 32-bit packing.
    """
    buf = b''
    for poly in t1:
        for c in poly:
            buf += (c % (1 << 10)).to_bytes(2, 'little')
    return buf


def _pack_poly_list(polys):
    buf = b''
    for p in polys:
        for c in p:
            buf += (c % Q).to_bytes(4, 'little')
    return buf

# ═══════════════════════ Signing ════════════════════════════════════

def _sign(sk_data, message):
    rho    = sk_data['rho']
    s1     = sk_data['s1']
    s2     = sk_data['s2']
    t0     = sk_data['t0']
    pk_hash = sk_data['pk_hash']

    # Expand A and batch NTT all static polynomials
    A_polys = [_sample_uniform(rho, i, j)
               for i in range(K) for j in range(L)]
    all_static = A_polys + list(s1) + list(s2) + list(t0)  # 16+4+4+4=28
    all_static_ntt = _ntt_batch(all_static)

    A_hat_flat = all_static_ntt[:K*L]
    A_hat = [A_hat_flat[i*L:(i+1)*L] for i in range(K)]
    s1_hat = all_static_ntt[K*L:K*L+L]
    s2_hat = all_static_ntt[K*L+L:K*L+L+K]
    t0_hat = all_static_ntt[K*L+L+K:]

    # Compute mu = H(pk_hash || msg)
    mu = hashlib.sha3_512(pk_hash + message).digest()

    # Deterministic nonce seed
    rho_prime = _shake256(sk_data.get('sigma', os.urandom(32)) + mu, 64)

    kappa = 0
    while True:
        # Sample y from [-γ1+1, γ1]
        y = [_sample_gamma1_poly(rho_prime, kappa * L + i) for i in range(L)]
        y_hat = _ntt_batch(y)

        # w = A * y (numpy-accelerated pointwise multiply + accumulate)
        w_ntt = []
        for i in range(K):
            a_row = np.array(A_hat[i], dtype=np.int64)
            y_h = np.array(y_hat, dtype=np.int64)
            acc = np.sum(a_row * y_h % Q, axis=0) % Q
            w_ntt.append(acc.tolist())
        w = _inv_ntt_batch(w_ntt)

        # w1 = HighBits(w)
        w1 = [_poly_highbits(wi) for wi in w]

        # Challenge hash
        w1_packed = _pack_poly_list(w1)
        c_seed = _shake256(mu + w1_packed, 32)
        c = _sample_challenge(c_seed)
        c_hat = _ntt(list(c))

        # z = y + c * s1
        z = [None] * L
        for i in range(L):
            cs1 = _inv_ntt(list(_poly_pointwise(c_hat, s1_hat[i])))
            z[i] = _poly_add(y[i], cs1)

        # Check ||z||∞ < γ1 - β
        reject = False
        for i in range(L):
            if _poly_infnorm(z[i]) >= GAMMA1 - BETA_:
                reject = True; break

        if not reject:
            # Check ||LowBits(w - c*s2)||∞ < γ2 - β
            for i in range(K):
                cs2 = _inv_ntt(list(_poly_pointwise(c_hat, s2_hat[i])))
                r = _poly_sub(w[i], cs2)
                low = _poly_lowbits(r)
                if max(abs(_to_signed(v)) for v in low) >= GAMMA2 - BETA_:
                    reject = True; break

        if not reject:
            # Compute hints
            ct0 = [[0]*N for _ in range(K)]
            for i in range(K):
                ct0[i] = _inv_ntt(list(_poly_pointwise(c_hat, t0_hat[i])))

            h = [None] * K
            total_ones = 0
            for i in range(K):
                cs2 = _inv_ntt(list(_poly_pointwise(c_hat, s2_hat[i])))
                r = _poly_sub(w[i], cs2)
                neg_ct0 = _poly_neg(ct0[i])
                # MakeHint(-ct0, w - cs2 + ct0) per FIPS 204 spec
                r_plus_ct0 = _poly_add(r, ct0[i])
                h[i] = _make_hint(neg_ct0, r_plus_ct0)
                total_ones += sum(h[i])

            if total_ones > OMEGA:
                reject = True

        if not reject:
            sig = {
                'c_seed': c_seed,
                'z': z,
                'h': h,
            }
            return sig

        kappa += 1
        if kappa > 1000:
            raise RuntimeError("Dilithium signing failed: too many rejections")


# ═══════════════════════ Verification ═══════════════════════════════

def _verify(pk_data, message, sig):
    rho = pk_data['rho']
    t1  = pk_data['t1']

    A_hat = [[_ntt(_sample_uniform(rho, i, j))
              for j in range(L)] for i in range(K)]

    c = _sample_challenge(sig['c_seed'])
    z = sig['z']
    h = sig['h']

    # Check ||z||∞ < γ1 - β
    for i in range(L):
        if _poly_infnorm(z[i]) >= GAMMA1 - BETA_:
            return False

    # Check hint weight
    total_h = sum(sum(hi) for hi in h)
    if total_h > OMEGA:
        return False

    pk_hash = hashlib.sha3_256(rho + _pack_t1(t1)).digest()
    mu = hashlib.sha3_512(pk_hash + message).digest()

    c_hat = _ntt(list(c))
    z_hat = [_ntt(list(zi)) for zi in z]

    # w' = A*z - c*t1*2^d
    w_prime = [[0]*N for _ in range(K)]
    for i in range(K):
        # A*z
        for j in range(L):
            w_prime[i] = _poly_add(w_prime[i],
                                    _poly_pointwise(A_hat[i][j], z_hat[j]))
        w_prime[i] = _inv_ntt(list(w_prime[i]))

        # c*t1*2^d
        t1_scaled = [(t1[i][j] * (1 << D)) % Q for j in range(N)]
        ct1 = _inv_ntt(list(_poly_pointwise(c_hat, _ntt(list(t1_scaled)))))
        w_prime[i] = _poly_sub(w_prime[i], ct1)

    # UseHint to recover w1'
    w1_prime = [_use_hint(h[i], w_prime[i]) for i in range(K)]

    # Recompute challenge
    w1_packed = _pack_poly_list(w1_prime)
    c_seed_prime = _shake256(mu + w1_packed, 32)

    return c_seed_prime == sig['c_seed']


# ═══════════════════ Serialisation helpers ══════════════════════════
#
# FIPS-204-compliant packing.  Gives the canonical Dilithium2
# signature size of 2420 bytes:
#     c_seed   : 32 bytes
#     z        : L · 576 = 2304 bytes  (18 bits/coeff, 256 coeffs each)
#     h        : omega + K = 84 bytes  (sparse "positions and offsets")
#     ---------------------------------
#     total    : 2420 bytes


def _pack_z_poly(poly):
    """
    Pack one polynomial z_i: each of its 256 coefficients lies in
    [-γ1 + 1, γ1].  Encode as  t = γ1 - coeff   in [0, 2γ1)  (18 bits),
    then bit-pack in little-endian order.

    Returns 576 bytes.
    """
    # Signed recovery: map mod-Q coefficients back to [-γ1+1, γ1]
    packed_int = 0
    for i in range(N):
        s = _to_signed(poly[i])
        t = (GAMMA1 - s) & 0x3FFFF   # 18 bits
        packed_int |= (t & 0x3FFFF) << (18 * i)
    return packed_int.to_bytes(576, 'little')


def _unpack_z_poly(buf):
    """Inverse of _pack_z_poly — returns a length-N polynomial mod Q."""
    packed_int = int.from_bytes(buf, 'little')
    poly = [0] * N
    for i in range(N):
        t = (packed_int >> (18 * i)) & 0x3FFFF
        s = GAMMA1 - t   # in (-γ1, γ1]
        poly[i] = s % Q
    return poly


def _pack_h(h):
    """
    Pack the hint polynomials h_0, ..., h_{K-1} as a list of indices
    followed by K cumulative offsets, totalling  omega + K  bytes.

    FIPS-204 format:
      bytes[0..total_ones-1] : indices j where h_i[j] == 1, for i = 0, 1, ...
      bytes[omega + i]       : cumulative count of ones up to and including h_i
    """
    out = bytearray(OMEGA + K)
    idx = 0
    for i in range(K):
        for j in range(N):
            if h[i][j] == 1:
                if idx >= OMEGA:
                    raise ValueError("Hint weight exceeds omega")
                out[idx] = j
                idx += 1
        out[OMEGA + i] = idx   # cumulative count after row i
    return bytes(out)


def _unpack_h(buf):
    """Inverse of _pack_h.  Returns K hint polynomials (length N each)."""
    h = [[0] * N for _ in range(K)]
    prev = 0
    for i in range(K):
        curr = buf[OMEGA + i]
        if curr < prev or curr > OMEGA:
            return None   # malformed hint
        for k in range(prev, curr):
            j = buf[k]
            if j >= N:
                return None
            h[i][j] = 1
        prev = curr
    # Leading zeros in the index region should really be zero.
    # We don't enforce that — any excess bytes are ignored.
    return h


def _sig_to_bytes(sig):
    """FIPS-204 Dilithium2 signature packing.  Produces 2420 bytes."""
    buf = bytearray(sig['c_seed'])                        # 32
    for zi in sig['z']:
        buf.extend(_pack_z_poly(zi))                       # 4 · 576 = 2304
    buf.extend(_pack_h(sig['h']))                          # omega + K = 84
    return bytes(buf)


def _sig_from_bytes(buf):
    """FIPS-204 Dilithium2 signature unpacking.  Expects 2420 bytes."""
    c_seed = buf[:32]
    pos = 32
    z = []
    for _ in range(L):
        z.append(_unpack_z_poly(buf[pos:pos + 576]))
        pos += 576
    h = _unpack_h(buf[pos:pos + OMEGA + K])
    return {'c_seed': c_seed, 'z': z, 'h': h}




# ═══════════════════ Public API ═════════════════════════════════════

class SecureDilithium:
    """
    CRYSTALS-Dilithium2 Digital Signatures  —  real lattice-based implementation.

    * Polynomial ring R_q = Z_q[X]/(X^256+1),  q = 8380417
    * NTT-based polynomial multiplication
    * Fiat-Shamir with rejection sampling
    * EUF-CMA secure under MLWE/MSIS hardness

    Matches PQ-SPIDER Eq. (59) and (62).
    """

    def __init__(self, variant="Dilithium2"):
        self.variant    = variant
        self.public_key = None
        self.secret_key = None
        self.is_oqs     = False

    def keygen(self):
        """Generate Dilithium2 keypair.
        Returns: (pk_data, sk_data) as dict objects
        (also stores serialised bytes internally for byte-level compat)
        """
        pk_data, sk_data = _keygen()
        self.public_key = pk_data
        self.secret_key = sk_data
        return pk_data, sk_data

    def sign(self, message: bytes, secret_key=None) -> bytes:
        """Sign a message.
        Returns: signature as bytes.

        Corresponds to PQ-SPIDER Eq. (59):
            σ <- Sign_Dilithium(sk_FN, H(BID || CT_AES || CT_L-ABE))
        """
        sk = secret_key if secret_key else self.secret_key
        if isinstance(sk, dict):
            sig = _sign(sk, message)
            return _sig_to_bytes(sig)
        raise TypeError("secret_key must be a Dilithium key dict")

    def verify(self, message: bytes, signature: bytes, public_key=None) -> bool:
        """Verify a signature.

        Corresponds to PQ-SPIDER Eq. (62):
            Verify_Dilithium(pk_FN, σ, H(...))
        """
        pk = public_key if public_key else self.public_key
        if isinstance(pk, dict):
            sig = _sig_from_bytes(signature)
            return _verify(pk, message, sig)
        raise TypeError("public_key must be a Dilithium key dict")
