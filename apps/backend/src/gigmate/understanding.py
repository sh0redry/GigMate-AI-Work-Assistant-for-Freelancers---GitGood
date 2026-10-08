"""Two fixed fictional examples, deliberately not a general language model.

This module is kept as a thin compatibility wrapper around the deterministic
extraction provider so existing Replay smoke tests can keep monkey patching
``gigmate.worker.extract``. The actual proposal generation lives in
``gigmate.extraction.deterministic.DeterministicProvider``.
"""

from __future__ import annotations

from gigmate.extraction.legacy import _legacy_extract as extract

__all__ = ["extract"]
