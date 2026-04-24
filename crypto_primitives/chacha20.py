import os
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

class SecureChaCha20:
    def __init__(self, key=None):
        """Initialize ChaCha20-Poly1305 with a 32-byte (256-bit) key."""
        self.key = key if key else ChaCha20Poly1305.generate_key()
        self.chacha = ChaCha20Poly1305(self.key)

    def encrypt(self, data: bytes, associated_data: bytes = None) -> (bytes, bytes):
        """
        Encrypts data using ChaCha20-Poly1305.
        Returns: (ciphertext, nonce)
        """
        nonce = os.urandom(12) # 96-bit nonce
        ct_and_tag = self.chacha.encrypt(nonce, data, associated_data)
        return ct_and_tag, nonce

    def decrypt(self, ciphertext: bytes, nonce: bytes, associated_data: bytes = None) -> bytes:
        """
        Decrypts data.
        Raises InvalidTag if authentication fails.
        """
        return self.chacha.decrypt(nonce, ciphertext, associated_data)
