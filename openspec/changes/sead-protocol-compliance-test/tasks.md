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
- [x] 1.3 (Informational) Submit a **valid-envelope-but-wrong-scheme** payload →
      record that it is **accepted** today (the gap), do NOT mark it as a pass.
      [GAP CONFIRMED — informational record, NOT a rejection pass]
      (see `tests/sead_scheme_gap.py` — 3 probes against a live sead-core via
      gRPC `Core.PostEvent`, each on a fresh DB. GAP CONFIRMED 2026-09-22:
      (A) org_genesis body with extra keys 6/999 outside the CDDL `* dag_links`
      range → **ACCEPTED** (gap, not a pass); (B) semantically valid body
      encoded with an indefinite-length map (non-canonical CBOR) →
      **ACCEPTED** (gap, not a pass); (C) non-org_genesis body under
      event_type=1 → rejected `ERR_INVALID_BODY`, showing wrong-body
      rejection is only *incidental* to the type-specific decoder, not
      scheme validation. Nothing validates the body against
      `sead_v1.3.0.cddl` at commit. The test asserts the documented gap
      still holds (drift-detector): if the server ever starts rejecting A/B,
      it fails so this doc gets updated.)

## Phase 2: Surface honestly in the console

- [x] 2.1 Render the conformance result with the two cases clearly labeled
      (rejected vs. not-rejected).
      (see `tests/sead_conformance_report.py` — runs the full probe set
      against a live sead-core via gRPC `Core.PostEvent` (fresh DB per
      probe) and renders a report with the two cases clearly labeled:
      CASE 1 — REJECTED: non-SEAD/malformed payloads (ERR_INVALID_CBOR /
      ERR_INVALID_ENVELOPE from the existing decode + validate_envelope
      layers); CASE 2 — NOT REJECTED: valid-envelope-but-wrong-scheme
      payloads (accepted today = the documented GAP, NOT a pass; the
      wrong_body_type probe is marked as rejected only INCIDENTALLY by the
      type-specific decoder). Positive control included so rejections are
      shown to be specific to non-compliance. 8/8 probes behaved as
      documented, PASS verified 2026-09-22. Drift-detector: fails if any
      case diverges from the documented contract.)
- [x] 2.2 Note that the rejection comes from the existing `validate_envelope`
      layer (no new detection added).
      (see `tests/REJECTION_ATTRIBUTION.md` — verified against sead-service
      source 2026-09-22: CASE 1 rejections come entirely from pre-existing
      code — `proto_to_envelope`/`decode_cbor` → `ERR_INVALID_CBOR`
      (`src/sead-core/grpc_server.cpp:810-812`) and `validate_envelope`
      (`lib/protocol/envelope.hpp:108`, called at `grpc_server.cpp:816`)
      → `ERR_INVALID_ENVELOPE` for missing required envelope fields 1/2/4/5.
      `validate_envelope` is structural-only (never inspects the body
      against `sead_v1.3.0.cddl`), which is exactly why the CASE 2 gap
      persists. No production code was modified by this change — all new
      code lives in `tests/` of stardome-cbor-schemes.)

## Quality Gate

- [x] Non-SEAD/malformed payloads are rejected (`ERR_INVALID_CBOR` /
      `ERR_INVALID_ENVELOPE`).
      (Gate verified 2026-09-22 by a fresh live run of
      `tests/sead_negative_control.py` against sead-core via gRPC
      `Core.PostEvent`: 4/4 malformed cases rejected with the expected
      codes — empty bytes and non-CBOR bytes → `ERR_INVALID_CBOR`
      (pre-existing `proto_to_envelope`/`decode_cbor`,
      `src/sead-core/grpc_server.cpp:810-812`); missing body (key 4) and
      missing protocol_version (key 1) → `ERR_INVALID_ENVELOPE`
      (pre-existing `validate_envelope`, `lib/protocol/envelope.hpp:108`,
      called at `grpc_server.cpp:816`). Attribution detail in
      `tests/REJECTION_ATTRIBUTION.md`.)
- [x] The scheme-validation gap is documented, not hidden or falsely claimed
      as passing.
      (Gate verified 2026-09-22 by a fresh live re-run of
      `tests/sead_scheme_gap.py` against sead-core via gRPC `Core.PostEvent`
      (fresh DB per case): 3/3 cases behaved as documented — (A) extra keys
      6/999 outside the CDDL `* dag_links` range → **ACCEPTED (GAP)**,
      (B) non-canonical indefinite-length body map → **ACCEPTED (GAP)**,
      (C) wrong body type → rejected only INCIDENTALLY by the type-specific
      decoder. The gap is recorded honestly in three places, none of which
      claims it as a passing rejection: task 1.3 above (explicitly labelled
      "GAP CONFIRMED — informational record, NOT a rejection pass"), the
      drift-detector in `tests/sead_scheme_gap.py` (asserts the gap still
      HOLDS — it FAILS if the server ever starts rejecting A/B, forcing this
      doc to be updated rather than silently drifting), and CASE 2 —
      NOT REJECTED in `tests/sead_conformance_report.py` (rendered as the
      documented gap, not a pass). Per the spec requirement "Wrong-scheme
      gap shown honestly", nothing in this change marks the wrong-scheme case
      as rejected.)
- [x] No production code change to the rejection path (test-only change).
      (Verified 2026-09-22 by full diff audit: `git diff origin/dev --name-only`
      in stardome-cbor-schemes shows only `.gitignore` (added ignores for
      `__pycache__/` and `tests/gen/` test artifacts), this `tasks.md`, and
      five new files under `tests/` (`sead_positive_control.py`,
      `sead_negative_control.py`, `sead_scheme_gap.py`,
      `sead_conformance_report.py`, `REJECTION_ATTRIBUTION.md`). Zero
      production source files changed — a filter for `*.cpp/*.hpp/*.c/*.h`
      outside `tests/` and a grep for `grpc_server|envelope|validate|cddl|src/|lib/`
      in the changed-path list both return nothing. The rejection path itself
      lives in sead-service (`src/sead-core/grpc_server.cpp`,
      `lib/protocol/envelope.hpp`); that repo's working tree is clean with no
      unpushed commits (`git status --short` empty). All new code is
      client-side test tooling that talks to the live server over gRPC
      `Core.PostEvent` — no new detection was added anywhere.)
- [ ] The console output is honest about what is and isn't caught.
