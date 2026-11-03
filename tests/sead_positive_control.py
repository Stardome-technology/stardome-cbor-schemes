#!/usr/bin/env python3
"""Positive control for SEAD protocol conformance (OpenSpec 1.1).

Builds a GENUINE SEAD envelope (org_genesis, event_type=1) per
sead_v1.3.0.cddl, signs it with the precomputed XMSS-SHAKE256_20_256
keypair (OID 0x12), submits it to a live sead-core via gRPC PostEvent,
and asserts it is ACCEPTED.

Exit 0 = accepted (positive control passes). Non-zero = failure.
"""
import sys, os, socket, subprocess, tempfile, time, hashlib
from pathlib import Path

SEAD = Path("/home/bd/projects/sead-service")
XMSS = Path("/home/bd/projects/xmss-reference/core")
WS = Path(os.environ.get("POSITIVE_CONTROL_WS", Path(__file__).resolve().parent))

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

/* xmss-reference hash.c routes XMSS_SHAKE256 (OID 0x12) directly to
 * shake256(); the sha_cb only serves the XMSS_SHA2 path. Register the
 * built-in SHA-256 wrapper so the callback is never NULL. */
int sd_init_shake(void) {
    return xmss_set_sha_cb(xmss_sha256_wrapper);
}
'''
os.chdir(WS)
lib = ffi.verify(src, include_dirs=[str(XMSS)], extra_compile_args=["-O1", "-w"])
rc = lib.sd_init_shake()
assert rc == 0, f"sd_init_shake rc={rc}"
print("[1/5] XMSS-SHAKE256 library compiled, callbacks registered")

sk = bytearray((SEAD / "test/vectors/xmss_shake256_20_256_sk.bin").read_bytes())
pk = (SEAD / "test/vectors/xmss_shake256_20_256_pk.bin").read_bytes()
assert sk[:4].hex() == "00000012" and pk[:4].hex() == "00000012", "unexpected OID"
# The checked-in vector SK carries a stale one-time index (>= 2^20-1) that trips
# the exhausted-key branch. Reset index_bytes (4 bytes after the OID) to 0 on a
# working copy — mirrors sead-service's KeyIndexStore override at XmssSigner
# construction. Never sign twice with the same index.
sk[4:8] = b"\x00\x00\x00\x00"
c_sk = ffi.from_buffer(sk)  # mutable: one-time index advances in place

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
org_id = hashlib.shake_256(pk).digest(32)          # sead-core: org_id == SHAKE256(org_pk)
now = int(time.time())
merkle_root = hashlib.shake_256(b"\x33").digest(32)
endorsement = [b"\x11", pk, merkle_root, sign(merkle_root)]
body = cbor2.dumps({1: org_id, 2: pk, 3: now, 4: 0, 5: [endorsement]}, canonical=True)
event_id = hashlib.shake_256(body).digest(32)      # event_id = SHAKE256(canonical body)
sig_target = cbor2.dumps({1: 1, 3: event_id}, canonical=True)  # {event_type, event_id}
env_sig = sign(sig_target)
envelope = cbor2.dumps({1: "1.1.2", 2: 1, 3: event_id, 4: body, 5: env_sig}, canonical=True)
print(f"[2/5] genuine org_genesis envelope built ({len(envelope)} bytes), event_id={event_id.hex()}")

gen = WS / "gen"
gen.mkdir(exist_ok=True)
r = subprocess.run([sys.executable, "-m", "grpc_tools.protoc",
                    f"-I{SEAD / 'protos'}", f"--python_out={gen}", f"--grpc_python_out={gen}",
                    str(SEAD / "protos" / "sead_rpc.proto")],
                   capture_output=True, text=True)
assert r.returncode == 0, f"protoc failed: {r.stderr[:400]}"
sys.path.insert(0, str(gen))
print("[3/5] gRPC stubs generated")

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
print(f"[4/5] sead-core live on 127.0.0.1:{port}")

import grpc
# protoc (grpcio-tools) gencode is newer than the installed protobuf runtime;
# the wire format is compatible, so bypass the strict version gate.
os.environ["TEMPORARILY_DISABLE_PROTOBUF_VERSION_CHECK"] = "true"
import sead_rpc_pb2 as pb2
import sead_rpc_pb2_grpc as pb2g
exit_code = 1
try:
    ch = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = pb2g.CoreStub(ch)
    req = pb2.PostEventRequest(envelope=pb2.SeadEnvelope(cbor=envelope, method="positive_control"))
    resp = stub.PostEvent(req, timeout=15)
    accepted = resp.status == "accepted" and resp.event_id == event_id.hex()
    print(f"[5/5] PostEvent -> status={resp.status!r} event_type_name={resp.event_type_name!r} "
          f"event_id={resp.event_id!r}")
    if accepted:
        print("POSITIVE CONTROL: PASS — genuine SEAD envelope ACCEPTED")
        exit_code = 0
    else:
        print("POSITIVE CONTROL: FAIL — response mismatch")
except grpc.RpcError as e:
    print(f"[5/5] PostEvent REJECTED code={e.code()} details={e.details()}")
    print("POSITIVE CONTROL: FAIL — genuine envelope was rejected")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    if os.path.exists(db):
        os.remove(db)
sys.exit(exit_code)
