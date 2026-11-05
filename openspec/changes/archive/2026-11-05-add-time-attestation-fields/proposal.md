# Add module time attestation fields (attestation/request/tree v2.0.0, in place)

## Why

The Stardome attestation binds time only through a *host-provided* timestamp
(tree leaf 42, `leaf_timestamp: 12`, "RTC Timestamp — ISO8601 UTC, provided by
the host device"). Three facts make that design untenable for Stardome modules:

1. **The request schema has no timestamp field.** Fixed leaves are device-owned;
   `source_data` maps only to `leaf_source` slots. A host-provided leaf 42 is
   not deliverable under the current grammar — the comment contradicts both the
   request schema and the host verifier (which labels leaf 42 "RTC-backed").
2. **A module must attest its own measured time.** The module owns a
   battery-backed, free-running RTC (never stepped). Its raw reading at signing
   is what witnesses monotonic continuity and tamper (RTC count loss = tamper),
   independent of any host input.
3. **Anti-dating needs a recorded verdict.** Where an integrator *does* declare
   a host time, the module cross-checks it against its own RTC and must record
   the verdict in the attestation — enforcement visible to verifiers, tolerance
   owned by policy (`shcap_policy_id`), not by the schema.

## What Changes

In-place revision of the **v2.0.0** Stardome module schemas (v2.0.0 is not yet
deployed by any module; no version bump). **v2.0.1 (third-party software
profile) is NOT touched.**

- `stardome_attestation_schema_v2.0.0.cddl` — add:
  - `16: uint` — `module_rtc_time`: raw module RTC reading (Unix seconds,
    free-running RTC) at signing. Always present.
  - `? 17: uint` — `host_time_claim`: host-declared timestamp cross-checked by
    the module; absent when the integrator supplies no host time.
  - `18: time_check_result` — module verdict at signing:
    `time_check_result = &(no_host_time: 0, approved: 1, not_approved: 2)`.
- `stardome_attestation_request_schema_v2.0.0.cddl` — add:
  - `? 8: uint` — `host_time_claim`: the ingress for the host-declared time
    (absent = case (a), no host time).
- `stardome_attestation_tree_schema_v2.0.0.cddl` —
  - `leaf_timestamp: 12` comment corrected: **device-owned** module RTC value
    (raw uint Unix seconds), not host-provided.
  - New type ids: `leaf_host_time_claim: 15`, `leaf_time_check_result: 16`.
  - Fixed leaf map: `42: 12` (module RTC), `43: 15` (host claim;
    `leaf_padding` when absent), `44: 16` (verdict); `leaf_source` slots become
    `45..62` (18 slots, `source_leaves_amt` unchanged at 32 leaves total).

Non-goals: no changes to the epoch schema, to v2.0.1, to `tree_depth`, or to
existing field semantics (`epoch_hash`, `mark_w`, chains unchanged).

## Impact

- Affected specs: `stardome-attestation-schema` (new capability spec in this
  change), `stardome-attestation-request-schema`, `stardome-attestation-tree-schema`.
- Affected code: none in this repo (CDDL + docs only).
- Downstream (separate changes, other repos):
  - adeptus-v3 pinned manifest `docs/attestation-tree-v2.0.0-pinned.yaml`
    re-pin (SHA-256 of all three CDDLs change).
  - adeptus-v3 firmware: RTC driver + field emission (change S2).
  - stardome-client{,-private,-private-usb}: verifier + fixtures (after S2).
  - Schema owner ruling requested on the leaf-42 comment correction (this
    change implements the device-owned reading; see design.md D3).
