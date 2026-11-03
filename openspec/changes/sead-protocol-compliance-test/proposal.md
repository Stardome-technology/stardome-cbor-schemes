# Proposal

## Why

The operator wants a security test that submits a **non-SEAD** (non-compliant)
message and confirms the SEAD **rejects** it. The feasibility analysis found the
rejecting layer already exists: `sead-core`'s acceptance pipeline validates the
canonical CBOR envelope and rejects non-compliant submissions. Verified in
source: `POST /events` (`src/sead-core/grpc_server.cpp:809`) first decodes the
envelope (undecodable → **`ERR_INVALID_CBOR`**, HTTP 400), then
`validate_envelope` (`lib/protocol/envelope.hpp:108`) enforces required fields
1–5 (missing/empty → **`ERR_INVALID_ENVELOPE`**, HTTP 400), and
`AcceptancePipeline::stage2_event_id` (`lib/sead/pipeline.cpp`) verifies
`event_id == SHA-256(canonical_cbor(body))` (→ **`ERR_INVALID_EVENT_ID`**).
So the test is a **demonstration**, not new detection logic.

## What Changes

- **No new detection code.** This change adds a **conformance test** that submits
  a non-SEAD payload and asserts the existing rejection.
- **Two cases, honestly distinguished:**
  - **Non-SEAD / malformed** (not a valid SEAD envelope at all) →
    `sead-core` rejects at `POST /events`: **`ERR_INVALID_CBOR`** if the bytes
    are not a decodable SEAD envelope, or **`ERR_INVALID_ENVELOPE`** if it
    decodes but is missing required envelope fields. This is the operator's
    scenario and it **works today**.
  - **Valid-envelope but wrong scheme** (a well-formed SEAD envelope whose payload
    does not match the declared scheme) → currently **NOT** scheme-validated at
    commit. Flagged as a **gap**, not claimed as passing.
- The test is surfaced in the console as a **protocol conformance check** with the
  two cases clearly labeled.

## Capabilities

### New Capabilities
- `sead-protocol-conformance-testing`: A test demonstrating that non-compliant
  (non-SEAD) messages are rejected by the existing `validate_envelope` layer,
  with the scheme-mismatch gap explicitly noted.

### Modified Capabilities
<!-- none; no behavior change, only a test + honest gap documentation -->

## Impact

- **No production code change** to the rejection path (it already works).
- Console: a conformance-check test that submits a non-SEAD payload to
  `POST /events` and asserts rejection with `ERR_INVALID_CBOR` /
  `ERR_INVALID_ENVELOPE`.
- Documentation of the **scheme-validation gap** (valid-envelope-but-wrong-scheme
  is not rejected at commit) so the operator is not misled into thinking arbitrary
  "wrong" payloads are caught.
- If closing the gap is later desired, that is a separate change (add CBOR-scheme
  validation at commit) — explicitly out of scope here.

## Cross-Repo Contract (verified)

**This change owns (schemes repo / test harness only):** the conformance test
fixtures + assertions. **No production code change anywhere.**

**Consumed from `sead-service` (read-only, already exists — do NOT modify):**
- `POST /events` — `src/sead-core/grpc_server.cpp:809` (decode → structural →
  event_id pipeline).
- `validate_envelope` — `lib/protocol/envelope.hpp:108` (required fields 1–5).
- `AcceptancePipeline::stage1_structural` / `stage2_event_id` —
  `lib/sead/pipeline.cpp`.
- Rejection codes: `ERR_INVALID_CBOR` (undecodable), `ERR_INVALID_ENVELOPE`
  (missing fields), `ERR_INVALID_EVENT_ID` (event_id mismatch).

**Test target:** submit bytes to `POST /events` (directly on sead-core, or via
the gateway). Non-SEAD → expect 400 with one of the codes above.

**Ownership for local agents:** schemes-repo agent writes the test + assertions;
no sead-service agent action required (the rejection path is pre-existing and
must not be changed).
