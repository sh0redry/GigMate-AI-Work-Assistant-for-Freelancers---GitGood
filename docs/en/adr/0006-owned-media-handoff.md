# ADR 0006 Owned media reads and the A/B processing boundary

- Date: 2026-10-10
- Status: A implementation; B real processor and physical acceptance pending.

The owner authorized original image/audio/PDF/TXT reading and confirmed B remains responsible for real OCR/ASR/parsing/GenAI. Supersede ADR 0005's file-reading deferral for explicit owned requests only. Reception remains metadata-only with global provider downloads disabled. A adds private bounded blobs, protected preview, source/context/version/lease checks and durable stages; B receives scoped bytes and returns strict context-only segments/suggestions. Nothing confirms a work order or sends externally.

Provider/model I/O occurs after lease commit. Read-only downloads have bounded retries. Unknown model outcomes require lookup of the original request, never automatic resubmission. File/result review is distinct from customer confirmation and merchant execution approval. A result's snapshot/attachment/hash/page/time provenance must not masquerade as an existing canonical SourceRef revision; B/C must separately agree promotion semantics.

Additive migration 0009 and generated contracts implement the seam. Opt-in Compose shares one private media volume across API/worker. Source-based retention and reference-aware orphan cleanup retain identity but remove content. Physical formats, provider cache retention, B accuracy/prompt-injection tests and full account/backup deletion remain independent gates. See [A/B protocol and acceptance](../role-a-media-ingestion.md).
