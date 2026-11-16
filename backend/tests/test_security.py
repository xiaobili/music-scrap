from __future__ import annotations

import pytest

from app.core.security import decrypt, encrypt, mask


def test_secret_roundtrip():
    token = encrypt("sk_live_123456789", key="test-key")
    assert token != "sk_live_123456789"
    assert decrypt(token, key="test-key") == "sk_live_123456789"


def test_mask_keeps_edges():
    assert mask("sk_123456789") == "sk_••••••6789"
    assert mask("abc") == "•••"


def test_decrypt_with_wrong_key_fails():
    token = encrypt("value", key="key-a")
    with pytest.raises(ValueError):
        decrypt(token, key="key-b")
