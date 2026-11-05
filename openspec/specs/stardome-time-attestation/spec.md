# stardome-time-attestation Specification

## Purpose
Define how Stardome module schemas bind time to attestations so that time is
attested by the module itself: the attestation always carries the module's own
raw free-running RTC reading (`module_rtc_time`) as the tamper/monotonicity
witness, an optional host-declared time (`host_time_claim`) is cross-checked by
the module at signing, and the module's verdict (`time_check_result`) is
recorded in the attestation so anti-dating enforcement is visible to verifiers
while tolerance remains a policy (`shcap_policy_id`) concern, not a schema one.

## Requirements

### Requirement: Module self-time in the attestation
The attestation SHALL carry `module_rtc_time` (key 16, `uint`): the raw reading
of the module's own free-running RTC (Unix seconds) at signing time. The value
SHALL be the module-measured count and SHALL NOT be adjusted, slewed, or
supplied by the host.

#### Scenario: Attestation without any host time
- **WHEN** a request carries no `host_time_claim`
- **THEN** the attestation still contains `module_rtc_time`
- **AND** `time_check_result` is `no_host_time` (0)
- **AND** `host_time_claim` (key 17) is absent

### Requirement: Host time claim ingress
The attestation request SHALL accept an optional `host_time_claim` (key 8,
`uint`, Unix seconds). The module SHALL NOT alter the claimed value; it echoes
it verbatim as attestation key 17 when present.

#### Scenario: Claim delivered and echoed
- **WHEN** a request carries `host_time_claim = T`
- **THEN** the attestation contains `host_time_claim = T` (key 17)

### Requirement: Module anti-dating verdict
The attestation SHALL carry `time_check_result` (key 18) with value
`no_host_time` (0), `approved` (1), or `not_approved` (2): the module's verdict
at signing on whether `host_time_claim` is consistent with its own RTC within
the tolerance defined by the active `shcap_policy_id`. The consistency
tolerance and anchor arithmetic SHALL NOT be defined by the schema.

#### Scenario: Claim outside tolerance
- **WHEN** a request carries `host_time_claim` inconsistent with the module RTC
  beyond the policy tolerance
- **THEN** the attestation records `time_check_result = not_approved` (2)
- **AND** the module's refusal/flag behaviour follows policy

### Requirement: Tree commitment of the time fields
The attestation tree SHALL commit each time field in a fixed leaf:
`leaf_timestamp: 12` at slot 42 = module RTC value (device-owned, raw uint
Unix seconds); `leaf_host_time_claim: 15` at slot 43 (`leaf_padding` when
absent); `leaf_time_check_result: 16` at slot 44. Dynamic `leaf_source` slots
SHALL occupy 45..62 (18 slots) with `tree_depth` 5 and 32 leaves unchanged.

#### Scenario: Verifier recomputation
- **WHEN** a verifier holds the module's epoch anchor
- **THEN** it can independently recompute
  `host_time_claim ≈ anchor + (module_rtc_time − anchor_rtc)` within tolerance
- **AND** compare the result against the recorded `time_check_result`
