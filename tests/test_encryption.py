"""Tests for encryption infrastructure and EncryptionService."""

import base64
import os
from unittest.mock import MagicMock

import pytest

from application.services.encryption_service import EncryptionService
from infrastructure.crypto.encryption import (
    decrypt_field,
    encrypt_field,
    generate_dek,
    unwrap_key,
    wrap_key,
)
from infrastructure.persistence.sqlite.repositories.encryption_repository import (
    SQLiteEncryptionRepository,
)

# =========================================================================
# Crypto primitives
# =========================================================================


class TestEncryptDecrypt:
    """Tests for AES-256-GCM field encryption."""

    def _make_key_b64(self):
        return base64.b64encode(os.urandom(32)).decode("ascii")

    def test_roundtrip(self):
        key = self._make_key_b64()
        plaintext = "Hello, World!"
        encrypted = encrypt_field(plaintext, key)
        assert encrypted != plaintext
        assert decrypt_field(encrypted, key) == plaintext

    def test_unicode(self):
        key = self._make_key_b64()
        plaintext = "Caf\u00e9 \u2615 \u65e5\u672c\u8a9e"
        encrypted = encrypt_field(plaintext, key)
        assert decrypt_field(encrypted, key) == plaintext

    def test_empty_string(self):
        key = self._make_key_b64()
        encrypted = encrypt_field("", key)
        assert decrypt_field(encrypted, key) == ""

    def test_large_data(self):
        key = self._make_key_b64()
        plaintext = "x" * 100_000
        encrypted = encrypt_field(plaintext, key)
        assert decrypt_field(encrypted, key) == plaintext

    def test_wrong_key_fails(self):
        key1 = self._make_key_b64()
        key2 = self._make_key_b64()
        encrypted = encrypt_field("secret", key1)
        with pytest.raises(Exception):
            decrypt_field(encrypted, key2)

    def test_different_encryptions_are_unique(self):
        """Each encryption uses a random nonce so ciphertexts differ."""
        key = self._make_key_b64()
        e1 = encrypt_field("same", key)
        e2 = encrypt_field("same", key)
        assert e1 != e2

    def test_encrypted_is_base64(self):
        key = self._make_key_b64()
        encrypted = encrypt_field("test", key)
        # Should not raise
        base64.b64decode(encrypted)


class TestKeyWrap:
    """Tests for AES Key Wrap / Unwrap (RFC 3394)."""

    def test_roundtrip(self):
        dek = os.urandom(32)
        kek = os.urandom(32)
        wrapped = wrap_key(dek, kek)
        assert wrapped != dek
        assert unwrap_key(wrapped, kek) == dek

    def test_wrong_kek_fails(self):
        dek = os.urandom(32)
        kek1 = os.urandom(32)
        kek2 = os.urandom(32)
        wrapped = wrap_key(dek, kek1)
        with pytest.raises(Exception):
            unwrap_key(wrapped, kek2)


class TestGenerateDEK:
    """Tests for DEK generation."""

    def test_length(self):
        dek = generate_dek()
        assert len(dek) == 32

    def test_randomness(self):
        dek1 = generate_dek()
        dek2 = generate_dek()
        assert dek1 != dek2


# =========================================================================
# Encryption Repository
# =========================================================================


class TestSQLiteEncryptionRepository:
    """Tests for the SQLite encryption repository."""

    @pytest.fixture
    def repo(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        return SQLiteEncryptionRepository(db_path)

    def test_store_and_get_wrapped_dek(self, repo):
        wrapped = os.urandom(40)
        repo.store_wrapped_dek("user1", "cred1", wrapped, "salt1")
        result = repo.get_wrapped_dek("user1", "cred1")
        assert result == wrapped

    def test_get_wrapped_dek_not_found(self, repo):
        assert repo.get_wrapped_dek("user1", "nonexistent") is None

    def test_get_wrapped_deks_for_user(self, repo):
        repo.store_wrapped_dek("user1", "cred1", b"wrapped1", "salt1")
        repo.store_wrapped_dek("user1", "cred2", b"wrapped2", "salt2")
        repo.store_wrapped_dek("user2", "cred3", b"wrapped3", "salt3")

        user1_deks = repo.get_wrapped_deks_for_user("user1")
        assert len(user1_deks) == 2

    def test_delete_wrapped_dek(self, repo):
        repo.store_wrapped_dek("user1", "cred1", b"wrapped", "salt1")
        repo.delete_wrapped_dek("user1", "cred1")
        assert repo.get_wrapped_dek("user1", "cred1") is None

    def test_get_prf_salt(self, repo):
        repo.store_wrapped_dek("user1", "cred1", b"wrapped", "my_salt")
        assert repo.get_prf_salt("user1", "cred1") == "my_salt"

    def test_get_prf_salt_not_found(self, repo):
        assert repo.get_prf_salt("user1", "nonexistent") is None

    def test_store_and_get_credential(self, repo):
        pub_key = os.urandom(64)
        repo.store_credential("user1", "cred1", pub_key, 0, "My Device")
        cred = repo.get_credential("cred1")
        assert cred is not None
        assert cred["user_id"] == "user1"
        assert cred["credential_id"] == "cred1"
        assert bytes(cred["public_key"]) == pub_key
        assert cred["sign_count"] == 0
        assert cred["device_name"] == "My Device"

    def test_get_credential_not_found(self, repo):
        assert repo.get_credential("nonexistent") is None

    def test_get_credentials_for_user(self, repo):
        repo.store_credential("user1", "cred1", b"key1", 0)
        repo.store_credential("user1", "cred2", b"key2", 0)
        repo.store_credential("user2", "cred3", b"key3", 0)

        creds = repo.get_credentials_for_user("user1")
        assert len(creds) == 2

    def test_update_sign_count(self, repo):
        repo.store_credential("user1", "cred1", b"key", 0)
        repo.update_sign_count("cred1", 5)
        cred = repo.get_credential("cred1")
        assert cred["sign_count"] == 5

    def test_delete_credential(self, repo):
        repo.store_credential("user1", "cred1", b"key", 0)
        repo.delete_credential("cred1")
        assert repo.get_credential("cred1") is None


# =========================================================================
# Encryption Service
# =========================================================================


class TestEncryptionService:
    """Tests for the EncryptionService."""

    @pytest.fixture
    def service(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        repo = SQLiteEncryptionRepository(db_path)
        return EncryptionService(repo)

    def _make_kek_b64(self):
        return base64.b64encode(os.urandom(32)).decode("ascii")

    def test_setup_and_unwrap(self, service):
        kek = self._make_kek_b64()
        dek_b64 = service.setup_encryption("user1", "cred1", kek, "salt1")
        assert dek_b64  # non-empty

        # Unwrap should return the same DEK
        unwrapped = service.unwrap_dek("user1", "cred1", kek)
        assert unwrapped == dek_b64

    def test_unwrap_wrong_kek_fails(self, service):
        kek1 = self._make_kek_b64()
        kek2 = self._make_kek_b64()
        service.setup_encryption("user1", "cred1", kek1, "salt1")

        with pytest.raises(Exception):
            service.unwrap_dek("user1", "cred1", kek2)

    def test_unwrap_no_dek_raises(self, service):
        kek = self._make_kek_b64()
        with pytest.raises(ValueError, match="No wrapped DEK found"):
            service.unwrap_dek("user1", "nonexistent", kek)

    def test_add_passkey_wrapper(self, service):
        kek1 = self._make_kek_b64()
        kek2 = self._make_kek_b64()

        # Setup with first passkey
        dek_b64 = service.setup_encryption("user1", "cred1", kek1, "salt1")

        # Add second passkey wrapper
        service.add_passkey_wrapper("user1", "cred2", dek_b64, kek2, "salt2")

        # Both KEKs should unwrap to the same DEK
        unwrapped1 = service.unwrap_dek("user1", "cred1", kek1)
        unwrapped2 = service.unwrap_dek("user1", "cred2", kek2)
        assert unwrapped1 == unwrapped2 == dek_b64

    def test_has_encryption(self, service):
        assert not service.has_encryption("user1")
        kek = self._make_kek_b64()
        service.setup_encryption("user1", "cred1", kek, "salt1")
        assert service.has_encryption("user1")

    def test_has_encryption_different_users(self, service):
        kek = self._make_kek_b64()
        service.setup_encryption("user1", "cred1", kek, "salt1")
        assert service.has_encryption("user1")
        assert not service.has_encryption("user2")


# =========================================================================
# Encryption Service — Migration methods
# =========================================================================


class TestEncryptionServiceMigration:
    """Tests for EncryptionService.migrate_to_encrypted / migrate_to_plaintext."""

    @pytest.fixture
    def mock_tx_ds(self):
        return MagicMock()

    @pytest.fixture
    def mock_session_ds(self):
        return MagicMock()

    @pytest.fixture
    def mock_encryption_repo(self):
        return MagicMock()

    def test_migrate_to_encrypted_delegates_to_transaction_ds(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_encrypted.return_value = 5
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
        )

        count = service.migrate_to_encrypted("tok")
        assert count == 5
        mock_tx_ds.migrate_to_encrypted.assert_called_once()

    def test_migrate_to_encrypted_encrypts_google_token(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_encrypted.return_value = 0
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
        )

        service.migrate_to_encrypted("session_tok")
        mock_session_ds.encrypt_google_token.assert_called_once_with("session_tok", "key123")

    def test_migrate_to_encrypted_skips_session_without_token(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_encrypted.return_value = 0
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
        )

        service.migrate_to_encrypted(None)
        mock_session_ds.encrypt_google_token.assert_not_called()

    def test_migrate_to_encrypted_raises_without_tx_datasource(
        self,
        mock_encryption_repo,
    ):
        service = EncryptionService(mock_encryption_repo)
        with pytest.raises(RuntimeError, match="Transaction datasource not configured"):
            service.migrate_to_encrypted("tok")

    def test_migrate_to_plaintext_delegates_to_transaction_ds(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_plaintext.return_value = 7
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
        )

        count = service.migrate_to_plaintext("tok")
        assert count == 7
        mock_tx_ds.migrate_to_plaintext.assert_called_once()

    def test_migrate_to_plaintext_decrypts_google_token(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_plaintext.return_value = 0
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
        )

        service.migrate_to_plaintext("session_tok")
        mock_session_ds.decrypt_google_token.assert_called_once_with("session_tok", "key123")

    def test_migrate_to_plaintext_raises_without_tx_datasource(
        self,
        mock_encryption_repo,
    ):
        service = EncryptionService(mock_encryption_repo)
        with pytest.raises(RuntimeError, match="Transaction datasource not configured"):
            service.migrate_to_plaintext("tok")

    # --- Embedding cache invalidation ---

    def test_migrate_to_encrypted_invalidates_embeddings(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_encrypted.return_value = 5
        mock_embedding_ds = MagicMock()
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
            embedding_datasource=mock_embedding_ds,
        )

        service.migrate_to_encrypted("tok")
        mock_embedding_ds.invalidate_all.assert_called_once()

    def test_migrate_to_encrypted_skips_invalidation_when_zero_migrated(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_encrypted.return_value = 0
        mock_embedding_ds = MagicMock()
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
            embedding_datasource=mock_embedding_ds,
        )

        service.migrate_to_encrypted("tok")
        mock_embedding_ds.invalidate_all.assert_not_called()

    def test_migrate_to_plaintext_invalidates_embeddings(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_plaintext.return_value = 7
        mock_embedding_ds = MagicMock()
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
            embedding_datasource=mock_embedding_ds,
        )

        service.migrate_to_plaintext("tok")
        mock_embedding_ds.invalidate_all.assert_called_once()

    def test_migrate_to_plaintext_skips_invalidation_when_zero_migrated(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        mock_tx_ds.migrate_to_plaintext.return_value = 0
        mock_embedding_ds = MagicMock()
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
            embedding_datasource=mock_embedding_ds,
        )

        service.migrate_to_plaintext("tok")
        mock_embedding_ds.invalidate_all.assert_not_called()

    def test_migrate_without_embedding_datasource_does_not_crash(
        self,
        mock_encryption_repo,
        mock_tx_ds,
        mock_session_ds,
    ):
        """Backward-compatible: no embedding_datasource passed."""
        mock_tx_ds.migrate_to_encrypted.return_value = 10
        mock_tx_ds.migrate_to_plaintext.return_value = 10
        service = EncryptionService(
            mock_encryption_repo,
            transaction_datasource=mock_tx_ds,
            session_datasource=mock_session_ds,
            encryption_key="key123",
        )

        # Should not raise
        service.migrate_to_encrypted("tok")
        service.migrate_to_plaintext("tok")
