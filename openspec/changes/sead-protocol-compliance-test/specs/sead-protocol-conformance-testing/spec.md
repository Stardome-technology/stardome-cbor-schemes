# sead-protocol-conformance-testing

## ADDED Requirements

### Requirement: Non-SEAD messages are rejected by the existing envelope validator

The test SHALL submit a non-SEAD / malformed payload and assert that `sead-core`
rejects it at `POST /events` — `ERR_INVALID_CBOR` when the bytes are not a
decodable SEAD envelope, or `ERR_INVALID_ENVELOPE` (from `validate_envelope`)
when it decodes but is missing required envelope fields — demonstrating that the
protocol boundary rejects non-compliant messages.

#### Scenario: Non-SEAD blob rejected
- **WHEN** a payload that is not a valid SEAD envelope is submitted to `POST /events`
- **THEN** it is rejected with `ERR_INVALID_CBOR` (undecodable) or
  `ERR_INVALID_ENVELOPE` (missing required fields)
- **AND** the message never enters the DAG

### Requirement: A genuine SEAD envelope is accepted (positive control)

The test SHALL submit a genuine, well-formed SEAD envelope and assert it is
accepted, confirming the rejection is specific to non-compliance rather than a
broken path.

#### Scenario: Genuine envelope accepted
- **WHEN** a genuine SEAD envelope is submitted
- **THEN** it passes `validate_envelope` and is accepted

### Requirement: The scheme-validation gap is documented, not hidden

The test SHALL NOT claim that a well-formed SEAD envelope with a non-conforming
payload scheme is rejected. It SHALL record that this case is currently accepted
at commit and label it a known gap.

#### Scenario: Wrong-scheme gap shown honestly
- **WHEN** a valid-envelope-but-wrong-scheme payload is exercised
- **THEN** the result is recorded as **accepted today (gap)**
- **AND** it is NOT marked as a passing rejection

### Requirement: No new detection logic is added

The change SHALL be test-only; it SHALL NOT modify `validate_envelope` or the
commit path.

#### Scenario: Test-only change
- **WHEN** this change is applied
- **THEN** `validate_envelope` and the commit path are unchanged
- **AND** the rejection demonstrated is the pre-existing behavior
