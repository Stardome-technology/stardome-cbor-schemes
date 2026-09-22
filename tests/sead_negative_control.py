#!/usr/bin/env python3
"""Negative control for SEAD protocol conformance (OpenSpec 1.2).

Submits NON-SEAD / malformed payloads to the event ingest path
(gRPC Core.PostEvent — the RPC behind POST /events) on a live sead-core,
and asserts each is REJECTED with:
  - ERR_INVALID_CBOR      (undecodable CBOR, or empty envelope bytes)
  - ERR_INVALID_ENVELOPE  (decodable CBOR missing required envelope fields)

This exercises the EXISTING rejection layers only (proto_to_envelope decode
+ validate_envelope in sead-core); no production code is changed.

Exit 0 = every case rejected with the expected error code. Non-zero = failure.
"""
import sys, os, socket, subprocess, tempfile, time
from pathlib import Path

SEAD = Path("/home/bd/projects/sead-service")
WS = Path(os.environ.get("NEGATIVE_CONTROL_WS", Path(__file__).resolve().parent))
os.chdir(WS)

import cbor2

# ── Malformed / non-SEAD cases: (name, envelope cbor bytes, expected error code)
#
# Case 1: empty bytes -> proto_to_envelope returns nullopt -> ERR_INVALID_CBOR
# Case 2: random non-CBOR bytes -> SeadEnvelope::decode_cbor fails -> ERR_INVALID_CBOR
# Case 3: valid CBOR map missing body (key 4) and signature (key 5)
#         -> validate_envelope -> ERR_INVALID_ENVELOPE
# Case 4: valid CBOR map missing protocol_version (key 1)
#         -> validate_envelope -> ERR_INVALID_ENVELOPE
CASES = [
    ("empty_bytes",
     b"",
     "ERR_INVALID_CBOR"),
    ("non_cbor_bytes",
     b"This is definitely not CBOR - just a plain text non-SEAD payload.",
     "ERR_INVALID_CBOR"),
    ("missing_body_and_signature",
     cbor2.dumps({1: "1.1.2", 2: 1, 3: b"\x00" * 32}, canonical=True),
     "ERR_INVALID_ENVELOPE"),
    ("missing_protocol_version",
     cbor2.dumps({2: 1, 3: b"\x00" * 32, 4: b"\xaa" * 10, 5: b"\xbb" * 10},
                 canonical=True),
     "ERR_INVALID_ENVELOPE"),
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
print("[1/3] gRPC stubs generated")

# ── Launch live sead-core
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
    print("FAIL: sead-core did not open port", port)
    sys.exit(2)
print(f"[2/3] sead-core live on 127.0.0.1:{port}")

# ── Submit each malformed payload and assert rejection
import grpc
# protoc (grpcio-tools) gencode is newer than the installed protobuf runtime;
# the wire format is compatible, so bypass the strict version gate.
os.environ["TEMPORARILY_DISABLE_PROTOBUF_VERSION_CHECK"] = "true"
import sead_rpc_pb2 as pb2
import sead_rpc_pb2_grpc as pb2g

exit_code = 1
results = []
try:
    ch = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = pb2g.CoreStub(ch)
    for name, payload, expected in CASES:
        req = pb2.PostEventRequest(
            envelope=pb2.SeadEnvelope(cbor=payload, method="negative_control"))
        try:
            resp = stub.PostEvent(req, timeout=15)
            ok = False
            detail = f"UNEXPECTEDLY ACCEPTED status={resp.status!r}"
        except grpc.RpcError as e:
            msg = e.details()
            ok = (e.code() == grpc.StatusCode.INVALID_ARGUMENT
                  and expected in msg)
            detail = f"code={e.code()} details={msg!r}"
        results.append((name, expected, ok, detail))
        print(f"  [{name}] expected={expected} -> {detail} -> "
              f"{'PASS' if ok else 'FAIL'}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    if os.path.exists(db):
        os.remove(db)

failed = [r_ for r_ in results if not r_[2]]
print(f"[3/3] {len(results) - len(failed)}/{len(results)} cases rejected as expected")
if failed:
    print("NEGATIVE CONTROL: FAIL — " + ", ".join(r_[0] for r_ in failed))
    sys.exit(1)
print("NEGATIVE CONTROL: PASS — non-SEAD/malformed payloads REJECTED "
      "(ERR_INVALID_CBOR / ERR_INVALID_ENVELOPE)")
sys.exit(0)
