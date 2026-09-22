#!/usr/bin/env python3
"""INFORMATIONAL gap test for SEAD protocol conformance (OpenSpec 1.3).

Submits VALID-ENVELOPE-BUT-WRONG-SCHEME payloads to the event ingest path
(gRPC Core.PostEvent — the RPC behind POST /events) on a live sead-core and
RECORDS that they are ACCEPTED today. This is the documented scheme-validation
GAP — it is NOT a pass. Per the OpenSpec honesty requirement, the test asserts
only that the observed behaviour matches the documented gap (accepted); if the
server ever starts rejecting these, the test fails so the OpenSpec doc gets
updated rather than silently drifting.

Why the gap exists (verified in sead-service source, read-only):
  - Envelope decode (lib/protocol/envelope.hpp) accepts any CBOR map with
    keys 1-5 of the right types; body (key 4) is an OPAQUE byte string.
  - verify_event_id only checks event_id == SHAKE256(body bytes) — any bytes.
  - handle_org_genesis (src/sead-core/grpc_server.cpp) runs the type-specific
    decoder, which is LENIENT: unknown labels are silently skipped, and body
    CBOR canonical-encoding is never verified.
  - Nothing validates the body against the sead_v1.3.0.cddl scheme at commit.

Cases:
  A extra_unknown_keys  — org_genesis body with valid required fields PLUS
                        keys 6 and 999 (outside the scheme's * dag_links
                        90-94 range) → violates CDDL → ACCEPTED today (GAP).
  B non_canonical_body  — semantically valid org_genesis body encoded with an
                        INDEFINITE-LENGTH map (0xbf..0xff), violating the
                        canonical-CBOR requirement of the scheme → ACCEPTED
                        today (GAP).
  C wrong_body_type     — a non-org_genesis CBOR map submitted under
                        event_type=1 → rejected ERR_INVALID_BODY. Shows some
                        wrong-scheme payloads are caught only INCIDENTALLY by
                        the type-specific decoder, not by scheme validation.

Exit 0 = every case behaved as documented (A,B accepted; C rejected).
Non-zero = behaviour drifted from the documented gap — update OpenSpec.
"""
import sys, os, socket, subprocess, tempfile, time, hashlib
from pathlib import Path

SEAD = Path("/home/bd/projects/sead-service")
XMSS = Path("/home/bd/projects/xmss-reference/core")
WS = Path(os.environ.get("SCHEME_GAP_WS", Path(__file__).resolve().parent))
os.chdir(WS)

import cffi
ffi = cffi.FFI()
ffi.cdef("""
int xmss_set_sha_cb(int (*cb)(const unsigned char *in, unsigned long long inlen, unsigned char *out));
int xmss_sha256_wrapper(const unsigned char *in, unsigned long long inlen, unsigned char *out);
int sd_init_shake(void);
int xmss_sign(unsigned char *sk, unsigned char *sm, unsigned long long *smlen,
              const unsigned char *m, unsigned long long mlen);
""")
src = r'''
#include "fips202.c"
#include "sha256.c"
#include "hash_address.c"
#include "utils.c"
#include "params.c"
#include "hash.c"
#include "wots.c"
#include "xmss_commons.c"
#include "xmss_core_fast.c"
#include "xmss_core_hooks.c"
#include "xmss.c"
#include "randombytes.c"

int sd_init_shake(void) {
    return xmss_set_sha_cb(xmss_sha256_wrapper);
}
'''
lib = ffi.verify(src, include_dirs=[str(XMSS)], extra_compile_args=["-O1", "-w"])
rc = lib.sd_init_shake()
assert rc == 0, f"sd_init_shake rc={rc}"
print("[1/4] XMSS-SHAKE256 library compiled, callbacks registered")

sk = bytearray((SEAD / "test/vectors/xmss_shake256_20_256_sk.bin").read_bytes())
pk = (SEAD / "test/vectors/xmss_shake256_20_256_pk.bin").read_bytes()
assert sk[:4].hex() == "00000012" and pk[:4].hex() == "00000012", "unexpected OID"
# Reset the stale one-time index on this working copy (mirrors sead-service's
# KeyIndexStore override). The index advances in place per signature; this run
# signs each index at most once.
sk[4:8] = b"\x00\x00\x00\x00"
c_sk = ffi.from_buffer(sk)

def sign(msg: bytes) -> bytes:
    sm = ffi.new("unsigned char[]", 8192)
    smlen = ffi.new("unsigned long long *")
    m = ffi.from_buffer(msg)
    rc = lib.xmss_sign(c_sk, sm, smlen, m, len(msg))
    if rc != 0:
        raise RuntimeError(f"xmss_sign rc={rc}")
    total = int(smlen[0])
    return ffi.buffer(sm, total - len(msg))[:]

import cbor2
org_id = hashlib.shake_256(pk).digest(32)
now = int(time.time())
merkle_root = hashlib.shake_256(b"\x44").digest(32)
endorsement = [b"\x11", pk, merkle_root, sign(merkle_root)]

def envelope_for(body: bytes, event_type: int = 1) -> bytes:
    """Wrap a body in a fully valid SEAD envelope (event_id + org signature)."""
    event_id = hashlib.shake_256(body).digest(32)
    sig_target = cbor2.dumps({1: event_type, 3: event_id}, canonical=True)
    return cbor2.dumps({1: "1.1.2", 2: event_type, 3: event_id, 4: body,
                       5: sign(sig_target)}, canonical=True)

# Case A: valid required fields + keys 6 and 999 (NOT in the CDDL scheme:
# org_genesis_body allows only 1-5 plus * dag_links 90-94).
body_a = cbor2.dumps({1: org_id, 2: pk, 3: now, 4: 0, 5: [endorsement],
                      6: "extra_key_not_in_scheme",
                      999: b"unknown_key_outside_dag_links_range"}, canonical=True)

# Case B: same semantics, but the outer body map is encoded INDEFINITE-LENGTH
# (0xbf ... 0xff) — violates canonical CBOR (CDE) required by the scheme.
pairs = [(1, org_id), (2, pk), (3, now), (4, 0), (5, [endorsement])]
body_b = (b"\xbf"
          + b"".join(cbor2.dumps(k) + cbor2.dumps(v) for k, v in pairs)
          + b"\xff")
assert not cbor2.dumps(pairs, canonical=True) == body_b  # sanity: not canonical

# Case C: a non-org_genesis map (no org_pk at key 2) under event_type=1.
body_c = cbor2.dumps({1: b"\x77" * 32, 2: "not_a_public_key", 3: now,
                     4: "reason_string_not_timestamp"}, canonical=True)

CASES = [
    ("extra_unknown_keys",   envelope_for(body_a), "ACCEPTED",
     "body violates CDDL org_genesis_body (keys 6, 999 outside * dag_links)"),
    ("non_canonical_body",   envelope_for(body_b), "ACCEPTED",
     "body is non-canonical CBOR (indefinite-length map) — scheme requires canonical"),
    ("wrong_body_type",      envelope_for(body_c), "REJECTED:ERR_INVALID_BODY",
     "non-org_genesis body under event_type=1 — caught only incidentally"),
]

# ── gRPC stubs
gen = WS / "gen"
gen.mkdir(exist_ok=True)
r = subprocess.run([sys.executable, "-m", "grpc_tools.protoc",
                    f"-I{SEAD / 'protos'}", f"--python_out={gen}", f"--grpc_python_out={gen}",
                    str(SEAD / "protos" / "sead_rpc.proto")],
                   capture_output=True, text=True)
assert r.returncode == 0, f"protoc failed: {r.stderr[:400]}"
sys.path.insert(0, str(gen))

# ── Submit each wrong-scheme payload against a FRESH sead-core instance
# (a fresh DB per case so the second org_genesis with the same org_pk doesn't
# trip ERR_DUPLICATE_ORG before we can observe scheme-validation behaviour).
import grpc
os.environ["TEMPORARILY_DISABLE_PROTOBUF_VERSION_CHECK"] = "true"
import sead_rpc_pb2 as pb2
import sead_rpc_pb2_grpc as pb2g

def run_case(payload):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    db = tempfile.mktemp(suffix=".sqlite")
    proc = subprocess.Popen([str(SEAD / "build/src/sead-core/sead-core"),
                            "-p", str(port), "-d", db, "--log-level", "info"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    up = False
    for _ in range(60):
        try:
            t = socket.create_connection(("127.0.0.1", port), 0.3); t.close(); up = True; break
        except OSError:
            time.sleep(0.25)
    if not up:
        proc.terminate(); proc.wait(timeout=5)
        raise RuntimeError(f"sead-core did not open port {port}")
    try:
        ch = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = pb2g.CoreStub(ch)
        req = pb2.PostEventRequest(
            envelope=pb2.SeadEnvelope(cbor=payload, method="scheme_gap_probe"))
        try:
            resp = stub.PostEvent(req, timeout=15)
            return "ACCEPTED", f"status={resp.status!r} event_type_name={resp.event_type_name!r}"
        except grpc.RpcError as e:
            return f"REJECTED:{e.details()}", f"code={e.code()} details={e.details()!r}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if os.path.exists(db):
            os.remove(db)

print(f"[2/4] probe harness ready (fresh sead-core per case)")
results = []
for name, payload, expected, why in CASES:
    observed, detail = run_case(payload)
    ok = observed == expected if expected == "ACCEPTED" \
         else (observed.startswith("REJECTED:") and expected.split(":")[1] in detail)
    results.append((name, expected, observed, ok, why))
    print(f"  [{name}] expected={expected} observed={observed} -> "
          f"{'MATCH' if ok else 'DRIFT'}   ({why})")

drift = [r_ for r_ in results if not r_[3]]
print(f"[3/4] {len(results) - len(drift)}/{len(results)} cases behaved as documented")
print("[4/4] RESULT")
if drift:
    print("SCHEME GAP TEST: FAIL — behaviour drifted from the documented gap: "
          + ", ".join(r_[0] for r_ in drift))
    print("If the server now REJECTS wrong-scheme payloads, the gap is closed — "
          "update openspec/changes/sead-protocol-compliance-test (1.3, Quality Gate).")
    sys.exit(1)
print("SCHEME GAP TEST: GAP CONFIRMED — valid-envelope-but-wrong-scheme payloads "
      "are ACCEPTED today (cases A, B). This is NOT a pass: scheme validation at "
      "commit is a known gap. Case C shows wrong-body-type rejection is only "
      "incidental (type-specific decoder), not scheme validation.")
sys.exit(0)
