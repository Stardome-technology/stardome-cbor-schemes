# Tasks — add-time-attestation-fields

## Phase 1 — CDDL revision

- [x] 1.1 `stardome_attestation_schema_v2.0.0.cddl`: add keys 16/17/18 +
  `time_check_result` enum + `where:` documentation (per approved field set).
- [x] 1.2 `stardome_attestation_request_schema_v2.0.0.cddl`: add optional key 8
  `host_time_claim` + documentation (absent = no host time).
- [x] 1.3 `stardome_attestation_tree_schema_v2.0.0.cddl`: correct
  `leaf_timestamp: 12` comment (device-owned module RTC, raw uint Unix
  seconds); add `leaf_host_time_claim: 15`, `leaf_time_check_result: 16`;
  update fixed map `42: 12, 43: 15, 44: 16`, `leaf_source` range `45..62`;
  update the trailing schema array accordingly.
- [ ] 1.4 Cross-check the three files for internal consistency (field names,
  comments, counts: 14 fixed + 18 source = 32).

## Phase 2 — Validation gate

- [ ] 2.1 Grammar-validate the three CDDLs (`cddl` CLI if available on the
  build host; otherwise manual review + note in MR).
- [ ] 2.2 `openspec validate add-time-attestation-fields --strict` green.

## Phase 3 — Downstream pointers (no code here)

- [ ] 3.1 MR description lists downstream follow-ups: adeptus-v3 pinned-manifest
  re-pin (S1-land), firmware emission (S2), client verifier/fixtures (post-S2).
- [ ] 3.2 Ask schema owner to confirm D3 (leaf-42 device-owned reading).
