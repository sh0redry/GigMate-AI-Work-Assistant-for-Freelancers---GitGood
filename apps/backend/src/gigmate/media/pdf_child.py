"""Private PDF child entrypoint. Only stdlib is loaded before resource limits."""

import ctypes
import importlib.util
import json
import math
import os
import signal
import sys
from pathlib import Path


def set_limits(memory, seconds):
    if os.name == "nt":
        return  # Parent assigns a Job Object before releasing stdin's gate.
    if sys.platform != "linux":
        raise RuntimeError("MEDIA_PDF_LIMIT_UNAVAILABLE")
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    cpu = math.ceil(seconds) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def bind_parent(expected):
    if sys.platform != "linux":
        return
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    if (
        os.getppid() != expected
        or libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0
        or os.getppid() != expected
    ):
        raise RuntimeError("MEDIA_PDF_LIMIT_UNAVAILABLE")


def main():
    try:
        memory, seconds = int(sys.argv[1]), float(sys.argv[2])
        try:
            set_limits(memory, seconds)
            bind_parent(int(sys.argv[4]))
        except (OSError, ValueError, RuntimeError):
            print(json.dumps({"error": "MEDIA_PDF_LIMIT_UNAVAILABLE"}), flush=True)
            return 0
        print(json.dumps({"ready": os.getpid()}), flush=True)
        if sys.stdin.buffer.read(1) != b"1":
            return 1
        content = sys.stdin.buffer.read(20 * 1024 * 1024 + 1)
        if not content or len(content) > 20 * 1024 * 1024:
            print(json.dumps({"error": "MEDIA_PDF_INPUT_LIMIT"}), flush=True)
            return 0
        # Only the locked pypdf directory is added, not the worker's PYTHONPATH.
        sys.path.insert(0, sys.argv[3])
        spec = importlib.util.spec_from_file_location(
            "pdf_local", Path(__file__).with_name("pdfparse.py")
        )
        parser = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = parser
        spec.loader.exec_module(parser)
        try:
            result = parser._extract_local(content)
        except parser.PdfParseError as exc:
            print(json.dumps({"error": str(exc).split(":", 1)[0]}), flush=True)
            return 0
        payload = {
            "pages": [{"page": p.page, "text": p.text} for p in result.pages],
            "total_pages": result.total_pages,
            "empty_pages": result.empty_pages,
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0
    except MemoryError:
        print('{"error":"MEDIA_PDF_MEMORY_LIMIT"}', flush=True)
        return 0
    except Exception:
        print('{"error":"MEDIA_PDF_CHILD_FAILED"}', flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
