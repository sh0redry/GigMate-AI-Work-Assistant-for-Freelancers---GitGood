"""Copy private configuration through stdin to fixed Docker volumes, never argv/logs.

This avoids Windows host-share availability and single-file inode replacement.
Only operator-created volumes and known configuration filenames are writable.
"""

import json
import subprocess
from dataclasses import asdict

ALLOWED = {
    "gigmate-waha-a02": {
        "waha-monitor-config": {"config.json", "bindings/ingress.json"},
        "waha-ingress-bindings": {"ingress.json"},
    },
    "gigmate-waha-recovery": {"recovery-binding": {"binding.json"}},
}
WRITER = """
import json,os,pathlib,sys,tempfile
payload=json.load(sys.stdin)
for mount,files in payload.items():
    root=pathlib.Path('/config')/mount
    for name,data in files.items():
        target=root/name
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,delete=False) as file:
            json.dump(data,file)
            file.flush()
            os.fsync(file.fileno())
            temporary=file.name
        os.chmod(temporary,0o600)
        os.chown(temporary,1000,1000)
        os.replace(temporary,target)
"""


def sync_volumes(project, bundles, *, run=subprocess.run):
    if (
        project not in ALLOWED
        or not bundles
        or any(
            volume not in ALLOWED[project]
            or not files
            or set(files) - ALLOWED[project][volume]
            for volume, files in bundles.items()
        )
    ):
        raise RuntimeError("INVALID_CONFIG_VOLUME_TARGET")
    try:
        payload = json.dumps(bundles)
        if len(payload) > 2 * 1024 * 1024:
            raise RuntimeError("PRIVATE_CONFIG_TOO_LARGE")
        args = ["docker", "run", "--rm", "-i", "--network", "none"]
        for volume in bundles:
            name = project + "_" + volume
            result = run(
                [
                    "docker",
                    "volume",
                    "create",
                    "--label",
                    "com.docker.compose.project=" + project,
                    "--label",
                    "com.docker.compose.volume=" + volume,
                    name,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode:
                raise RuntimeError("CONTAINER_CONFIG_SYNC_FAILED")
            args.extend(["--mount", f"type=volume,src={name},dst=/config/{volume}"])
        args.extend(["python:3.12.10-slim", "python", "-c", WRITER])
        result = run(args, input=payload, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("CONTAINER_CONFIG_SYNC_FAILED")
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        raise RuntimeError("CONTAINER_CONFIG_SYNC_FAILED") from None


def sync_private_config(config, binding=None, *, run=subprocess.run):
    data = asdict(config)
    data["allowlisted_chats"] = sorted(config.allowlisted_chats)
    bundles = {"waha-monitor-config": {"config.json": data}}
    if binding:
        bundles["waha-monitor-config"]["bindings/ingress.json"] = asdict(binding)
        bundles["waha-ingress-bindings"] = {"ingress.json": asdict(binding)}
    sync_volumes("gigmate-waha-a02", bundles, run=run)
    return {"container_config_synced": True, "recreate_services_required": True}
