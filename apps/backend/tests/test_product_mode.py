"""The delivered product never accepts fixture ingestion."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from scripts import start_product, waha_team
from sqlalchemy import func, select

from gigmate import api
from gigmate.db import Inbox, Job
from gigmate.messaging import replay_event


def test_product_blocks_both_replay_paths_and_reports_its_actual_mode(signed_in, monkeypatch):
    client, factory, _, headers = signed_in
    monkeypatch.setattr(api, "APP_MODE", "product")
    assert client.get("/health").json()["mode"] == "product"
    login = client.post(
        "/api/v1/auth/login", json={"username": "merchant", "password": "demo-only-change-me"}
    )
    assert login.json()["data"]["mode"] == "product"
    headers = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}
    for route, body in [
        ("/replay", {"scenario": "available"}),
        ("/replay/events", replay_event("available")),
    ]:
        result = client.post(
            "/api/v1" + route,
            json=body,
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert result.status_code == 404
    assert client.get("/api/v1/connection-status").status_code == 404
    assert client.get("/api/v1/connectors").status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Inbox)) == 0
        assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_default_runtime_is_product_not_fixture_mode():
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        if name in os.environ
    }
    environment["PYTHONPATH"] = str(Path(api.__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-c", "from gigmate.config import APP_MODE; print(APP_MODE)"],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "product"


def test_product_overlay_keeps_model_key_out_of_compose_and_process_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(
        start_product, "private_run", lambda command, **kwargs: calls.append((command, kwargs))
    )
    overlay = start_product.model_overlay(
        {
            "GIGMATE_LLM_API_KEY": "synthetic-private-key",
            "GIGMATE_EXTRACTION_PROVIDER": "reviewed_llm",
            "GIGMATE_LLM_LIVE": "1",
            "UNKNOWN_SETTING": "must-not-be-forwarded",
        }
    )
    assert "synthetic-private-key" not in json.dumps(overlay)
    assert "UNKNOWN_SETTING" not in json.dumps(overlay)
    assert all("synthetic-private-key" not in " ".join(command) for command, _ in calls)
    assert calls[-1][1]["data"] == b"synthetic-private-key"
    for service in overlay["services"].values():
        assert service["environment"]["GIGMATE_LLM_API_KEY_FILE"].endswith("/deepseek.txt")
        assert service["volumes"][0]["read_only"] is True
    assert "product-web" not in overlay["services"]


def test_product_start_refuses_an_outdated_backend_contract(tmp_path, monkeypatch):
    from io import BytesIO

    monkeypatch.setattr(start_product, "ROOT", tmp_path)
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts/openapi.json").write_text('{"version":"latest"}')
    responses = iter([{"mode": "product"}, {"version": "old"}])
    monkeypatch.setattr(
        start_product, "urlopen", lambda *a, **k: BytesIO(json.dumps(next(responses)).encode())
    )
    with pytest.raises(waha_team.TeamError, match="BACKEND_CONTRACT_DOES_NOT_MATCH"):
        start_product.verify_runtime()


def test_first_install_has_a_private_random_password_and_does_not_reset_it(tmp_path, monkeypatch):
    monkeypatch.setattr(waha_team, "ROOT", tmp_path)
    private = tmp_path / "local-data/waha-a02"
    monkeypatch.setattr(waha_team, "PRIVATE", private)
    monkeypatch.delenv("GIGMATE_PASSWORD", raising=False)
    password = waha_team.initial_password()
    assert len(password) >= 24 and password != "demo-only-change-me"
    assert waha_team.initial_password() == password
    if os.name != "nt":
        assert stat.S_IMODE((private / "login.json").stat().st_mode) == 0o600
    monkeypatch.setenv("GIGMATE_PASSWORD", "short")
    with pytest.raises(waha_team.TeamError, match="12_CHARACTERS"):
        waha_team.initial_password()
