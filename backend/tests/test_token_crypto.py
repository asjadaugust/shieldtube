"""Tests for token encryption/decryption."""

import importlib
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import backend.services.token_crypto as tc


@pytest.fixture(autouse=True)
def reset_fernet():
    """Reset the module-level _fernet cache between tests."""
    tc._fernet = None
    yield
    tc._fernet = None


def test_round_trip_with_key():
    key = Fernet.generate_key().decode()
    with patch.object(tc.settings, "token_encryption_key", key):
        encrypted = tc.encrypt_token("my-secret-token")
        assert encrypted != "my-secret-token"
        assert tc.decrypt_token(encrypted) == "my-secret-token"


def test_passthrough_when_no_key():
    with patch.object(tc.settings, "token_encryption_key", ""):
        assert tc.encrypt_token("plaintext") == "plaintext"
        assert tc.decrypt_token("plaintext") == "plaintext"


def test_graceful_decrypt_of_plaintext():
    """Pre-encryption plaintext should be returned unchanged."""
    key = Fernet.generate_key().decode()
    with patch.object(tc.settings, "token_encryption_key", key):
        result = tc.decrypt_token("not-encrypted-at-all")
        assert result == "not-encrypted-at-all"


def test_fernet_key_validation():
    """A bad key should raise on first encrypt attempt."""
    with patch.object(tc.settings, "token_encryption_key", "not-a-valid-fernet-key"):
        with pytest.raises(Exception):
            tc.encrypt_token("test")
