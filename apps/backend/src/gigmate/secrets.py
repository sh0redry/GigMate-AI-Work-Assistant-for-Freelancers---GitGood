"""Reading model credentials without putting them in a command line.

Issue #29 asks the maintainer to select the real vendor and configure its
credential privately. An environment variable is fine for a local run but it
leaks into ``docker inspect``, process listings and shell history on a server,
so every credential here can also be supplied as a **file**:

* ``GIGMATE_LLM_API_KEY_FILE=/run/secrets/deepseek``
* ``GIGMATE_MEDIA_API_KEY_FILE=/run/secrets/media-vendor``

The file wins when both are present, because a file is the deliberate choice.
A file that is named but unreadable is a hard failure, never an empty key:
silently running unconfigured is how a deployment ends up refusing every call
for hours without saying why.
"""

from __future__ import annotations

import os
from pathlib import Path


class SecretUnreadable(RuntimeError):
    """A ``*_FILE`` variable was set but the file could not be read."""


def secret(name: str) -> str:
    """Return the credential for ``name`` from ``<name>_FILE`` or ``<name>``."""

    path = os.environ.get(f"{name}_FILE", "").strip()
    if not path:
        return os.environ.get(name, "").strip()
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SecretUnreadable(
            f"{name}_FILE is set to {path!r} but could not be read: {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise SecretUnreadable(
            f"{name}_FILE is set to {path!r} but is not UTF-8 text: {exc}"
        ) from exc


def configured(name: str) -> bool:
    """Whether a credential is present, without returning it."""

    try:
        return bool(secret(name))
    except SecretUnreadable:
        return False


__all__ = ["SecretUnreadable", "configured", "secret"]
