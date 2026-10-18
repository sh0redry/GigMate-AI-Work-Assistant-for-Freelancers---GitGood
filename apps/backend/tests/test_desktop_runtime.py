"""Generated desktop configuration must pass the actual backend gate, offline."""

import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("options", "live"),
    [
        ({}, False),
        ({"modelKey": "synthetic-key"}, False),
        ({"aiEnabled": True, "aiConsent": True, "modelKey": "synthetic-key"}, False),
        (
            {
                "aiEnabled": True,
                "aiConsent": True,
                "modelKey": "synthetic-key",
                "inputPrice": "NaN",
                "outputPrice": "0.002",
            },
            False,
        ),
        (
            {
                "aiEnabled": True,
                "aiConsent": True,
                "modelKey": "synthetic-key",
                "inputPrice": "0.001",
                "outputPrice": "0.002",
            },
            True,
        ),
    ],
)
def test_generated_worker_config_passes_backend_gate_without_vendor_calls(
    monkeypatch, tmp_path, options, live
):
    import os

    from gigmate.extraction.reviewed import configured_for_live
    from gigmate.worker import audit_provider_config

    script = """
const fs=require('node:fs'),r=require('./apps/desktop/runtime.cjs');
const options=JSON.parse(fs.readFileSync(0,'utf8'));
const profile=r.newProfile({username:'synthetic',password:'synthetic-password',...options});
process.stdout.write(JSON.stringify(r.composeDocument(profile,'/synthetic','http://127.0.0.1:27880').services.worker.environment));
"""
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(options),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=True,
        timeout=15,
    )
    generated = json.loads(result.stdout)
    for key in list(os.environ):
        if key.startswith("GIGMATE_"):
            monkeypatch.delenv(key)
    key_file = tmp_path / "synthetic-model.key"
    key_file.write_text(options.get("modelKey", ""))
    generated["GIGMATE_LLM_API_KEY_FILE"] = str(key_file)
    for key, value in generated.items():
        monkeypatch.setenv(key, value)
    assert audit_provider_config() is True
    assert configured_for_live() is live


def test_initializer_moves_key_out_of_monitor_volume_and_preserves_account(
    environment, monkeypatch, tmp_path
):
    from scripts import desktop_init

    from gigmate import db as database
    from gigmate.seed import uid

    _, factory, _ = environment
    config = tmp_path / "config"
    model = tmp_path / "model"
    config.mkdir()
    (config / "model.key").write_text("synthetic-obsolete-key")
    monkeypatch.setattr(
        desktop_init,
        "Path",
        lambda value: {"/run/desktop-config": config, "/run/desktop-model": model}[value],
    )
    monkeypatch.setattr(
        desktop_init.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0)
    )
    monkeypatch.setattr(database, "Session", factory)
    settings = {
        "connectionId": str(uuid4()),
        "username": "synthetic",
        "wahaKey": "synthetic-waha",
        "webhookSecret": "synthetic-webhook",
        "modelKey": "synthetic-model",
    }
    with factory() as db:
        old_hash = db.get(database.Account, uid(1)).password_hash
    for _ in range(2):
        monkeypatch.setattr(desktop_init.sys, "stdin", io.StringIO(json.dumps(settings)))
        desktop_init.main()
    assert not (config / "model.key").exists()
    assert (model / "model.key").read_text() == settings["modelKey"]
    assert settings["modelKey"] not in (config / "config.json").read_text()
    with factory() as db:
        assert db.get(database.Account, uid(1)).password_hash == old_hash
