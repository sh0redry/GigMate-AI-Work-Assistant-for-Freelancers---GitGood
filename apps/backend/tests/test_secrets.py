"""Model credentials can be supplied as a file, and failures are loud.

Issue #29 makes the maintainer responsible for choosing the vendor and
configuring its credential privately. A file (``<NAME>_FILE``) is the shape
that survives a real server — it does not appear in ``docker inspect``, in a
process listing or in shell history — so the loader must prefer it, and a file
that is named but unreadable must fail instead of degrading to "not
configured", which would look identical to a deployment that never set one up.
"""

from __future__ import annotations

import pytest

from gigmate.secrets import SecretUnreadable, configured, secret


def test_value_variable_is_used_when_no_file_is_named(monkeypatch, tmp_path):
    monkeypatch.delenv("GIGMATE_LLM_API_KEY_FILE", raising=False)
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-from-env")
    assert secret("GIGMATE_LLM_API_KEY") == "sk-from-env"
    assert configured("GIGMATE_LLM_API_KEY") is True


def test_file_wins_over_the_value_variable(monkeypatch, tmp_path):
    path = tmp_path / "deepseek.key"
    path.write_text("sk-from-file\n", encoding="utf-8")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-from-env")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY_FILE", str(path))
    # The file is the deliberate choice, so it beats a stray environment value.
    assert secret("GIGMATE_LLM_API_KEY") == "sk-from-file"


def test_missing_file_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGMATE_LLM_API_KEY_FILE", str(tmp_path / "absent"))
    with pytest.raises(SecretUnreadable):
        secret("GIGMATE_LLM_API_KEY")
    # Reported as not configured, but never mistaken for a working key.
    assert configured("GIGMATE_LLM_API_KEY") is False


def test_unreadable_file_fails_loudly(monkeypatch, tmp_path):
    path = tmp_path / "locked"
    path.write_bytes(b"\xff\xfe\x00binary")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY_FILE", str(path))
    with pytest.raises(SecretUnreadable):
        secret("GIGMATE_LLM_API_KEY")


def test_nothing_configured_is_empty_not_error(monkeypatch):
    monkeypatch.delenv("GIGMATE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GIGMATE_LLM_API_KEY_FILE", raising=False)
    assert secret("GIGMATE_LLM_API_KEY") == ""
    assert configured("GIGMATE_LLM_API_KEY") is False
