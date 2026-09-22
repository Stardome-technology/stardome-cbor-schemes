# Tasks

## Phase 1: Conformance test (uses existing rejection)

- [ ] 1.1 Submit a **genuine** SEAD envelope → assert **accepted** (positive control).
- [ ] 1.2 Submit a **non-SEAD / malformed** payload to `POST /events` → assert
      **rejected** with `ERR_INVALID_CBOR` (undecodable) or `ERR_INVALID_ENVELOPE`
      (missing fields) — the operator's scenario; works today.
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
