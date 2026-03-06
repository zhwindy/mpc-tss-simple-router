#!/usr/bin/env python3
"""
MPC-TSS 消息路由 / 测试客户端：连接多台 tofnd gRPC 守护进程，协助测试 Keygen / Sign / KeyPresence。
使用前请先生成 proto: pip install -r requirements.txt && bash gen_proto.sh
（依赖本目录下 common.proto、multisig.proto 生成的 common_pb2.py、multisig_pb2.py、multisig_pb2_grpc.py）
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import grpc

# 使用 gen_proto.sh 根据本目录 proto 生成的模块
# KeyPresenceRequest/KeyPresenceResponse 在 common_pb2，Keygen/Sign 相关在 multisig_pb2
try:
    import common_pb2
    import multisig_pb2 as pb2
    import multisig_pb2_grpc as pb2_grpc
except ImportError as e:
    print("请先生成 proto: pip install -r requirements.txt && bash gen_proto.sh", file=sys.stderr)
    print(f"  ({e})", file=sys.stderr)
    sys.exit(1)

# tofnd gRPC 地址（端口 50051），请按实际部署修改为你的节点 IP 或主机名
# 示例：内网或本地 3 台机器
NODES = {
    0: "192.168.1.10:50051",
    1: "192.168.1.11:50051",
    2: "192.168.1.12:50051",
}

ALGORITHM_ECDSA = 0
ALGORITHM_ED25519 = 1


def _channel(addr: str, timeout: float = 30.0) -> grpc.Channel:
    return grpc.insecure_channel(
        addr,
        options=[
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
        ],
    )


def _stub(addr: str):
    return pb2_grpc.MultisigStub(_channel(addr))


def key_presence_one(party_id: int, key_uid: str, algorithm: int = ALGORITHM_ECDSA, pub_key: bytes = b"") -> dict:
    """单节点 KeyPresence 查询。"""
    addr = NODES[party_id]
    try:
        stub = _stub(addr)
        req = common_pb2.KeyPresenceRequest(key_uid=key_uid, pub_key=pub_key, algorithm=algorithm)
        resp = stub.KeyPresence(req, timeout=15)
        r = resp.response
        # 枚举值: 0=UNSPECIFIED, 1=PRESENT, 2=ABSENT, 3=FAIL
        if r == 1:
            status = "PRESENT"
        elif r == 2:
            status = "ABSENT"
        elif r == 3:
            status = "FAIL"
        else:
            status = "UNSPECIFIED"
        return {"party_id": party_id, "addr": addr, "status": status, "error": None}
    except Exception as e:
        return {"party_id": party_id, "addr": addr, "status": None, "error": str(e)}


def keygen_one(party_id: int, key_uid: str, algorithm: int = ALGORITHM_ECDSA) -> dict:
    """单节点 Keygen。"""
    addr = NODES[party_id]
    try:
        stub = _stub(addr)
        req = pb2.KeygenRequest(
            key_uid=key_uid,
            party_uid=str(party_id),
            algorithm=algorithm,
        )
        resp = stub.Keygen(req, timeout=60)
        which = resp.WhichOneof("keygen_response")
        if which == "pub_key":
            return {
                "party_id": party_id,
                "addr": addr,
                "pub_key": resp.pub_key,
                "error": None,
            }
        return {
            "party_id": party_id,
            "addr": addr,
            "pub_key": None,
            "error": getattr(resp, "error", "unknown"),
        }
    except Exception as e:
        return {"party_id": party_id, "addr": addr, "pub_key": None, "error": str(e)}


def sign_one(
    party_id: int,
    key_uid: str,
    msg_to_sign: bytes,
    algorithm: int = ALGORITHM_ECDSA,
    pub_key: bytes = b"",
) -> dict:
    """单节点 Sign。msg_to_sign 需为 32 字节（例如 SHA256 哈希）。"""
    addr = NODES[party_id]
    if len(msg_to_sign) != 32:
        return {"party_id": party_id, "addr": addr, "signature": None, "error": "msg_to_sign must be 32 bytes"}
    try:
        stub = _stub(addr)
        req = pb2.SignRequest(
            key_uid=key_uid,
            msg_to_sign=msg_to_sign,
            party_uid=str(party_id),
            pub_key=pub_key,
            algorithm=algorithm,
        )
        resp = stub.Sign(req, timeout=60)
        which = resp.WhichOneof("sign_response")
        if which == "signature":
            return {"party_id": party_id, "addr": addr, "signature": resp.signature, "error": None}
        return {
            "party_id": party_id,
            "addr": addr,
            "signature": None,
            "error": getattr(resp, "error", "unknown"),
        }
    except Exception as e:
        return {"party_id": party_id, "addr": addr, "signature": None, "error": str(e)}


def cmd_key_presence(key_uid: str, algorithm: int = ALGORITHM_ECDSA) -> None:
    """并行查询所有节点上该 key 是否存在。"""
    print(f"KeyPresence key_uid={key_uid!r} algorithm={algorithm}")
    with ThreadPoolExecutor(max_workers=len(NODES)) as ex:
        futures = {ex.submit(key_presence_one, pid, key_uid, algorithm): pid for pid in NODES}
        for f in as_completed(futures):
            r = f.result()
            err = f" ERROR: {r['error']}" if r["error"] else ""
            print(f"  Node {r['party_id']} ({r['addr']}): {r['status'] or 'N/A'}{err}")


def cmd_keygen(key_uid: str, algorithm: int = ALGORITHM_ECDSA) -> None:
    """并行在所有节点上执行 Keygen（每节点独立生成密钥，用于测试连通性）。"""
    print(f"Keygen key_uid={key_uid!r} algorithm={algorithm} on {len(NODES)} nodes")
    with ThreadPoolExecutor(max_workers=len(NODES)) as ex:
        futures = {ex.submit(keygen_one, pid, key_uid, algorithm): pid for pid in NODES}
        for f in as_completed(futures):
            r = f.result()
            if r["error"]:
                print(f"  Node {r['party_id']} ({r['addr']}): ERROR {r['error']}")
            else:
                pk_hex = r["pub_key"].hex() if r["pub_key"] else ""
                print(f"  Node {r['party_id']} ({r['addr']}): pub_key len={len(r['pub_key'] or b'')} hex={pk_hex[:32]}...")


def _strip_hex_prefix(s: str) -> str:
    """去掉 0x/0X 前缀，便于直接粘贴以太坊等格式的 hex。"""
    s = s.strip()
    if s.lower().startswith("0x"):
        return s[2:].strip()
    return s


def cmd_sign(key_uid: str, msg_hex: str, algorithm: int = ALGORITHM_ECDSA, pub_key_hex: str = "") -> None:
    """在所有节点上并行 Sign。msg_hex 为 32 字节的十六进制（64 个 hex 字符，可带 0x 前缀）。"""
    msg_hex = _strip_hex_prefix(msg_hex)
    try:
        msg_to_sign = bytes.fromhex(msg_hex)
    except Exception as e:
        print(f"无效的 msg_hex: {e}")
        return
    if len(msg_to_sign) != 32:
        print("msg_hex 必须对应 32 字节（64 个十六进制字符）")
        return
    pub_key_hex = _strip_hex_prefix(pub_key_hex)
    pub_key = bytes.fromhex(pub_key_hex) if pub_key_hex else b""
    print(f"Sign key_uid={key_uid!r} msg_len=32 algorithm={algorithm} on {len(NODES)} nodes")
    with ThreadPoolExecutor(max_workers=len(NODES)) as ex:
        futures = {
            ex.submit(sign_one, pid, key_uid, msg_to_sign, algorithm, pub_key): pid
            for pid in NODES
        }
        for f in as_completed(futures):
            r = f.result()
            if r["error"]:
                print(f"  Node {r['party_id']} ({r['addr']}): ERROR {r['error']}")
            else:
                sig_hex = r["signature"].hex() if r["signature"] else ""
                print(f"  Node {r['party_id']} ({r['addr']}): signature len={len(r['signature'] or b'')} hex={sig_hex}")


def cmd_ping() -> None:
    """简单连通性检查：对每个节点做一次 KeyPresence（key 不存在也会返回 ABSENT）。"""
    print("Ping: 检查各节点 gRPC 连通性...")
    key_uid = "_ping_"
    with ThreadPoolExecutor(max_workers=len(NODES)) as ex:
        futures = {ex.submit(key_presence_one, pid, key_uid): pid for pid in NODES}
        for f in as_completed(futures):
            r = f.result()
            if r["error"]:
                print(f"  Node {r['party_id']} ({r['addr']}): FAIL - {r['error']}")
            else:
                print(f"  Node {r['party_id']} ({r['addr']}): OK (status={r['status']})")


def main():
    parser = argparse.ArgumentParser(
        description="MPC-TSS 路由/测试：连接多台 tofnd，测试 Keygen/Sign/KeyPresence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s ping
  %(prog)s keygen --key-uid test-key-1
  %(prog)s key-presence --key-uid test-key-1
  %(prog)s sign --key-uid test-key-1 --msg-hex 0f0e0d0c0b0a090807060504030201000f0e0d0c0b0a09080706050403020100
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ping
    p_ping = sub.add_parser("ping", help="检查所有 tofnd 节点连通性")
    p_ping.set_defaults(func=lambda _: cmd_ping())

    # key-presence
    p_kp = sub.add_parser("key-presence", help="查询各节点上 key 是否存在")
    p_kp.add_argument("--key-uid", required=True, help="key_uid")
    p_kp.add_argument("--algorithm", type=int, default=ALGORITHM_ECDSA, help="0=ECDSA 1=ED25519")
    p_kp.set_defaults(func=lambda a: cmd_key_presence(a.key_uid, a.algorithm))

    # keygen
    p_kg = sub.add_parser("keygen", help="在各节点执行 Keygen（测试用）")
    p_kg.add_argument("--key-uid", required=True, help="key_uid")
    p_kg.add_argument("--algorithm", type=int, default=ALGORITHM_ECDSA, help="0=ECDSA 1=ED25519")
    p_kg.set_defaults(func=lambda a: cmd_keygen(a.key_uid, a.algorithm))

    # sign
    p_sg = sub.add_parser("sign", help="在各节点执行 Sign")
    p_sg.add_argument("--key-uid", required=True, help="key_uid")
    p_sg.add_argument("--msg-hex", required=True, help="32 字节消息的十六进制（64 字符）")
    p_sg.add_argument("--algorithm", type=int, default=ALGORITHM_ECDSA, help="0=ECDSA 1=ED25519")
    p_sg.add_argument("--pub-key-hex", default="", help="可选：SEC1 压缩公钥十六进制，用于定位 mnemonic")
    p_sg.set_defaults(
        func=lambda a: cmd_sign(a.key_uid, a.msg_hex, a.algorithm, a.pub_key_hex),
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
