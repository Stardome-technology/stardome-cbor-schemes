# Rejection attribution — the existing `validate_envelope` layer (OpenSpec 2.2)

**Note: the rejection exercised by this change comes entirely from the
pre-existing `validate_envelope` layer. No new detection logic was added
anywhere.** This satisfies the OpenSpec requirement "No new detection logic
is added" (`specs/sead-protocol-conformance-testing/spec.md`) and backs the
"test-only" claim in the proposal.

## Verified code path (sead-service @ this change)

When a payload arrives at `POST /events` (gRPC `Core.PostEvent`), the
rejection for CASE 1 (non-SEAD / malformed) happens in this order, all in
**existing** code:

1. **Decode layer** — `src/sead-core/grpc_server.cpp:810`
   `proto_to_envelope()` calls `SeadEnvelope::decode_cbor()`. If the bytes
   are empty or not a decodable SEAD envelope map, `PostEvent` returns
   `ERR_INVALID_CBOR` (`grpc_server.cpp:812`).
   → covers probes `empty_bytes`, `non_cbor_bytes`.

2. **Structural validation layer** — `src/sead-core/grpc_server.cpp:816`
   calls `validate_envelope()`, defined at `lib/protocol/envelope.hpp:108`.
   It checks only that the required envelope fields are present:
   - key 1 `protocol_version` non-empty
   - key 2 `event_type` non-zero
   - key 4 `body` non-empty
   - key 5 `signature` non-empty
   Any missing field → `ERR_INVALID_ENVELOPE` with a per-field message.
   → covers probes `missing_body_and_signature`, `missing_protocol_version`.

3. Only *after* these existing layers pass does the pipeline continue to
   `verify_event_id` and the type-specific decoder dispatch
   (`grpc_server.cpp:826+`). The CASE 2 probes reach this far; the
   incidental `ERR_INVALID_BODY` on `wrong_body_type` comes from the
   type-specific decoder, not from any scheme validation added here.

## What this change did NOT touch

- `validate_envelope` (`lib/protocol/envelope.hpp:108`) — unchanged.
- `proto_to_envelope` / `decode_cbor` — unchanged.
- The commit path / DAG insertion — unchanged.
- All new code lives in `tests/` of **stardome-cbor-schemes** (probe
  scripts + report renderer). Zero production-code changes in any repo.

## Consequence for the conformance report

The `CASE 1 — REJECTED` section of `tests/sead_conformance_report.py`
reports **pre-existing behaviour**, demonstrated — not introduced. The
`CASE 2 — NOT REJECTED` gap persists precisely because `validate_envelope`
is structural-only: it never inspects the body against
`sead_v1.3.0.cddl`. If a future change adds body-level scheme validation,
the drift-detector in the report will fail and this note plus tasks 1.3/2.1
must be updated.

References verified against sead-service on 2026-09-22
(`grep validate_envelope`: `lib/protocol/envelope.hpp:108`,
`src/sead-core/grpc_server.cpp:816`, `lib/sead/pipeline.cpp:31`,
`lib/sead/sync.cpp:170`).
