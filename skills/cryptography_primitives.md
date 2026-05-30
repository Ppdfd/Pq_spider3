---
name: cryptography-primitives
description: >-
  Use when the user asks to modify, debug, or integrate the post-quantum cryptographic primitives (Dilithium, Kyber, or CP-ABE).
  Includes context for how PQ-SPIDER handles secure communication and delegation.
---

# Instructions

1. **Locate the Cryptography Logic**: All base cryptographic functions are in the `crypto_primitives/` directory.
   - Phases 1, 2, and 6 heavily rely on these modules for setup, encryption, and decryption.
2. **Key Generation and Handling**: Ensure that Dilithium (for signatures) and Kyber (for key encapsulation) are used correctly. CP-ABE is used for access control.
3. **Execution Size and Latency Limits**: When adjusting crypto logic, remember that ciphertext sizes and signature times must align with the paper's benchmarks.

## Constraints
- **Never** replace the post-quantum algorithms with classical ones (like RSA or ECC) unless explicitly requested for a baseline comparison.
- **Never** hardcode private keys into the source files; use the key generation functions provided in the `crypto_primitives` module.

## References
- See `crypto_primitives/` for implementation details.
- Review [PQ_SPIDER2_readable.txt](../papers/PQ_SPIDER2_readable.txt) Section IV for the mathematical definitions of the security models.
