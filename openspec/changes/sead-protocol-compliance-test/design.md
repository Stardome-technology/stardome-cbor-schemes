# Design

## Approach

A conformance test that exercises the **existing** rejection layer. No new
detection logic. The value is demonstrating the boundary honestly.

## The rejection boundary

`sead-core` `validate_envelope` enforces the canonical SEAD CBOR envelope
schema. A payload that is not a valid SEAD envelope is rejected with
`INVALID_SEAD_ENVELOPE` before it ever reaches the DAG. This is the layer the
operator's "non-SEAD message" test targets.

## Two cases (must be distinguished)

1. **Non-SEAD / malformed** — the submitted bytes are not a valid SEAD envelope
   (wrong structure, missing required envelope fields, not canonical CBOR, etc.).
   → `validate_envelope` rejects: `INVALID_SEAD_ENVELOPE`. **Works today.**
2. **Valid-envelope, wrong scheme** — a well-formed SEAD envelope whose *payload*
   does not conform to the declared CBOR scheme. → **NOT** scheme-validated at
   commit; this is accepted today. **Gap.** The test SHALL NOT claim this is
   rejected.

## Test scenarios

- **Positive control:** a genuine SEAD envelope → accepted.
- **Operator scenario:** a non-SEAD blob (e.g. arbitrary bytes / a non-SEAD CBOR
  structure) → rejected `INVALID_SEAD_ENVELOPE`.
- **Gap illustration (informational):** a valid-envelope-but-wrong-scheme payload
  → shown as **accepted** with a note that scheme validation at commit is a known
  gap (not a pass).

## Honesty requirement

The console output SHALL make clear:
- what is rejected (non-SEAD/malformed),
- what is NOT rejected (valid-envelope wrong scheme),
- that no new detection was added — the existing `validate_envelope` does the work.

## Non-goals

- No change to `validate_envelope` or the commit path.
- No CBOR-scheme validation added at commit (that would be a separate change).
- No claim that arbitrary "wrong" payloads are caught.
