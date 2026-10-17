"""Build and start the single local user application without synthetic fixtures.

Only the backend receives model credentials, through a private read-only volume.
The existing installation, messages, approvals and WhatsApp session are retained.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import waha_team as team  # noqa: E402

SECRET_VOLUME = "gigmate-waha-a02_model-secret"
MODEL_SETTINGS = {
    "GIGMATE_EXTRACTION_PROVIDER",
    "GIGMATE_LLM_PROVIDER",
    "GIGMATE_LLM_MODEL",
    "GIGMATE_LLM_ENDPOINT",
    "GIGMATE_LLM_LIVE",
    "GIGMATE_LLM_ALLOW_LIVE_ORIGIN",
    "GIGMATE_LLM_COST_BUDGET_USD",
    "GIGMATE_LLM_COST_INPUT_USD_PER_1K",
    "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K",
    "GIGMATE_LLM_MAX_INPUT_TOKENS",
    "GIGMATE_LLM_MAX_OUTPUT_TOKENS",
    "GIGMATE_WORKSPACE_TIMEZONE",
}


def settings_from(path):
    if not path.is_file():
        raise team.TeamError("COPY_ENV_EXAMPLE_TO_PRIVATE_ENV_FIRST")
    settings = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            settings[name.strip()] = value.strip().strip('"').strip("'")
    return settings


def private_run(command, *, data=None):
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=team.environment(),
            input=data,
            capture_output=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError):
        raise team.TeamError("PRODUCT_COMMAND_UNAVAILABLE_OR_TIMED_OUT") from None
    if result.returncode:
        # Docker output can contain operator configuration; never echo it.
        raise team.TeamError("PRODUCT_START_FAILED_CHECK_DOCKER_AND_CONFIGURATION")


def model_overlay(settings):
    environment = {name: settings[name] for name in MODEL_SETTINGS if name in settings}
    service = {"environment": environment}
    secret = settings.get("GIGMATE_LLM_API_KEY", "")
    if settings.get("GIGMATE_LLM_API_KEY_FILE"):
        path = Path(settings["GIGMATE_LLM_API_KEY_FILE"])
        if not path.is_absolute():
            path = ROOT / path
        secret = path.read_text(encoding="utf-8").strip()
    if not secret:
        environment.setdefault("GIGMATE_EXTRACTION_PROVIDER", "disabled")
        return {"services": {"ingress": service, "ingress-worker": service}}
    private_run(["docker", "volume", "create", SECRET_VOLUME])
    writer = (
        "import os,sys; "
        "fd=os.open('/secret/deepseek.txt',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o400); "
        "os.write(fd,sys.stdin.buffer.read()); os.fchown(fd,1000,1000); os.close(fd)"
    )
    private_run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "-v",
            SECRET_VOLUME + ":/secret",
            "python:3.12.10-slim",
            "python",
            "-c",
            writer,
        ],
        data=secret.encode(),
    )
    environment["GIGMATE_LLM_API_KEY_FILE"] = "/run/gigmate-model/deepseek.txt"
    service["volumes"] = [
        {
            "type": "volume",
            "source": "gigmate_model_secret",
            "target": "/run/gigmate-model",
            "read_only": True,
        }
    ]
    return {
        "services": {"ingress": service, "ingress-worker": service},
        "volumes": {"gigmate_model_secret": {"external": True, "name": SECRET_VOLUME}},
    }


def verify_runtime():
    with urlopen("http://127.0.0.1:18780/health", timeout=10) as response:
        if json.load(response).get("mode") != "product":
            raise team.TeamError("PRODUCT_MODE_MISMATCH")
    with urlopen("http://127.0.0.1:18702/openapi.json", timeout=10) as response:
        actual = json.load(response)
    expected = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))
    if actual != expected:
        raise team.TeamError("BACKEND_CONTRACT_DOES_NOT_MATCH_THIS_CHECKOUT")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="First installation only")
    args = parser.parse_args(argv)
    settings = settings_from(ROOT / ".env")
    os.environ["APP_MODE"] = "product"
    for name in (
        "GIGMATE_USERNAME",
        "GIGMATE_PASSWORD",
        "WAHA_SEND_ENABLED",
        "WAHA_SEND_CHROME",
        "WAHA_MEDIA_ENABLED",
    ):
        if name in settings:
            os.environ[name] = settings[name]
    if args.init:
        team.initialize()
    if not team.PROFILE.exists():
        raise team.TeamError("FIRST_INSTALLATION_REQUIRES_INIT")
    overlay = team.private_path(team.PRIVATE / "product-text.compose.json")
    data = json.dumps(model_overlay(settings), indent=2).encode()
    descriptor = os.open(overlay, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
    print("Building matching backend, worker and user interface...", flush=True)
    command = [
        *team.compose(),
        "-f",
        str(ROOT / "infra/product.compose.yaml"),
        "-f",
        str(overlay),
    ]
    private_run([*command, "build", "ingress", "ingress-worker", "product-web"])
    # Provision/migrate with the existing profile, without creating/restarting a WAHA session.
    team.startup(team.environment())
    private_run(
        [*command, "up", "-d", "--wait", "ingress", "ingress-worker", "product-web"]
    )
    verify_runtime()
    print("GigMate ready: http://127.0.0.1:18780")
    print(
        "Existing login is unchanged. New generated login: local-data/waha-a02/login.json"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (team.TeamError, OSError, ValueError) as exc:
        # Never print private exception values or subprocess output.
        code = (
            str(exc)
            if isinstance(exc, team.TeamError)
            else "PRIVATE_CONFIGURATION_UNREADABLE"
        )
        print("GigMate startup: " + code, file=sys.stderr)
        raise SystemExit(1) from None
