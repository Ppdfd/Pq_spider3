import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class SecureAESGCM:
    def __init__(self, key=None):
        """Initialize AES-GCM with a 256-bit key."""
        # 256 bits = 32 bytes
        self.key = key if key else AESGCM.generate_key(bit_length=256)
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, data: bytes, associated_data: bytes = None) -> (bytes, bytes):
        """
        Encrypts data using AES-GCM.
        Returns: (ciphertext, iv)
        """
        iv = os.urandom(12) # 96-bit IV
        # encrypt returns ciphertext + tag appended
        ct_and_tag = self.aesgcm.encrypt(iv, data, associated_data)
        return ct_and_tag, iv

    def decrypt(self, ciphertext: bytes, iv: bytes, associated_data: bytes = None) -> bytes:
        """
        Decrypts data.
        Raises InvalidTag if authentication fails.
        """
        return self.aesgcm.decrypt(iv, ciphertext, associated_data)
