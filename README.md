# Stardome digital signature schemas

## Changelogs

04/2026 TODOs to keep in mind when updating codebase to v2
added v2 schemas
changed naming conventions
changed from array to objects
dropped host_keys from attestation request
dropped host_keys from attestation response
changed XMSS signature from root-only to root+context
stardome_host_id_response installation_id required

## Schema

Naming conventions:
```
stardome_<..>_schema_vXX.XX.XX
                     |
                     semantic versioning 
```
### Legacy
```
stardome_<..>_scheme_vXX.XX.XX_Y
                     |         |
                     semantic versioning
                               |
                               0 for Stardome SGE (ground) modules
                               1 for Stardome SSP (satellite) modules 
```

## Versions
| Filename | Version | Stardome module |
|----------|:-------:|----------------:|
| sead_v1.1.2 | 1.1.2 | ALL |
| sead_v1.2.0 | 1.2.0 | ALL |
| sead_v1.3.0 | 1.3.0 | ALL |
| stardome-merkle-tree | n/a | ALL |
| stardome_attestation_request_schema_v2.0.0 | 2.0.0 | ALL |
| stardome_attestation_scheme_v1.0.0_0 | 1.0.0 | SGE |
| stardome_attestation_scheme_v1.0.0_1 | 1.0.0 | SSP |
| stardome_attestation_schema_v2.0.0 | 2.0.0 | ALL |
| stardome_attestation_schema_v2.0.1 | 2.0.1 | ALL |
| stardome_attestation_tree_scheme_v1.0.0_0 | 1.0.0 | SGE |
| stardome_attestation_tree_scheme_v1.0.0_1 | 1.0.0 | SSP |
| stardome_attestation_tree_schema_v2.0.0 | 2.0.0 | ALL |
| stardome_attestation_tree_schema_v2.0.1 | 2.0.1 | ALL |
| stardome_epoch_schema_v2.0.0 | 2.0.0 | ALL |
| stardome_host_id_response_scheme_v1.0.0_0 | 1.0.0 | SGE |
| stardome_host_id_response_scheme_v1.0.0_1 | 1.0.0 | SSP |
| stardome_host_id_response_schema_v2.0.0 | 2.0.0 | ALL |
| stardome_proof_request_scheme_v1.0.0_0 | 1.0.0 | ALL |
| stardome_proof_request_schema_v2.0.0 | 2.0.0 | ALL |
| stardome_sign_request_scheme_v1.0.0_0 | 1.0.0 | SGE |
| stardome_sign_request_scheme_v1.0.0_1 | 1.0.0 | SSP |

## SEAD authorization validity (`not_before` / `not_after`)

In the SEAD DAG schemas (`sead_v1.1.2` / `v1.2.0` / `v1.3.0`) the `not_before` / `not_after`
fields are the **overall validity window** of an org key or an edge authorization:

- `org_genesis_body.not_before` / `.not_after` bound the validity of the **org writer key**
  (when it may sign org-level events such as `edge_authorization`).
- `edge_authorization_body.not_before` / `.not_after` bound the window during which the org
  authorizes **that edge key** to act (commit `edge_commit` / `edge_batch_head` under the org).

They are **NOT** a window within which a single one-off action must be performed. A verifier
treats the key as authorized only while `now` is inside `[not_before, not_after]`. **After
`not_after` elapses, the key is no longer authorized and verifiers reject new events from it**
(e.g. sead-core returns `ERR_EDGE_NOT_AUTHORIZED: no active edge authorization`). `not_after`
of `0` means *no expiry*.

Practical implication: a cluster enrolled with a bounded `not_after` must be **re-enrolled**
(fresh `org_genesis` + `edge_authorization`, or an extended `not_after`) once the window passes,
or no new commits from those keys will be accepted.

## Encoding notes (CBOR)

The on-device firmware is resource-constrained, so some request handlers use a lightweight CBOR parser that supports the schema-defined subset. In particular, `stardome_proof_request_scheme_v1.0.0_*.cddl` and `stardome_proof_request_schema_v2.0.0.cddl` requests should use **definite-length** CBOR containers (no indefinite-length arrays/maps/strings). Python `cbor2` emits definite-length CBOR by default.

