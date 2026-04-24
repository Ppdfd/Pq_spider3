"""
PQ-SPIDER Cryptographic Primitives — Test Suite
================================================
Tests all cryptographic primitives used in the PQ-SPIDER architecture:
  - AES-GCM (symmetric AEAD)
  - ChaCha20-Poly1305 (lightweight AEAD)
  - CRYSTALS-Kyber512 (post-quantum KEM)
  - CRYSTALS-Dilithium2 (post-quantum signatures)
  - SRAM-PUF + Fuzzy Extractor (hardware authentication)
  - Lattice-based CP-ABE (fine-grained access control)
"""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aes_gcm import SecureAESGCM
from chacha20 import SecureChaCha20
from kyber import SecureKyber
from dilithium import SecureDilithium
from cp_abe import LatticeCPABE, full_encrypt, full_decrypt
from puf import SRAM_PUF, FuzzyExtractor


def test_aes_gcm():
    print("Testing AES-GCM...")
    plain = b"Secret IIoT MQTT Payload"
    aes = SecureAESGCM()
    ct, iv = aes.encrypt(plain, b"aad")
    pt = aes.decrypt(ct, iv, b"aad")
    assert pt == plain, "AES-GCM decryption failed!"
    print("  -> AES-GCM Passed.")


def test_chacha():
    print("Testing ChaCha20-Poly1305...")
    plain = b"Industrial sensor data 1234.56"
    chacha = SecureChaCha20()
    ct, nonce = chacha.encrypt(plain, b"header")
    pt = chacha.decrypt(ct, nonce, b"header")
    assert pt == plain, "ChaCha decryption failed!"
    print("  -> ChaCha20 Passed.")


def test_kyber():
    print("Testing CRYSTALS-Kyber512 KEM...")
    kyber = SecureKyber()

    t0 = time.time()
    pk, sk = kyber.keygen()
    t_kg = time.time() - t0

    t0 = time.time()
    ct, ss_sender = kyber.encap(pk)
    t_enc = time.time() - t0

    t0 = time.time()
    ss_receiver = kyber.decap(ct, sk)
    t_dec = time.time() - t0

    assert ss_sender == ss_receiver, "Kyber shared secrets do not match!"
    assert len(pk) == 800, f"pk size wrong: {len(pk)}"
    assert len(sk) == 1632, f"sk size wrong: {len(sk)}"
    assert len(ct) == 768, f"ct size wrong: {len(ct)}"

    # Multiple trials
    for _ in range(3):
        pk2, sk2 = kyber.keygen()
        ct2, ss2a = kyber.encap(pk2)
        ss2b = kyber.decap(ct2, sk2)
        assert ss2a == ss2b, "Kyber multi-trial failed!"

    print(f"  -> Kyber512 Passed.  (KeyGen {t_kg*1000:.1f}ms, "
          f"Encap {t_enc*1000:.1f}ms, Decap {t_dec*1000:.1f}ms)")
    print(f"     pk={len(pk)}B, sk={len(sk)}B, ct={len(ct)}B, ss=32B")


def test_dilithium():
    print("Testing CRYSTALS-Dilithium2 Signatures...")
    dil = SecureDilithium()

    t0 = time.time()
    pk, sk = dil.keygen()
    t_kg = time.time() - t0

    msg = b"IIoT Batch Approval BID-0042"

    t0 = time.time()
    sig = dil.sign(msg, sk)
    t_sign = time.time() - t0

    t0 = time.time()
    valid = dil.verify(msg, sig, pk)
    t_ver = time.time() - t0

    assert valid, "Dilithium signature verification failed!"

    # Forgery detection
    assert not dil.verify(b"Tampered message", sig, pk), \
        "Dilithium accepted forged message!"

    # Multiple trials
    for _ in range(3):
        pk2, sk2 = dil.keygen()
        m = os.urandom(64)
        s = dil.sign(m, sk2)
        assert dil.verify(m, s, pk2), "Dilithium multi-trial verify failed!"
        assert not dil.verify(m + b"x", s, pk2), "Dilithium accepted forgery!"

    print(f"  -> Dilithium2 Passed.  (KeyGen {t_kg*1000:.1f}ms, "
          f"Sign {t_sign*1000:.1f}ms, Verify {t_ver*1000:.1f}ms)")
    print(f"     sig={len(sig)}B")


def test_puf():
    print("Testing SRAM PUF & Fuzzy Extractor...")
    puf = SRAM_PUF()
    challenge = b"CHALLENGE_001"
    resp1 = puf.evaluate(challenge)
    resp2 = puf.evaluate(challenge)
    stable1, helper = FuzzyExtractor.generate(resp1)
    stable2 = FuzzyExtractor.reproduce(resp2, helper)
    assert stable1 == stable2, \
        "Fuzzy Extractor failed to stabilize noisy PUF responses!"
    print("  -> PUF Passed.")


def test_cp_abe():
    print("Testing Split-Phase Lattice CP-ABE...")
    cpabe = LatticeCPABE(n=32, q=3329)
    cpabe.setup()

    symmetric_key = os.urandom(32)

    # ── AND policy: all attributes required ──
    user_attrs = ["Engineer", "ZoneA"]
    sk_u = cpabe.keygen({}, user_attrs)

    t0 = time.time()
    policy = {"type": "AND", "attributes": ["Engineer", "ZoneA"]}
    ct = full_encrypt(cpabe, symmetric_key, policy)
    t_enc = time.time() - t0

    t0 = time.time()
    recovered = full_decrypt(cpabe, ct, sk_u)
    t_dec = time.time() - t0

    assert recovered == symmetric_key, \
        "CP-ABE AND decryption failed (key mismatch)!"

    # ── AND policy: user missing attribute → must fail ──
    policy_strict = {"type": "AND",
                     "attributes": ["Engineer", "Safety", "ZoneA"]}
    ct2 = full_encrypt(cpabe, symmetric_key, policy_strict)
    assert full_decrypt(cpabe, ct2, sk_u) is None, \
        "CP-ABE AND should reject when attributes are missing!"

    # ── OR policy: any one attribute suffices ──
    cpabe.keygen({}, ["Admin"])  # register Admin
    policy_or = {"type": "OR", "attributes": ["Admin", "Engineer"]}
    ct3 = full_encrypt(cpabe, symmetric_key, policy_or)
    recovered_or = full_decrypt(cpabe, ct3, sk_u)
    assert recovered_or == symmetric_key, \
        "CP-ABE OR decryption failed!"

    # ── 3-attribute AND ──
    sk_full = cpabe.keygen({}, ["Engineer", "Safety", "ZoneA"])
    ct4 = full_encrypt(cpabe, symmetric_key, policy_strict)
    assert full_decrypt(cpabe, ct4, sk_full) == symmetric_key, \
        "CP-ABE 3-attr AND failed!"

    # ── Multiple random trials ──
    for trial in range(5):
        key = os.urandom(32)
        ct_r = full_encrypt(cpabe, key, policy)
        rec = full_decrypt(cpabe, ct_r, sk_u)
        assert rec == key, f"CP-ABE random trial {trial} failed!"

    print(f"  -> CP-ABE Passed (AND, OR, rejection, multi-trial)."
          f"  (Enc {t_enc*1000:.1f}ms, Dec {t_dec*1000:.1f}ms)")


if __name__ == "__main__":
    try:
        test_aes_gcm()
        test_chacha()
        test_kyber()
        test_dilithium()
        test_puf()
        test_cp_abe()
        print("\n" + "=" * 60)
        print("All cryptographic primitive tests PASSED.")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nTest FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
