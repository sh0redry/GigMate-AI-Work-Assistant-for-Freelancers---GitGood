"""Bounded PDF IPC and hard resources; this is not a filesystem/network sandbox."""

import ctypes
import importlib.util
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .pdfparse import PdfExtraction, PdfPageText, PdfParseError

MAX_INPUT = 20 * 1024 * 1024
MAX_OUTPUT = 1024 * 1024
_slot = threading.BoundedSemaphore(1)
ERROR_CODES = frozenset(
    {
        "MEDIA_PDF_LIMIT_UNAVAILABLE",
        "MEDIA_PDF_INPUT_LIMIT",
        "MEDIA_PDF_MEMORY_LIMIT",
        "MEDIA_PDF_CHILD_FAILED",
        "MEDIA_PDF_PARSER_LIBRARY_MISSING",
        "MEDIA_PDF_NOT_PARSEABLE",
        "MEDIA_PDF_PAGE_LIMIT",
        "MEDIA_PDF_TEXT_LIMIT",
        "MEDIA_PDF_SEGMENT_LIMIT",
        "MEDIA_PDF_NO_TEXT_LAYER",
    }
)


@dataclass(frozen=True)
class Limits:
    seconds: float = 20.0
    memory: int = 512 * 1024 * 1024


def configured_limits():
    try:
        seconds = float(os.environ.get("GIGMATE_PDF_TIMEOUT_SECONDS", "20"))
        mib = int(os.environ.get("GIGMATE_PDF_MEMORY_MIB", "512"))
        if not math.isfinite(seconds) or not 1 <= seconds <= 60 or not 128 <= mib <= 1024:
            raise ValueError
        return Limits(seconds, mib * 1024 * 1024)
    except ValueError:
        raise PdfParseError("MEDIA_PDF_LIMIT_CONFIG_INVALID") from None


class WindowsJob:
    def __init__(self, process, limits):
        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working", ctypes.c_size_t),
                ("max_working", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel, self.handle = kernel, kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError
        info = Extended()
        info.basic.flags = 0x100 | 0x200 | 0x2000 | 0x8 | 0x2
        info.basic.active = 1
        info.basic.process_time = int((limits.seconds + 1) * 10_000_000)
        info.process_memory = info.job_memory = limits.memory
        if not kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ) or not kernel.AssignProcessToJobObject(
            self.handle, wintypes.HANDLE(int(process._handle))
        ):
            self.close()
            raise OSError
        # Attach before interpreter startup, not merely before reading PDF bytes.
        # Memory committed before assignment is not retroactively job-accounted.
        try:
            resume_child(process)
        except OSError:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def attach(process, limits):
    return WindowsJob(process, limits) if os.name == "nt" else None


def resume_child(process):
    class Entry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("id", wintypes.DWORD),
            ("owner", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("delta", wintypes.LONG),
            ("flags", wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenThread.restype = wintypes.HANDLE
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(4, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise OSError
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        present = kernel.Thread32First(snapshot, ctypes.byref(entry))
        while present:
            if entry.owner == process.pid:
                thread = kernel.OpenThread(2, False, entry.id)
                if not thread:
                    raise OSError
                try:
                    if kernel.ResumeThread(thread) != 1:
                        raise OSError
                    return
                finally:
                    kernel.CloseHandle(thread)
            present = kernel.Thread32Next(snapshot, ctypes.byref(entry))
        raise OSError
    finally:
        kernel.CloseHandle(snapshot)


def child_path():
    return Path(__file__).with_name("pdf_child.py")


def safe_environment():
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "LANG", "LC_ALL"}
    }


def terminate(process, job):
    if job:
        job.close()  # Kills every process in the private Job Object.
    elif os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def validate_result(raw):
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and set(data) == {"error"} and data["error"] in ERROR_CODES:
            raise PdfParseError(data["error"])
        if not isinstance(data, dict) or set(data) != {"pages", "total_pages", "empty_pages"}:
            raise ValueError
        total, empty, pages = data["total_pages"], data["empty_pages"], data["pages"]
        if (
            type(total) is not int
            or not 1 <= total <= 200
            or type(empty) is not int
            or not 0 <= empty < total
            or not isinstance(pages, list)
            or not 1 <= len(pages) <= 200
        ):
            raise ValueError
        converted = []
        for item in pages:
            if (
                not isinstance(item, dict)
                or set(item) != {"page", "text"}
                or type(item["page"]) is not int
                or not 1 <= item["page"] <= total
                or not isinstance(item["text"], str)
                or not 0 < len(item["text"]) <= 4000
            ):
                raise ValueError
            converted.append(PdfPageText(**item))
        if (
            sum(len(p.text) for p in converted) > 100000
            or len({p.page for p in converted}) + empty != total
            or [p.page for p in converted] != sorted(p.page for p in converted)
        ):
            raise ValueError
        return PdfExtraction(converted, total, empty)
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise PdfParseError("MEDIA_PDF_PROTOCOL_INVALID") from None


def run_child(content, limits):
    spec = importlib.util.find_spec("pypdf")
    if not spec or not spec.origin:
        raise PdfParseError("MEDIA_PDF_PARSER_LIBRARY_MISSING")
    deadline = time.monotonic() + limits.seconds
    process, job, threads = None, None, []
    output = bytearray()
    overflow = threading.Event()
    ready = threading.Event()
    protocol_error = []
    try:
        process = subprocess.Popen(
            [
                getattr(sys, "_base_executable", None) or sys.executable,
                "-I",
                "-B",
                "-X",
                "utf8",
                str(child_path()),
                str(limits.memory),
                str(limits.seconds),
                str(Path(spec.origin).parent.parent),
                str(os.getpid()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=safe_environment(),
            cwd=Path(__file__).parent,
            start_new_session=os.name != "nt",
            creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name == "nt" else 0,
        )
        try:
            job = attach(process, limits)
        except OSError:
            raise PdfParseError("MEDIA_PDF_LIMIT_UNAVAILABLE") from None

        def write():
            try:
                while not ready.wait(0.01):
                    if protocol_error or process.poll() is not None or time.monotonic() >= deadline:
                        return
                if not protocol_error:
                    process.stdin.write(b"1")
                    process.stdin.write(content)
            except (OSError, ValueError):
                pass
            finally:
                try:
                    process.stdin.close()
                except OSError:
                    pass

        def read():
            try:
                first = bytearray()
                while char := process.stdout.read(1):
                    first.extend(char)
                    if len(first) > 512:
                        protocol_error.append("MEDIA_PDF_PROTOCOL_INVALID")
                        return
                    if char == b"\n":
                        break
                try:
                    startup = json.loads(first)
                except (ValueError, UnicodeError):
                    protocol_error.append("MEDIA_PDF_PROTOCOL_INVALID")
                    return
                if (
                    isinstance(startup, dict)
                    and set(startup) == {"error"}
                    and startup["error"] in ERROR_CODES
                ):
                    output.extend(first)
                    return
                if (
                    not isinstance(startup, dict)
                    or set(startup) != {"ready"}
                    or type(startup["ready"]) is not int
                    or startup["ready"] != process.pid
                ):
                    protocol_error.append("MEDIA_PDF_LIMIT_UNAVAILABLE")
                    return
                ready.set()
                while chunk := process.stdout.read(4096):
                    if len(output) + len(chunk) > MAX_OUTPUT:
                        overflow.set()
                        return
                    output.extend(chunk)
            except (OSError, ValueError, TypeError):
                pass

        threads = [
            threading.Thread(target=write, daemon=True),
            threading.Thread(target=read, daemon=True),
        ]
        for thread in threads:
            thread.start()
        while True:
            if protocol_error:
                raise PdfParseError(protocol_error[0])
            if overflow.is_set():
                raise PdfParseError("MEDIA_PDF_OUTPUT_LIMIT")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PdfParseError("MEDIA_PDF_TIMEOUT")
            try:
                code = process.wait(timeout=min(0.05, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        if overflow.is_set():
            raise PdfParseError("MEDIA_PDF_OUTPUT_LIMIT")
        if protocol_error:
            raise PdfParseError(protocol_error[0])
        if any(thread.is_alive() for thread in threads):
            raise PdfParseError("MEDIA_PDF_TIMEOUT")
        if code != 0:
            raise PdfParseError("MEDIA_PDF_CHILD_TERMINATED")
        return validate_result(output)
    except OSError:
        raise PdfParseError("MEDIA_PDF_LIMIT_UNAVAILABLE") from None
    finally:
        if process:
            terminate(process, job)
            for thread in threads:
                thread.join(timeout=2)
            for pipe in (process.stdin, process.stdout):
                pipe.close()


def extract_isolated(content):
    if not isinstance(content, bytes) or not content or len(content) > MAX_INPUT:
        raise PdfParseError("MEDIA_PDF_INPUT_LIMIT")
    if not _slot.acquire(blocking=False):
        raise PdfParseError("MEDIA_PDF_BUSY")
    try:
        return run_child(content, configured_limits())
    finally:
        _slot.release()
