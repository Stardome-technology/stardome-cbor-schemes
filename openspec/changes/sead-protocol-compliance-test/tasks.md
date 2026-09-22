# Tasks

> **IMPLEMENTATION ORDER: WAVE 1 (start here) — #1 of 5.**
> **Repo:** stardome-cbor-schemes. **Risk:** LOW (test-only, no production change).
> **Depends on:** NOTHING. **Blocks:** NOTHING. Safe to run in parallel with any other change.
> See `openspec/SEQUENCING.md` for the full cross-repo order.

## Phase 1: Conformance test (uses existing rejection)

- [x] 1.1 Submit a **genuine** SEAD envelope → assert **accepted** (positive control).
      (see `tests/sead_positive_control.py` — genuine org_genesis signed with
      XMSS-SHAKE256_20_256 test vector, submitted via gRPC `Core.PostEvent` to a
      live sead-core; asserts `status="accepted"`. PASS verified 2026-09-22.)
- [x] 1.2 Submit a **non-SEAD / malformed** payload to `POST /events` → assert
      **rejected** with `ERR_INVALID_CBOR` (undecodable) or `ERR_INVALID_ENVELOPE`
      (missing fields) — the operator's scenario; works today.
      (see `tests/sead_negative_control.py` — 4 malformed cases (empty bytes,
      non-CBOR bytes, missing body+signature, missing protocol_version)
      submitted via gRPC `Core.PostEvent` to a live sead-core; each asserted
      rejected with the expected error code. 4/4 PASS verified 2026-09-22.
      Rejection comes from the existing `proto_to_envelope` decode +
      `validate_envelope` layers — no new detection added.)
- [ ] 1.3 (Informational) Submit a **valid-envelope-but-wrong-scheme** payload →
      record that it is **accepted** today (the gap), do NOT mark it as a pass.

## Phase 2: Surface honestly in the console

- [ ] 2.1 Render the conformance result with the two cases clearly labeled
      (rejected vs. not-rejected).
- [ ] 2.2 Note that the rejection comes from the existing `validate_envelope`
      layer (no new detection added).

## Quality Gate

- [ ] Non-SEAD/malformed payloads are rejected (`ERR_INVALID_CBOR` /
      `ERR_INVALID_ENVELOPE`).
- [ ] The scheme-validation gap is documented, not hidden or falsely claimed as passing.
- [ ] No production code change to the rejection path (test-only change).
- [ ] The console output is honest about what is and isn't caught.
