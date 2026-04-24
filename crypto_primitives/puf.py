"""
SRAM PUF Simulator with a Real Code-Offset Fuzzy Extractor
===========================================================
Implements the "code-offset" construction (Dodis-Reyzin-Smith 2004,
Boyen 2004) over a BCH error-correcting code.  This is the standard
fuzzy extractor used in hardware PUF literature — it is a REAL
cryptographic primitive, not a simulator.

Honest scope statement
----------------------
  * The PUF itself is still a SIMULATOR.  We don't have hardware
    SRAM; we model the underlying physical randomness as a single
    static secret plus per-query Bernoulli noise.  The simulator
    is deterministic given its `_internal_secret`, so timing is
    reproducible.

  * The FUZZY EXTRACTOR is real.  It uses BCH(n=1023, t=32) as the
    underlying error-correcting code (3% BER tolerance per code-
    word).  Helper data is the XOR of the noisy response and a BCH
    codeword drawn from the target secret's codeword — this does
    NOT reveal the secret (the codeword itself is random and the
    XOR is a one-time-pad style mask).

  * Unlike the original `FuzzyExtractor.generate(noisy) -> (secret,
    helper=secret)` placeholder, helper data in this implementation
    is strictly non-secret: giving it to an attacker reveals only
    the random codeword used, not the stable secret.

  * We also lower the simulated PUF BER from the old 10% to 2% so
    the BCH(t=32) code can reliably correct it.  Real SRAM PUFs
    typically exhibit 3-15% BER depending on temperature and
    voltage; the simulator is tunable via the `ber` parameter of
    `SRAM_PUF`.

Construction (Code-Offset)
--------------------------
  Setup:
    R_noisy_0      <- PUF.evaluate(challenge)      # enrollment
    W              <- random BCH codeword of length n
    helper_data    = R_noisy_0 XOR W                (padded to n bits)
    stable_secret  = SHA-256(R_noisy_0)

  Reproduce:
    R_noisy_1      <- PUF.evaluate(challenge)      # later query
    W'             = R_noisy_1 XOR helper_data
                   = W + noise                     (≤ t bit-flips)
    W_corrected    = BCH_decode(W')                # correct up to t errors
    R_enrol        = W_corrected XOR helper_data   # = R_noisy_0
    stable_secret' = SHA-256(R_enrol)

If BER exceeds `t / n`, decoding will fail silently (returning a
different or invalid secret); the caller should verify with a
keyed hash or challenge-response before relying on the output.

References
----------
  Y. Dodis, L. Reyzin, A. Smith, "Fuzzy Extractors: How to Generate
  Strong Keys from Biometrics and Other Noisy Data," Eurocrypt 2004.
  X. Boyen, "Reusable Cryptographic Fuzzy Extractors," CCS 2004.
"""

from __future__ import annotations

import hashlib
import os
from typing import Tuple

try:
    import bchlib
    _BCH_AVAILABLE = True
except ImportError:
    _BCH_AVAILABLE = False


# ────────────────── BCH parameters ──────────────────────────────────
# m=10 gives n = 2^10 - 1 = 1023 bit codewords.
# t=32 corrects up to 32 bit errors, i.e. about 3% BER tolerance.
# data_bits = 1023 - ecc_bits(315) = 708 bits available for payload.
BCH_M = 10
BCH_T = 32
CODEWORD_BITS = (1 << BCH_M) - 1                    # 1023
DATA_BYTES    = 32                                  # 256 data bits (easily fits)
ECC_BYTES_CACHE: int = None                         # populated on first use


def _get_bch():
    """Lazily create a BCH instance, caching the ECC size."""
    if not _BCH_AVAILABLE:
        raise RuntimeError(
            "bchlib not available — pip install bchlib for a real "
            "fuzzy extractor.  Falling back to the legacy no-op is "
            "not implemented here.")
    global ECC_BYTES_CACHE
    bch = bchlib.BCH(t=BCH_T, m=BCH_M)
    ECC_BYTES_CACHE = bch.ecc_bytes
    return bch


# ────────────────── PUF simulator ───────────────────────────────────

class SRAM_PUF:
    """
    Hardware PUF simulator.

    Internally holds a single 32-byte `_internal_secret` acting as
    the "fixed physical randomness" of a real SRAM PUF.  Each call
    to evaluate() returns `SHA-256(challenge || secret)` with a
    small per-bit Bernoulli error layered on top to simulate the
    noisy physical read.
    """

    def __init__(self, size: int = 32, ber: float = 0.02):
        """
        Parameters
        ----------
        size : int
            Response length in bytes.
        ber : float
            Simulated bit-error rate (0 ≤ ber < 0.5).  Default 2%
            matches the BCH(t=32, n=1023) decoder's capacity (~3.1%)
            with margin.
        """
        if not 0 <= ber < 0.5:
            raise ValueError("ber must lie in [0, 0.5)")
        self.size = size
        self.ber = ber
        self._internal_secret = os.urandom(size)

    def evaluate(self, challenge: bytes) -> bytes:
        """
        Produce a noisy response  SHA-256(C || S)  XOR  bit_noise.

        Each bit is independently flipped with probability `self.ber`.
        """
        base = hashlib.sha256(challenge + self._internal_secret).digest()
        base = (base * ((self.size + 31) // 32))[:self.size]
        out = bytearray(base)
        # Per-bit Bernoulli noise
        for byte_idx in range(self.size):
            for bit_idx in range(8):
                # os.urandom gives us uniform bytes -> compare against threshold
                r_byte = os.urandom(1)[0]
                if r_byte < int(self.ber * 256):
                    out[byte_idx] ^= (1 << bit_idx)
        return bytes(out)


# ────────────────── BCH code-offset helpers ─────────────────────────

def _bytes_to_bits(buf: bytes, n_bits: int) -> bytearray:
    """Pack bytes into a length-n_bits bitarray (LSB first)."""
    bits = bytearray(n_bits)
    for i in range(min(len(buf) * 8, n_bits)):
        if (buf[i >> 3] >> (i & 7)) & 1:
            bits[i] = 1
    return bits


def _bits_to_bytes(bits: bytearray) -> bytes:
    """Inverse of _bytes_to_bits."""
    n_bytes = (len(bits) + 7) // 8
    out = bytearray(n_bytes)
    for i, b in enumerate(bits):
        if b:
            out[i >> 3] |= (1 << (i & 7))
    return bytes(out)


def _xor(a: bytes, b: bytes) -> bytes:
    n = min(len(a), len(b))
    return bytes(x ^ y for x, y in zip(a[:n], b[:n]))


# ────────────────── Fuzzy extractor ─────────────────────────────────

class FuzzyExtractor:
    """
    Code-offset fuzzy extractor over BCH(n=1023, t=32).

    Both methods are `staticmethod`s to preserve the original API
    used by `crypto_primitives/test.py`.
    """

    @staticmethod
    def generate(noisy_response: bytes) -> Tuple[bytes, bytes]:
        """
        Enrollment.  From a noisy PUF reading:
          * Derive a stable secret as  SHA-256(noisy_response).
          * Pick a random payload W of length (bch.n - bch.ecc_bits).
          * Encode W into codeword C = W || ECC(W).
          * Helper data h = noisy_response XOR C (zero-padded to bch.n bits).
        Returns (stable_secret, helper_data).

        Helper data is NOT a secret: it is a one-time-pad-style
        masking of a RANDOM codeword by the noisy response.

        The response is zero-extended (NOT repeated) to codeword
        length; bit-errors in the zero-padded region are therefore
        none, so total errors for BCH decoding remain bounded by
        the response's own bit-error count.
        """
        bch = _get_bch()
        codeword_bytes = (CODEWORD_BITS + 7) // 8

        # Zero-extend the noisy response to codeword_bytes.
        # Bit errors in the extension region are zero by construction.
        resp_padded = noisy_response + b'\x00' * max(
            0, codeword_bytes - len(noisy_response))
        resp_padded = resp_padded[:codeword_bytes]

        # Pick a random payload and ECC-encode it.
        data_bytes = (CODEWORD_BITS - bch.ecc_bits) // 8
        w_data = os.urandom(data_bytes)
        w_ecc  = bch.encode(w_data)
        codeword = w_data + w_ecc
        codeword = codeword + b'\x00' * (codeword_bytes - len(codeword))

        # Helper: XOR of padded noisy response with codeword.
        helper = _xor(resp_padded, codeword)

        # Stable secret derived from the noisy response seen at enrol.
        stable_secret = hashlib.sha256(noisy_response).digest()
        return stable_secret, helper

    @staticmethod
    def reproduce(noisy_response_new: bytes, helper_data: bytes) -> bytes:
        """
        Reproduction.  Using helper data h from enrollment and a
        fresh noisy reading:
          * (h XOR new_reading) gives  C + noise'
          * BCH decode recovers C, from which W is the low bytes.
          * Now  orig_reading = h XOR C  (the exact enrollment reading).
          * stable_secret = SHA-256(orig_reading).

        If the Hamming distance between enrollment and reproduction
        readings exceeds the BCH decoder's capacity (t = 32 bit
        errors), the returned secret will silently differ from the
        enrolled secret.  Downstream code MUST verify the secret
        before trusting it (e.g. via a challenge-response check).
        """
        bch = _get_bch()
        codeword_bytes = (CODEWORD_BITS + 7) // 8

        resp_padded = noisy_response_new + b'\x00' * max(
            0, codeword_bytes - len(noisy_response_new))
        resp_padded = resp_padded[:codeword_bytes]

        # Recover the noisy codeword.
        noisy_codeword = _xor(resp_padded, helper_data)

        data_bytes = (CODEWORD_BITS - bch.ecc_bits) // 8
        data_buf = bytearray(noisy_codeword[:data_bytes])
        ecc_buf  = bytearray(noisy_codeword[data_bytes:data_bytes + bch.ecc_bytes])

        nerr = bch.decode(bytes(data_buf), bytes(ecc_buf))
        if nerr < 0:
            return hashlib.sha256(b"FUZZY_DECODE_FAIL" +
                                  helper_data).digest()
        bch.correct(data_buf, ecc_buf)

        recovered_cw = (bytes(data_buf) + bytes(ecc_buf) +
                        b'\x00' * (codeword_bytes - data_bytes -
                                    bch.ecc_bytes))

        orig_response_padded = _xor(helper_data, recovered_cw)
        orig_trim = orig_response_padded[:len(noisy_response_new)]
        return hashlib.sha256(orig_trim).digest()
