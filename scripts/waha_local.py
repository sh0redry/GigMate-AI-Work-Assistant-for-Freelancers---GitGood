"""Local A-02 operations. Secrets/QR stay in ignored local-data, never stdout."""

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend/src"))
sys.path.insert(0, str(ROOT))

try:
    import httpx
    import uvicorn

    from gigmate.waha_adapter import AdapterError
    from gigmate.waha_client import LocalWahaClient, LocalWahaConfig
    from gigmate.waha_probe import create_probe
except ImportError:
    raise SystemExit("Use .venv; install apps/backend/requirements.lock.") from None


def private_directory():
    root = ROOT.resolve()
    directory = (root / "local-data/waha-a02").resolve()
    if not directory.is_relative_to(root / "local-data"):
        raise AdapterError("PRIVATE_PATH_REQUIRED")
    return directory


def initialize():
    directory = private_directory()
    directory.mkdir(parents=True, exist_ok=True)
    config_path, env_path = directory / "config.json", directory / ".env"
    if config_path.exists() or env_path.exists():
        raise AdapterError("LOCAL_CONFIG_EXISTS")
    api_key, webhook_secret = secrets.token_hex(32), secrets.token_hex(32)
    config = {
        "base_url": "http://127.0.0.1:18700",
        "account_id": "00000000-0000-4000-8000-000000000001",
        "session": "default",
        "api_key": api_key,
        "webhook_secret": webhook_secret,
        "allowlisted_chats": [],
        "consent_active": True,
    }
    with config_path.open("x", encoding="utf-8") as file:
        file.write(json.dumps(config, indent=2))
    with env_path.open("x", encoding="utf-8") as file:
        file.write(
            "WAHA_API_KEY_HASH=sha512:"
            + hashlib.sha512(api_key.encode()).hexdigest()
            + "\n"
        )
    return {
        "mode": "capability_probe",
        "config_created": True,
        "secrets_printed": False,
    }


def load_config():
    try:
        data = json.loads(
            (private_directory() / "config.json").read_text(encoding="utf-8")
        )
        data["allowlisted_chats"] = frozenset(data["allowlisted_chats"])
        return LocalWahaConfig(**data)
    except (OSError, ValueError, TypeError, KeyError):
        raise AdapterError("LOCAL_CONFIG_INVALID_OR_MISSING") from None


def parse_selection(answer, size):
    if not answer.strip():
        return []
    parts = answer.split(",")
    if any(not part.strip().isascii() or not part.strip().isdigit() for part in parts):
        raise AdapterError("INVALID_CHAT_SELECTION")
    indices = [int(part.strip()) - 1 for part in parts]
    if any(index < 0 or index >= size for index in indices):
        raise AdapterError("INVALID_CHAT_SELECTION")
    return list(dict.fromkeys(indices))


def save_selected_chats(selected, original):
    target = private_directory() / "config.json"
    if target.is_symlink():
        raise AdapterError("PRIVATE_PATH_REQUIRED")
    data = json.loads(original)
    data["allowlisted_chats"] = list(
        dict.fromkeys(data["allowlisted_chats"] + selected)
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp"
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        if target.is_symlink() or target.read_bytes() != original:
            raise AdapterError("LOCAL_CONFIG_CHANGED; rerun selection")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def select_chats(config, *, limit, offset):
    original = (private_directory() / "config.json").read_bytes()
    if load_config() != config:
        raise AdapterError("LOCAL_CONFIG_CHANGED; rerun selection")
    client = LocalWahaClient(config)
    try:
        chats = client.recent_chats(limit=limit, offset=offset)
    finally:
        client.close()
    if not chats:
        print("未发现可选择的聊天；可以调整 --offset 或先用手机发送测试消息。")
        return 0
    print("近期聊天（仅名称和真实 ID；只在你的本地终端显示）：")
    for number, chat in enumerate(chats, 1):
        print(f"{number}. " + json.dumps(chat, ensure_ascii=False))
    try:
        answer = input("输入要加入白名单的序号，逗号分隔，如 1,3；直接回车取消：")
    except (EOFError, KeyboardInterrupt):
        print("已取消，没有修改白名单。")
        return 0
    indices = parse_selection(answer, len(chats))
    if not indices:
        print("已取消，没有修改白名单。")
        return 0
    save_selected_chats([chats[index]["id"] for index in indices], original)
    print(f"已将所选 {len(indices)} 个聊天加入本地白名单，保留原有设置。")
    print("请同步配置后重启验证服务：")
    print(".venv\\Scripts\\python.exe scripts/waha_local.py sync-container-config")
    print(
        "docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml restart probe"
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Local WAHA A-02 capability operations; no sends"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init", help="Generate private config once without printing secrets"
    )
    probe = commands.add_parser("probe", help="Start independent HMAC probe")
    probe.add_argument(
        "--container",
        action="store_true",
        help="Bind inside loopback-published Compose service",
    )
    for name in (
        "create",
        "status",
        "qr",
        "observations",
        "restart",
        "sync-container-config",
    ):
        commands.add_parser(name)
    selection = commands.add_parser(
        "select-chats", help="Select recent chat metadata locally"
    )
    selection.add_argument("--limit", type=int, default=20)
    selection.add_argument("--offset", type=int, default=0)
    history = commands.add_parser(
        "history", help="Count available history in a configured allowlisted chat"
    )
    history.add_argument("--chat", required=True)
    history.add_argument("--limit", type=int, default=10)
    history.add_argument("--offset", type=int, default=0)
    args = parser.parse_args(argv)
    if args.command == "init":
        print(json.dumps(initialize()))
        return 0
    config = load_config()
    if args.command == "select-chats":
        return select_chats(config, limit=args.limit, offset=args.offset)
    if args.command == "probe":
        uvicorn.run(
            create_probe(config),
            host="0.0.0.0" if args.container else "127.0.0.1",
            port=18701,
            access_log=False,
            log_level="error",
        )
        return 0
    if args.command == "observations":
        try:
            with httpx.Client(
                timeout=5, trust_env=False, follow_redirects=False
            ) as client:
                response = client.get(
                    "http://127.0.0.1:18701/probe/observations",
                    headers={"Authorization": "Bearer " + config.api_key},
                )
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError):
            raise AdapterError("PROBE_UNAVAILABLE") from None
        print(json.dumps(result))
        return 0
    client = LocalWahaClient(config)
    try:
        if args.command == "create":
            result = client.create_session()
        elif args.command == "sync-container-config":
            from scripts.waha_container_config import sync_private_config

            try:
                result = sync_private_config(config)
            except RuntimeError:
                raise AdapterError("CONTAINER_CONFIG_SYNC_FAILED") from None
        elif args.command == "restart":
            result = client.restart_failed_session()
        elif args.command == "status":
            result = client.status()
        elif args.command == "qr":
            data = client.qr()
            directory = private_directory()
            target = directory / "qr.png"
            if target.is_symlink():
                raise AdapterError("PRIVATE_PATH_REQUIRED")
            target.write_bytes(data)
            result = {
                "mode": "capability_probe",
                "qr_file": "local-data/waha-a02/qr.png",
                "refresh_on_scan_qr": True,
            }
        else:
            result = client.history(args.chat, limit=args.limit, offset=args.offset)
    finally:
        client.close()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AdapterError as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError):
        raise SystemExit("LOCAL_OPERATION_FAILED") from None
