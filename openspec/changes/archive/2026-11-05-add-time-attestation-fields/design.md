# Design — add-time-attestation-fields

## Context

The module attests with a Merkle tree whose root is XMSS-signed; therefore
**every attestation field must have a tree leaf** (3 new fields ⇒ 3 leaves).
The module is stateless w.r.t. chains (host delivers `epoch` and
`previous_mark_w_hash` per request); the new time fields follow the same
pattern: claim enters via the request, verdict + module reading exit in the
attestation.

## Decisions

### D1 — Raw uint Unix-seconds, not bytes, not hashes
Both times are `uint` (RTC Unix seconds). Verifiers must do arithmetic
(`declared ≈ anchor + (module_rtc − anchor_rtc)`), which requires clear values;
hashes commit (tree leaves) but never replace values. Rejected: `bstr` raw-bytes
style (consistency with neighbours) — arithmetic ergonomics win; ISO8601 string
(the old leaf-42 comment) — parsing ambiguity, waste.

### D2 — Mandatory `module_rtc_time` + `time_check_result`, optional `host_time_claim`
Case (a) (integrator supplies no host time) still gets the module witness:
monotonic continuity / no-tamper is proven from `module_rtc_time` alone across
the attestation chain. So 16 and 18 are mandatory; 17 is optional and its
absence *is* the `no_host_time` case (verdict enum must match: `17` absent ⇔
`18 = no_host_time`).

### D3 — Leaf 42 repurposed to device-owned module RTC
The v2.0.0 comment "provided by the host device" is a grammar contradiction
(no request field can deliver it; fixed leaves are device-owned) and the host
verifier already treats leaf 42 as RTC-backed. The in-place revision corrects
the comment and assigns the module's own reading. **Requested from the schema
owner: confirm this reading** (the change is comment-only for leaf 42's slot;
the semantic fix is which value the module places there).

### D4 — Fixed set 12 → 14 leaves
`43: 15` (host claim, `leaf_padding` when absent) and `44: 16` (verdict) join
the fixed set; `leaf_source` dynamic slots shrink 20 → 18 (`45..62`).
`tree_depth` 5 and total 32 leaves unchanged. Accepted cost: consumers re-pin
anyway (SHA-256s change).

### D5 — Verdict enum is nameless-enum `&( … )`
`time_check_result = &(no_host_time: 0, approved: 1, not_approved: 2)` —
extensible by appending values; the *tolerance* and anchor arithmetic stay in
`shcap_policy_id` policy, not the schema. Verifiers recompute the check
independently; the module verdict is the live-enforcement record.

## Risks / open questions

- Consumers that hard-coded leaf 42 as host-provided ISO8601 must migrate —
  none exist in production (v2.0.0 not yet implemented by any module); client
  verifier already parses RTC-style values there.
- RTC second-granularity vs sub-second claims: tolerance policy must account
  for ±1 s quantisation (documented in the spec, policy owns the number).
