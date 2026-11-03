#!/usr/bin/env python3
"""SEAD protocol conformance report renderer (OpenSpec 2.1).

Runs the full conformance probe set against a live sead-core (gRPC
Core.PostEvent — the RPC behind POST /events) and RENDERS the result with
the two cases clearly labeled, per the OpenSpec honesty requirement:

  CASE 1 — REJECTED: non-SEAD / malformed payloads.
      These are not valid SEAD envelopes at all. sead-core rejects them at
      the EXISTING decode + validate_envelope layers
      (ERR_INVALID_CBOR / ERR_INVALID_ENVELOPE). No new detection added.

  CASE 2 — NOT REJECTED: valid-envelope-but-wrong-scheme payloads.
      These are well-formed SEAD envelopes whose body violates the
      sead_v1.3.0.cddl scheme. sead-core ACCEPTS them today — the
      documented scheme-validation GAP. This is NOT a pass.

Plus a positive control (genuine envelope -> accepted) proving the ingest
path works, so the Case 1 rejections are specific to non-compliance.

The renderer is a pure function (render_report) over collected probe results
so the labelling can be reviewed independently of the live run.

Exit 0 = every probe behaved as documented (positive accepted, Case 1 all
rejected with expected codes, Case 2 all accepted = gap still holds) AND
the honesty self-audit (audit_honesty) confirms the rendered console output
is honest about what is and isn't caught: accepted wrong-scheme probes are
labelled NOT REJECTED, the GAP is named and disclaimed as not a pass, the
incidental rejection stays labelled incidental, and no blanket "PASS" is
claimed while the gap is open. The audit is itself self-tested against a
deliberately dishonest render.
Non-zero = behaviour drifted from the documented contract, or the console
output was found dishonest — update OpenSpec.
"""
import sys, os, socket, subprocess, tempfile, time, hashlib
from pathlib import Path

SEAD = Path("/home/bd/projects/sead-service")
XMSS = Path("/home/bd/projects/xmss-reference/core")
WS = Path(os.environ.get("CONFORMANCE_REPORT_WS", Path(__file__).resolve().parent))
os.chdir(WS)

# ── XMSS-SHAKE256_20_256 signing (same harness as the Phase 1 tests) ────────
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

def envelope_for(body: bytes, event_type: int = 1) -> bytes:
    """Wrap a body in a fully valid SEAD envelope (event_id + org signature)."""
    event_id = hashlib.shake_256(body).digest(32)
    sig_target = cbor2.dumps({1: event_type, 3: event_id}, canonical=True)
    return cbor2.dumps({1: "1.1.2", 2: event_type, 3: event_id, 4: body,
                       5: sign(sig_target)}, canonical=True)

# ── Probe set ───────────────────────────────────────────────────────────────
# Each probe: (case_group, name, payload_bytes, expected_outcome, expected_code, why)
#   expected_outcome: "ACCEPTED" or "REJECTED"
#   expected_code:    substring required in the rejection detail (None if ACCEPTED)

# Positive control: genuine org_genesis per sead_v1.3.0.cddl.
merkle_root = hashlib.shake_256(b"\x55").digest(32)
endorsement = [b"\x11", pk, merkle_root, sign(merkle_root)]
body_ok = cbor2.dumps({1: org_id, 2: pk, 3: now, 4: 0, 5: [endorsement]},
                      canonical=True)

# Case 1: non-SEAD / malformed — NOT valid SEAD envelopes at all.
c1_probes = [
    ("empty_bytes", b"", "ERR_INVALID_CBOR",
     "empty envelope bytes — undecodable"),
    ("non_cbor_bytes",
     b"This is definitely not CBOR - just a plain text non-SEAD payload.",
     "ERR_INVALID_CBOR",
     "arbitrary non-CBOR bytes"),
    ("missing_body_and_signature",
     cbor2.dumps({1: "1.1.2", 2: 1, 3: b"\x00" * 32}, canonical=True),
     "ERR_INVALID_ENVELOPE",
     "decodable CBOR map missing required envelope fields 4 (body) and 5 (signature)"),
    ("missing_protocol_version",
     cbor2.dumps({2: 1, 3: b"\x00" * 32, 4: b"\xaa" * 10, 5: b"\xbb" * 10},
                 canonical=True),
     "ERR_INVALID_ENVELOPE",
     "decodable CBOR map missing required envelope field 1 (protocol_version)"),
]

# Case 2: valid-envelope-but-wrong-scheme — envelope is fine, body violates CDDL.
body_a = cbor2.dumps({1: org_id, 2: pk, 3: now, 4: 0, 5: [endorsement],
                      6: "extra_key_not_in_scheme",
                      999: b"unknown_key_outside_dag_links_range"}, canonical=True)
pairs = [(1, org_id), (2, pk), (3, now), (4, 0), (5, [endorsement])]
body_b = (b"\xbf"
          + b"".join(cbor2.dumps(k) + cbor2.dumps(v) for k, v in pairs)
          + b"\xff")
body_c = cbor2.dumps({1: b"\x77" * 32, 2: "not_a_public_key", 3: now,
                      4: "reason_string_not_timestamp"}, canonical=True)
c2_probes = [
    ("extra_unknown_keys", envelope_for(body_a), None,
     "body violates CDDL org_genesis_body (keys 6, 999 outside * dag_links 90-94)"),
    ("non_canonical_body", envelope_for(body_b), None,
     "body is non-canonical CBOR (indefinite-length map) — scheme requires canonical"),
    # Case C is the incidental-rejection probe: it is REJECTED, but only by the
    # type-specific decoder (ERR_INVALID_BODY), NOT by scheme validation. It is
    # grouped under CASE 2 to show that even the one wrong-body rejection here
    # is not evidence of scheme validation.
    ("wrong_body_type", envelope_for(body_c), "ERR_INVALID_BODY",
     "non-org_genesis body under event_type=1 — rejected only INCIDENTALLY by the "
     "type-specific decoder, not by scheme validation"),
]

PROBES = (
    [("positive", "genuine_envelope", envelope_for(body_ok), "ACCEPTED", None,
      "genuine org_genesis signed with XMSS-SHAKE256_20_256 (OID 0x12)")]
    + [("case1_rejected", n, p, "REJECTED", code, why)
       for (n, p, code, why) in c1_probes]
    + [("case2_not_rejected", n, p,
        ("REJECTED" if code else "ACCEPTED"), code, why)
       for (n, p, code, why) in c2_probes]
)

# ── gRPC stubs ──────────────────────────────────────────────────────────────
gen = WS / "gen"
gen.mkdir(exist_ok=True)
r = subprocess.run([sys.executable, "-m", "grpc_tools.protoc",
                    f"-I{SEAD / 'protos'}", f"--python_out={gen}", f"--grpc_python_out={gen}",
                    str(SEAD / "protos" / "sead_rpc.proto")],
                   capture_output=True, text=True)
assert r.returncode == 0, f"protoc failed: {r.stderr[:400]}"
sys.path.insert(0, str(gen))
import grpc
os.environ["TEMPORARILY_DISABLE_PROTOBUF_VERSION_CHECK"] = "true"
import sead_rpc_pb2 as pb2
import sead_rpc_pb2_grpc as pb2g

def run_probe(payload):
    """Submit one payload to a FRESH sead-core (fresh DB per probe) and return
    (outcome, detail) where outcome is 'ACCEPTED' or 'REJECTED:<detail>'."""
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
            envelope=pb2.SeadEnvelope(cbor=payload, method="conformance_report"))
        try:
            resp = stub.PostEvent(req, timeout=15)
            return "ACCEPTED", f"status={resp.status!r} event_type_name={resp.event_type_name!r}"
        except grpc.RpcError as e:
            return "REJECTED", f"code={e.code()} details={e.details()!r}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if os.path.exists(db):
            os.remove(db)

# ── Renderer (pure function over collected results) ─────────────────────────
def render_report(rows):
    """Render the conformance result with the two cases clearly labeled.

    rows: list of dicts with keys:
      group   — 'positive' | 'case1_rejected' | 'case2_not_rejected'
      name    — probe name
      outcome — observed 'ACCEPTED' / 'REJECTED'
      detail  — observed detail string
      expected— 'ACCEPTED' / 'REJECTED'
      code    — expected error code substring (or None)
      why     — what the probe demonstrates
      match   — bool: observed behaviour == documented contract
    """
    lines = []
    lines.append("=" * 72)
    lines.append("SEAD PROTOCOL CONFORMANCE REPORT")
    lines.append("=" * 72)

    pos = [r_ for r_ in rows if r_["group"] == "positive"]
    c1 = [r_ for r_ in rows if r_["group"] == "case1_rejected"]
    c2 = [r_ for r_ in rows if r_["group"] == "case2_not_rejected"]

    lines.append("")
    lines.append("POSITIVE CONTROL (path sanity)")
    for r_ in pos:
        lines.append(f"  [{r_['name']}] {r_['outcome']:<8} "
                    f"{'OK' if r_['match'] else 'DRIFT'} — {r_['why']}")
    lines.append("  Meaning: the ingest path works; the rejections below are")
    lines.append("  specific to non-compliance, not a broken path.")

    lines.append("")
    lines.append("CASE 1 — REJECTED: non-SEAD / malformed payloads")
    for r_ in c1:
        tag = "REJECTED" if r_["outcome"] == "REJECTED" else "NOT REJECTED"
        lines.append(f"  [{r_['name']}] {tag:<12} "
                    f"{'OK' if r_['match'] else 'DRIFT'} — {r_['why']}")
        lines.append(f"      observed: {r_['detail']}")
    lines.append("  Meaning: these are NOT valid SEAD envelopes. They are rejected")
    lines.append("  by the EXISTING decode + validate_envelope layers")
    lines.append("  (ERR_INVALID_CBOR / ERR_INVALID_ENVELOPE). No new detection")
    lines.append("  was added by this change.")

    lines.append("")
    lines.append("CASE 2 — NOT REJECTED: valid-envelope-but-wrong-scheme payloads")
    for r_ in c2:
        if r_["outcome"] == "ACCEPTED":
            tag = "NOT REJECTED"
        else:
            tag = "REJECTED*"
        lines.append(f"  [{r_['name']}] {tag:<12} "
                    f"{'OK' if r_['match'] else 'DRIFT'} — {r_['why']}")
        lines.append(f"      observed: {r_['detail']}")
    lines.append("  Meaning: these ARE well-formed SEAD envelopes whose body")
    lines.append("  violates the sead_v1.3.0.cddl scheme. They are ACCEPTED")
    lines.append("  today — the documented scheme-validation GAP. This is NOT a")
    lines.append("  pass. (*) wrong_body_type is rejected only INCIDENTALLY by the")
    lines.append("  type-specific decoder (ERR_INVALID_BODY), not by scheme")
    lines.append("  validation; it does not close the gap.")

    drift = [r_ for r_ in rows if not r_["match"]]
    lines.append("")
    lines.append("-" * 72)
    if drift:
        lines.append("OVERALL: FAIL — behaviour drifted from the documented contract:")
        for r_ in drift:
            lines.append(f"  - {r_['group']}/{r_['name']}: "
                        f"expected {r_['expected']}, observed {r_['outcome']}")
        lines.append("If the server now REJECTS wrong-scheme payloads (Case 2), the")
        lines.append("gap is closed — update openspec/changes/"
                    "sead-protocol-compliance-test (1.3, 2.1, Quality Gate).")
    else:
        lines.append("OVERALL: CONTRACT HELD —")
        lines.append("  Case 1 (non-SEAD/malformed): REJECTED by the existing")
        lines.append("  validate_envelope layer — the operator's scenario works today.")
        lines.append("  Case 2 (valid-envelope-but-wrong-scheme): NOT REJECTED —")
        lines.append("  known GAP, honestly labeled, NOT claimed as a pass.")
    lines.append("=" * 72)
    return "\n".join(lines)

# ── Honesty self-audit (Quality Gate: console output is honest) ─────────────
def audit_honesty(text, rows):
    """Assert the RENDERED console output is honest about what is and isn't
    caught. This guards the report itself, not the server: if a future edit
    to the renderer (or a flipped expectation) ever makes the output claim
    the wrong-scheme GAP is closed, or presents a Case 2 probe as a passing
    rejection, this audit fails the run.

    Returns a list of problems (empty = honest)."""
    problems = []

    # 1. Every Case 2 probe that was actually ACCEPTED must be rendered as
    #    "NOT REJECTED" next to its name — the gap must be visible, never
    #    silently omitted or mislabelled.
    for r_ in rows:
        if r_["group"] == "case2_not_rejected" and r_["outcome"] == "ACCEPTED":
            if f"[{r_['name']}] NOT REJECTED" not in text:
                problems.append(
                    f"Case 2 probe '{r_['name']}' was ACCEPTED but is not "
                    f"rendered as 'NOT REJECTED' — output hides the gap")

    # 2. The gap must be named explicitly as a GAP and explicitly disclaimed
    #    as not a pass (whitespace-collapsed so line wrapping is fine).
    collapsed = " ".join(text.split())
    if "GAP" not in collapsed:
        problems.append("rendered output never names the scheme-validation GAP")
    if "NOT a pass" not in collapsed:
        problems.append("rendered output lacks the 'NOT a pass' disclaimer "
                       "for the accepted wrong-scheme probes")

    # 3. The incidental rejection must stay labelled as incidental — it must
    #    not be presented as evidence of scheme validation.
    if any(r_["group"] == "case2_not_rejected" and r_["outcome"] == "REJECTED"
           for r_ in rows):
        if "INCIDENTAL" not in collapsed:
            problems.append("a Case 2 probe was rejected but the output does "
                           "not label the rejection as INCIDENTAL")

    # 4. While any Case 2 payload is still accepted, the overall verdict must
    #    never read as a blanket pass.
    if any(r_["group"] == "case2_not_rejected" and r_["outcome"] == "ACCEPTED"
           for r_ in rows):
        if "OVERALL: PASS" in text:
            problems.append("output claims 'OVERALL: PASS' while wrong-scheme "
                           "payloads are still accepted")

    return problems

# ── Run ─────────────────────────────────────────────────────────────────────
print("[2/4] probe harness ready (fresh sead-core per probe)")
rows = []
for group, name, payload, expected, code, why in PROBES:
    outcome, detail = run_probe(payload)
    if expected == "ACCEPTED":
        match = outcome == "ACCEPTED"
    else:
        match = outcome == "REJECTED" and (code is None or code in detail)
    rows.append({"group": group, "name": name, "outcome": outcome,
                "detail": detail, "expected": expected, "code": code,
                "why": why, "match": match})
    print(f"  [{group}/{name}] expected={expected} observed={outcome} -> "
          f"{'MATCH' if match else 'DRIFT'}")

print("[3/4] probes complete — rendering report")
print()
report = render_report(rows)
print(report)

# Audit the rendered console output itself (Quality Gate: honesty).
problems = audit_honesty(report, rows)

# Self-test the audit: a deliberately dishonest render (gap claimed as closed,
# accepted probe shown as rejected) MUST be caught, or the audit is toothless.
dishonest = report.replace("NOT REJECTED", "REJECTED").replace(
    "known GAP, honestly labeled, NOT claimed as a pass.",
    "OVERALL: PASS — full scheme conformance achieved.")
if not audit_honesty(dishonest, rows):
    problems.append("honesty audit failed to catch a deliberately dishonest "
                   "render — the audit itself is broken")

drift = [r_ for r_ in rows if not r_["match"]]
print(f"[4/4] {len(rows) - len(drift)}/{len(rows)} probes behaved as documented")
if problems:
    print("HONESTY AUDIT: FAIL — console output misrepresents what is caught:")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("HONESTY AUDIT: PASS — output labels the GAP, the incidental rejection,")
print("and does not claim the wrong-scheme case as caught.")
sys.exit(1 if drift else 0)
