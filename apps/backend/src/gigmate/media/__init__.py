"""Real-model media processor (Role B).

This package implements :class:`gigmate.media_processing.MediaProcessor` for the
WAHA media ingestion seam introduced by the WAHA media ingestion batch. A owns
storage, leases, authorization and review; B owns OCR / ASR / parsing / GenAI
through this processor. The seam is loaded via the ``GIGMATE_MEDIA_PROCESSOR_FACTORY``
environment variable (e.g. ``gigmate.media.processor:MediaProcessorImpl``) and
never accepts credentials or model endpoints over HTTP.

The default implementation in :mod:`gigmate.media.processor` mirrors the two-gate
safety pattern used by :mod:`gigmate.extraction.llm`:

1. Module-level :data:`_ENABLED` flag. While ``False`` (the shipping default) the
   processor refuses every call with :class:`gigmate.media_processing.ProcessingUnavailable`
   *before* it reads any environment variable. This is the safety net that
   prevents a future contributor from silently turning the seam on by exporting
   :envvar:`GIGMATE_MEDIA_LIVE`.
2. ``GIGMATE_MEDIA_LIVE=1`` operator switch. Even after the class flag flips,
   the processor refuses every call unless this variable is exported.

The seam returns :class:`gigmate.contracts.WahaMediaResult` proposals only.
Merchant confirmation is enforced by :class:`gigmate.contracts.WahaMediaEvidence`
downstream; B never marks a field ``confirmed`` and never grants execution
authority.
"""

from __future__ import annotations

from .processor import MediaProcessorImpl, build_processor

__all__ = ["MediaProcessorImpl", "build_processor"]
