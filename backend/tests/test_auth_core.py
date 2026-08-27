from app.auth_core import is_authorized


def test_auth_off_when_no_key_configured():
    assert is_authorized(None, None) is True
    assert is_authorized("anything", None) is True


def test_auth_rejects_missing_header_when_key_configured():
    assert is_authorized(None, "secret") is False


def test_auth_rejects_wrong_key():
    assert is_authorized("wrong", "secret") is False


def test_auth_accepts_matching_key():
    assert is_authorized("secret", "secret") is True
