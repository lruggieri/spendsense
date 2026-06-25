import base64
from infrastructure.crypto.encryption import (
    generate_api_key, hash_token, hkdf_derive_kek, wrap_key, unwrap_key, generate_dek,
)


def test_generate_api_key_shape():
    k = generate_api_key()
    assert k.startswith("ssk_")
    assert len(k) > 40


def test_hash_token_is_stable_and_hex():
    k = "ssk_abc"
    h = hash_token(k)
    assert h == hash_token(k)
    assert len(h) == 64  # sha256 hex


def test_kek_wrap_unwrap_roundtrip():
    raw = generate_api_key()
    salt = b"\x01" * 16
    dek = generate_dek()
    kek = hkdf_derive_kek(raw, salt)
    assert len(kek) == 32
    wrapped = wrap_key(dek, kek)
    assert unwrap_key(wrapped, hkdf_derive_kek(raw, salt)) == dek


def test_kek_differs_with_salt():
    raw = generate_api_key()
    assert hkdf_derive_kek(raw, b"a" * 16) != hkdf_derive_kek(raw, b"b" * 16)
