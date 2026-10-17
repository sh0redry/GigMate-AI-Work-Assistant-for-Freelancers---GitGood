"""Configuration inspection never calls the vendor or reveals credentials."""

import json
import os

import pytest
from scripts.check_model_config import build_report, main

from gigmate.extraction.reviewed import configured_for_live


@pytest.fixture
def configured(monkeypatch):
    for name in list(os.environ):
        if name.startswith("GIGMATE_LLM_") or name.startswith("GIGMATE_MEDIA_"):
            monkeypatch.delenv(name)
    for name, value in {
        "GIGMATE_EXTRACTION_PROVIDER": "reviewed_llm",
        "GIGMATE_LLM_PROVIDER": "deepseek",
        "GIGMATE_LLM_MODEL": "deepseek-chat",
        "GIGMATE_LLM_API_KEY": "synthetic-not-a-real-key",
        "GIGMATE_LLM_LIVE": "1",
        "GIGMATE_LLM_ALLOW_LIVE_ORIGIN": "1",
        "GIGMATE_LLM_COST_INPUT_USD_PER_1K": "0.00014",
        "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K": "0.00028",
        "GIGMATE_LLM_COST_BUDGET_USD": "0.10",
        "GIGMATE_WORKSPACE_TIMEZONE": "Asia/Hong_Kong",
    }.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_valid_reviewed_configuration_is_ready_without_making_a_call(configured, capsys):
    assert configured_for_live() is True
    report = build_report()
    assert report["configuration_complete"] is True
    assert report["text"]["configured_for_live"] is True
    assert report["text"]["selected_provider"] == "reviewed_llm"
    assert report["text"]["refusal_reason"] is None
    assert "synthetic-not-a-real-key" not in json.dumps(report)
    configured.setattr("sys.argv", ["check_model_config.py", "--json"])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["configuration_complete"] is True


@pytest.mark.parametrize(
    "name,value",
    [
        ("GIGMATE_EXTRACTION_PROVIDER", "llm"),
        ("GIGMATE_EXTRACTION_PROVIDER", "deterministic"),
        ("GIGMATE_EXTRACTION_PROVIDER", "disabled"),
        ("GIGMATE_EXTRACTION_PROVIDER", "unknown"),
        ("GIGMATE_LLM_LIVE", "0"),
        ("GIGMATE_LLM_ALLOW_LIVE_ORIGIN", "0"),
        ("GIGMATE_LLM_API_KEY", ""),
        ("GIGMATE_LLM_COST_INPUT_USD_PER_1K", ""),
        ("GIGMATE_LLM_COST_OUTPUT_USD_PER_1K", ""),
        ("GIGMATE_LLM_MAX_OUTPUT_TOKENS", "0"),
        ("GIGMATE_WORKSPACE_TIMEZONE", ""),
        ("GIGMATE_WORKSPACE_TIMEZONE", "Invalid/Timezone"),
    ],
)
def test_incomplete_or_closed_configuration_is_not_ready(configured, name, value, capsys):
    configured.setenv(name, value)
    assert build_report()["configuration_complete"] is False
    configured.setattr("sys.argv", ["check_model_config.py"])
    assert main() == 1
    assert "synthetic-not-a-real-key" not in capsys.readouterr().out


def test_file_credential_is_supported_but_never_printed(configured, tmp_path, capsys):
    key = tmp_path / "synthetic-secret"
    key.write_text("synthetic-file-key", encoding="utf-8")
    configured.setenv("GIGMATE_LLM_API_KEY_FILE", str(key))
    configured.delenv("GIGMATE_LLM_API_KEY")
    assert build_report()["configuration_complete"] is True
    configured.setattr("sys.argv", ["check_model_config.py", "--json"])
    assert main() == 0
    assert "synthetic-file-key" not in capsys.readouterr().out


def test_unreadable_file_credential_is_not_ready(configured, tmp_path):
    configured.setenv("GIGMATE_LLM_API_KEY_FILE", str(tmp_path / "missing"))
    assert build_report()["configuration_complete"] is False
