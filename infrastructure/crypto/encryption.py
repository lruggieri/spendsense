"""
Field-level encryption utilities using AES-256-GCM.

Provides encrypt/decrypt for individual fields and AES Key Wrap (RFC 3394)
for envelope encryption of Data Encryption Keys (DEKs).
"""

import base64
import hashlib
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap, aes_key_wrap
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

API_KEY_PREFIX = "ssk_"
_KEK_INFO = b"spendsense-mcp-dek-wrap"


def generate_dek() -> bytes:
    """Generate a random 256-bit Data Encryption Key."""
    return os.urandom(32)


def encrypt_field(plaintext: str, key_b64: str) -> str:
    """
    Encrypt a string field using AES-256-GCM.

    Args:
        plaintext: The string to encrypt.
        key_b64: Base64-encoded 256-bit key.

    Returns:
        Base64-encoded string of nonce (12 bytes) + ciphertext.
    """
    key = base64.b64decode(key_b64)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_field(encrypted: str, key_b64: str) -> str:
    """
    Decrypt an AES-256-GCM encrypted field.

    Args:
        encrypted: Base64-encoded string of nonce + ciphertext.
        key_b64: Base64-encoded 256-bit key.

    Returns:
        Decrypted plaintext string.
    """
    key = base64.b64decode(key_b64)
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext_bytes.decode("utf-8")


def wrap_key(dek: bytes, kek: bytes) -> bytes:
    """
    Wrap a DEK using AES Key Wrap (RFC 3394).

    Args:
        dek: 256-bit Data Encryption Key to wrap.
        kek: 256-bit Key Encryption Key.

    Returns:
        Wrapped key bytes.
    """
    return aes_key_wrap(kek, dek)


def unwrap_key(wrapped_dek: bytes, kek: bytes) -> bytes:
    """
    Unwrap a DEK using AES Key Unwrap (RFC 3394).

    Args:
        wrapped_dek: Wrapped key bytes.
        kek: 256-bit Key Encryption Key.

    Returns:
        Unwrapped 256-bit DEK.
    """
    return aes_key_unwrap(kek, wrapped_dek)


def generate_api_key() -> str:
    """Generate a new MCP API key string: 'ssk_' + base64url(32 random bytes)."""
    raw = secrets.token_bytes(32)
    return API_KEY_PREFIX + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def hash_token(raw_key: str) -> str:
    """SHA-256 hex digest of the full key string, for auth lookup."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def hkdf_derive_kek(raw_key: str, salt: bytes) -> bytes:
    """Derive a 256-bit KEK from the raw key via HKDF-SHA256 (domain-separated from auth hash)."""
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=_KEK_INFO)
    return hkdf.derive(raw_key.encode("utf-8"))
