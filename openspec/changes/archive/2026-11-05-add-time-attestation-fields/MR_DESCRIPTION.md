# MR: Add module time attestation fields (attestation/request/tree v2.0.0, in place)

Change: `add-time-attestation-fields` · Branch: `feat/add-time-attestation-fields` → `stardome-stripped`

## Summary

In-place revision of the three Stardome module v2.0.0 schemas (v2.0.0 is not yet
deployed by any module; no version bump; v2.0.1 third-party profile untouched) so
the module attests its **own measured time** instead of relying on an
undeliverable host-provided leaf-42 timestamp:

- `stardome_attestation_schema_v2.0.0.cddl` — new keys:
  `16: uint` `module_rtc_time` (raw module RTC Unix seconds at signing, always
  present), `? 17: uint` `host_time_claim` (absent ⇔ no host time),
  `18: time_check_result` with
  `time_check_result = &(no_host_time: 0, approved: 1, not_approved: 2)`.
- `stardome_attestation_request_schema_v2.0.0.cddl` — new optional
  `? 8: uint` `host_time_claim` (ingress for the host-declared time).
- `stardome_attestation_tree_schema_v2.0.0.cddl` — `leaf_timestamp: 12` comment
  corrected to **device-owned** module RTC (raw uint Unix seconds); new type ids
  `leaf_host_time_claim: 15`, `leaf_time_check_result: 16`; fixed leaf map
  `42: 12, 43: 15, 44: 16` (`leaf_padding` when 43 absent); `leaf_source` slots
  shifted to `45..62` (14 fixed + 18 source = 32 leaves, `tree_depth` 5
  unchanged).

Design decisions and rationale: `design.md` (D1 raw uint arithmetic, D2 mandatory
module witness / optional host claim, D3 leaf-42 device-owned reading, D4 fixed
set 12→14, D5 nameless verdict enum; tolerance stays in `shcap_policy_id`
policy). Spec delta: `specs/stardome-time-attestation/`.

## Validation

- CDDL grammar validation (task 2.1): `cddl` 0.10.7 on the build host — request
  and attestation schemas pass after the ratified dangling-prose-line fix
  (`9fcb790`); the tree-schema chained-range (`45..62`) validator deviation is
  left as-is per human ruling A (2026-11-04).
- `openspec validate add-time-attestation-fields --strict` green (task 2.2).
- Internal consistency cross-check (task 1.4): field names, comments, leaf
  counts (14 fixed + 18 source = 32) consistent across the three files.

## Downstream follow-ups (separate changes, other repos)

1. **adeptus-v3 pinned-manifest re-pin (S1-land)** — re-pin
   `docs/attestation-tree-v2.0.0-pinned.yaml` in adeptus-v3: the SHA-256s of all
   three revised CDDLs (`stardome_attestation_schema_v2.0.0.cddl`,
   `stardome_attestation_request_schema_v2.0.0.cddl`,
   `stardome_attestation_tree_schema_v2.0.0.cddl`) change with this merge, so the
   consumer-side pinned manifest must be updated to the merged bytes as the
   first step after this MR lands.
2. **adeptus-v3 firmware emission (change S2)** — RTC driver + emission of the
   new fields: `module_rtc_time` (key 16), optional `host_time_claim` (key 17),
   `time_check_result` verdict (key 18), and the corresponding tree leaves 42/43/44.
3. **stardome-client{,-private,-private-usb} verifier + fixtures (after S2)** —
   verifier support for the new fields/leaves (including the leaf-42
   device-owned reading) and updated test fixtures.
4. **Schema owner confirmation of D3 (task 3.2)** — confirm the leaf-42
   device-owned module-RTC reading (this change implements it; the fix is
   comment-only for the slot, semantic for the value placed there).

## Non-goals

No changes to the epoch schema, to v2.0.1, to `tree_depth`, or to existing field
semantics (`epoch_hash`, `mark_w`, chains unchanged). No code changes in this
repo (CDDL + docs only).
